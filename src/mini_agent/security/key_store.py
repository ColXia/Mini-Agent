"""Secure key storage with AES encryption for API keys and secrets."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


@dataclass
class EncryptedKey:
    """Encrypted key container."""

    key_id: str
    encrypted_value: str
    salt: str
    nonce: str
    tag: str
    created_at: str
    algorithm: str = "AES-256-GCM"
    metadata: dict[str, Any] = field(default_factory=dict)


class KeyEncryptionError(Exception):
    """Error during key encryption/decryption."""


class KeyStore:
    """Secure key storage with AES-256-GCM encryption."""

    KEY_LENGTH = 32  # AES-256
    NONCE_LENGTH = 12  # GCM recommended nonce size
    SALT_LENGTH = 16
    TAG_LENGTH = 16

    def __init__(
        self,
        storage_path: Path,
        *,
        master_key: bytes | None = None,
        master_key_env: str = "MINI_AGENT_MASTER_KEY",
    ) -> None:
        self.storage_path = Path(storage_path).expanduser().resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._keys_file = self.storage_path / "encrypted_keys.json"

        # Get or generate master key
        if master_key is not None:
            self._master_key = master_key
        else:
            env_key = os.environ.get(master_key_env)
            if env_key:
                self._master_key = base64.urlsafe_b64decode(env_key.encode())
            else:
                # Generate and store master key
                self._master_key = self._generate_master_key()

        self._keys: dict[str, EncryptedKey] = {}
        self._load_keys()

    def _generate_master_key(self) -> bytes:
        """Generate a new master key and save to file."""
        master_key = secrets.token_bytes(self.KEY_LENGTH)
        key_file = self.storage_path / ".master_key"

        # Save master key (should be protected by file permissions)
        key_file.write_bytes(master_key)
        try:
            os.chmod(key_file, 0o600)  # Owner read/write only
        except Exception:
            pass

        return master_key

    def _derive_key(self, salt: bytes) -> bytes:
        """Derive encryption key from master key using salt."""
        return hashlib.pbkdf2_hmac(
            "sha256",
            self._master_key,
            salt,
            iterations=100000,
            dklen=self.KEY_LENGTH,
        )

    def _load_keys(self) -> None:
        """Load encrypted keys from storage."""
        if not self._keys_file.exists():
            return

        try:
            data = json.loads(self._keys_file.read_text(encoding="utf-8"))
            for key_id, key_data in data.items():
                self._keys[key_id] = EncryptedKey(
                    key_id=key_data.get("key_id", key_id),
                    encrypted_value=key_data.get("encrypted_value", ""),
                    salt=key_data.get("salt", ""),
                    nonce=key_data.get("nonce", ""),
                    tag=key_data.get("tag", ""),
                    created_at=key_data.get("created_at", ""),
                    algorithm=key_data.get("algorithm", "AES-256-GCM"),
                    metadata=key_data.get("metadata", {}),
                )
        except Exception:
            pass

    def _save_keys(self) -> None:
        """Save encrypted keys to storage."""
        data = {}
        for key_id, key in self._keys.items():
            data[key_id] = {
                "key_id": key.key_id,
                "encrypted_value": key.encrypted_value,
                "salt": key.salt,
                "nonce": key.nonce,
                "tag": key.tag,
                "created_at": key.created_at,
                "algorithm": key.algorithm,
                "metadata": key.metadata,
            }

        self._keys_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            os.chmod(self._keys_file, 0o600)
        except Exception:
            pass

    def encrypt(self, key_id: str, plaintext: str, metadata: dict[str, Any] | None = None) -> EncryptedKey:
        """Encrypt and store a key."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            raise KeyEncryptionError("cryptography package required for key encryption")

        # Generate salt and nonce
        salt = secrets.token_bytes(self.SALT_LENGTH)
        nonce = secrets.token_bytes(self.NONCE_LENGTH)

        # Derive key
        derived_key = self._derive_key(salt)

        # Encrypt
        aesgcm = AESGCM(derived_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        # Extract tag (last 16 bytes)
        encrypted_value = ciphertext[:-self.TAG_LENGTH]
        tag = ciphertext[-self.TAG_LENGTH:]

        encrypted_key = EncryptedKey(
            key_id=key_id,
            encrypted_value=base64.urlsafe_b64encode(encrypted_value).decode(),
            salt=base64.urlsafe_b64encode(salt).decode(),
            nonce=base64.urlsafe_b64encode(nonce).decode(),
            tag=base64.urlsafe_b64encode(tag).decode(),
            created_at=_utc_iso(_utc_now()) or "",
            metadata=metadata or {},
        )

        self._keys[key_id] = encrypted_key
        self._save_keys()

        return encrypted_key

    def decrypt(self, key_id: str) -> str:
        """Decrypt and retrieve a key."""
        if key_id not in self._keys:
            raise KeyEncryptionError(f"Key not found: {key_id}")

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            raise KeyEncryptionError("cryptography package required for key decryption")

        key = self._keys[key_id]

        # Decode values
        salt = base64.urlsafe_b64decode(key.salt.encode())
        nonce = base64.urlsafe_b64decode(key.nonce.encode())
        encrypted_value = base64.urlsafe_b64decode(key.encrypted_value.encode())
        tag = base64.urlsafe_b64decode(key.tag.encode())

        # Derive key
        derived_key = self._derive_key(salt)

        # Decrypt
        aesgcm = AESGCM(derived_key)
        ciphertext = encrypted_value + tag

        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8")
        except Exception as e:
            raise KeyEncryptionError(f"Decryption failed: {e}")

    def delete(self, key_id: str) -> bool:
        """Delete a key from storage."""
        if key_id not in self._keys:
            return False

        del self._keys[key_id]
        self._save_keys()
        return True

    def list_keys(self) -> list[str]:
        """List all stored key IDs."""
        return list(self._keys.keys())

    def get_key_info(self, key_id: str) -> dict[str, Any] | None:
        """Get key metadata without decrypting."""
        if key_id not in self._keys:
            return None

        key = self._keys[key_id]
        return {
            "key_id": key.key_id,
            "created_at": key.created_at,
            "algorithm": key.algorithm,
            "metadata": key.metadata,
        }

    def rotate_master_key(self, new_master_key: bytes | None = None) -> None:
        """Rotate the master key and re-encrypt all keys."""
        if new_master_key is None:
            new_master_key = secrets.token_bytes(self.KEY_LENGTH)

        # Decrypt all keys with old master key
        plaintexts: dict[str, tuple[str, dict[str, Any]]] = {}
        for key_id in list(self._keys.keys()):
            try:
                plaintext = self.decrypt(key_id)
                metadata = self._keys[key_id].metadata
                plaintexts[key_id] = (plaintext, metadata)
            except Exception:
                continue

        # Set new master key
        self._master_key = new_master_key

        # Re-encrypt all keys
        self._keys.clear()
        for key_id, (plaintext, metadata) in plaintexts.items():
            self.encrypt(key_id, plaintext, metadata)

        # Save new master key
        key_file = self.storage_path / ".master_key"
        key_file.write_bytes(new_master_key)
        try:
            os.chmod(key_file, 0o600)
        except Exception:
            pass


class APIKeyManager:
    """High-level API key management."""

    def __init__(self, storage_path: Path = Path("~/.mini-agent/keys")) -> None:
        self.keystore = KeyStore(storage_path)

    def store_api_key(
        self,
        provider: str,
        api_key: str,
        *,
        description: str | None = None,
    ) -> EncryptedKey:
        """Store an API key for a provider."""
        key_id = f"api_key:{provider}"
        metadata = {"provider": provider}
        if description:
            metadata["description"] = description
        return self.keystore.encrypt(key_id, api_key, metadata)

    def get_api_key(self, provider: str) -> str | None:
        """Get an API key for a provider."""
        key_id = f"api_key:{provider}"
        try:
            return self.keystore.decrypt(key_id)
        except KeyEncryptionError:
            return None

    def delete_api_key(self, provider: str) -> bool:
        """Delete an API key for a provider."""
        key_id = f"api_key:{provider}"
        return self.keystore.delete(key_id)

    def list_providers(self) -> list[str]:
        """List all providers with stored API keys."""
        providers = []
        for key_id in self.keystore.list_keys():
            if key_id.startswith("api_key:"):
                providers.append(key_id[8:])
        return providers

    def store_secret(
        self,
        name: str,
        value: str,
        *,
        description: str | None = None,
    ) -> EncryptedKey:
        """Store a generic secret."""
        key_id = f"secret:{name}"
        metadata = {"type": "secret"}
        if description:
            metadata["description"] = description
        return self.keystore.encrypt(key_id, value, metadata)

    def get_secret(self, name: str) -> str | None:
        """Get a generic secret."""
        key_id = f"secret:{name}"
        try:
            return self.keystore.decrypt(key_id)
        except KeyEncryptionError:
            return None
