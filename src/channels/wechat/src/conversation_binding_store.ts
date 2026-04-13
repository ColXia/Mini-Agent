/**
 * Lightweight file-backed conversation binding store for WeChat channel.
 */

import * as fs from "fs";
import * as path from "path";
import {
  IRemoteConversationBindingStore,
  RemoteConversationBindingState,
} from "@mini-agent/channel-types";

export interface MemoryConversationBindingStoreOptions {
  filePath?: string;
}

export class MemoryConversationBindingStore implements IRemoteConversationBindingStore {
  private store: Map<string, RemoteConversationBindingState> = new Map();
  private loaded = false;
  private filePath: string;

  constructor(options: MemoryConversationBindingStoreOptions = {}) {
    this.filePath = path.resolve(options.filePath || path.join(process.cwd(), ".wechat_sessions.json"));
  }

  private ensureLoaded(): void {
    if (this.loaded) {
      return;
    }
    this.loaded = true;

    if (!fs.existsSync(this.filePath)) {
      return;
    }

    try {
      const raw = fs.readFileSync(this.filePath, "utf8");
      const payload = JSON.parse(raw) as {
        sessions?: Record<string, RemoteConversationBindingState>;
      };
      const sessions = payload.sessions || {};
      for (const [conversationId, state] of Object.entries(sessions)) {
        if (state && typeof state === "object") {
          this.store.set(conversationId, state);
        }
      }
    } catch {
      // Keep running with empty store if persisted session file is invalid.
    }
  }

  private persist(): void {
    const payload = {
      sessions: Object.fromEntries(this.store.entries()),
    };
    const dir = path.dirname(this.filePath);
    fs.mkdirSync(dir, { recursive: true });

    const tmpPath = `${this.filePath}.tmp`;
    fs.writeFileSync(tmpPath, JSON.stringify(payload, null, 2), "utf8");
    fs.renameSync(tmpPath, this.filePath);
  }

  async get(conversationId: string): Promise<RemoteConversationBindingState | undefined> {
    this.ensureLoaded();
    return this.store.get(conversationId);
  }

  async set(conversationId: string, state: RemoteConversationBindingState): Promise<void> {
    this.ensureLoaded();
    this.store.set(conversationId, state);
    this.persist();
  }

  async delete(conversationId: string): Promise<void> {
    this.ensureLoaded();
    this.store.delete(conversationId);
    this.persist();
  }

  async exists(conversationId: string): Promise<boolean> {
    this.ensureLoaded();
    return this.store.has(conversationId);
  }

  clear(): void {
    this.ensureLoaded();
    this.store.clear();
    this.persist();
  }
}
