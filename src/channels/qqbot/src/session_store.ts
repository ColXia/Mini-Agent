/**
 * Lightweight file-backed session store implementation.
 */

import * as fs from "fs";
import * as path from "path";
import { ISessionStore, SessionState } from "@mini-agent/channel-types";

export interface MemorySessionStoreOptions {
  filePath?: string;
}

/**
 * Session store with in-memory hot cache and JSON persistence.
 *
 * This keeps runtime logic small while preserving channel sessions across restarts.
 */
export class MemorySessionStore implements ISessionStore {
  private store: Map<string, SessionState> = new Map();
  private loaded = false;
  private filePath: string;

  constructor(options: MemorySessionStoreOptions = {}) {
    this.filePath = path.resolve(options.filePath || path.join(process.cwd(), ".qqbot_sessions.json"));
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
      const payload = JSON.parse(raw) as { sessions?: Record<string, SessionState> };
      const sessions = payload.sessions || {};
      for (const [conversationId, state] of Object.entries(sessions)) {
        if (state && typeof state === "object") {
          this.store.set(conversationId, state);
        }
      }
    } catch {
      // Keep running with empty store if the persistence file is invalid.
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

  async get(conversationId: string): Promise<SessionState | undefined> {
    this.ensureLoaded();
    return this.store.get(conversationId);
  }

  async set(conversationId: string, state: SessionState): Promise<void> {
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

  /**
   * Clear all sessions.
   */
  clear(): void {
    this.ensureLoaded();
    this.store.clear();
    this.persist();
  }

  /**
   * Get the number of sessions.
   */
  get size(): number {
    this.ensureLoaded();
    return this.store.size;
  }
}
