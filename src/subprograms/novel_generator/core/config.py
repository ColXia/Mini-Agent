"""Novel Generator configuration."""

from dataclasses import asdict, dataclass
from pathlib import Path
import json


@dataclass
class DemoConfig:
    """Novel generator configuration."""

    topic: str
    genre: str
    num_chapters: int
    words_per_chapter: int
    model: str = "MiniMax-M2.5"
    temperature: float = 0.8
    max_tokens: int = 4096

    @classmethod
    def load(cls, path: Path) -> "DemoConfig":
        """Load configuration from a JSON file.

        Args:
            path: Path to the configuration file

        Returns:
            DemoConfig instance
        """
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    def save(self, path: Path) -> None:
        """Save configuration to a JSON file.

        Args:
            path: Path to save the configuration
        """
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
