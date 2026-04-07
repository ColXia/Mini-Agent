/**
 * Channel type definitions for Mini-Agent.
 *
 * These interfaces define the contract between channels and the Gateway.
 */

/**
 * Unified message format from any channel.
 */
export interface ChannelMessage {
  /** Unique message identifier from the channel */
  message_id: string;
  /** Message text content */
  content: string;
  /** Channel type identifier (e.g., "qq", "wechat") */
  channel_type: string;
  /** Conversation/channel/group identifier */
  conversation_id: string;
  /** Optional sender identifier */
  sender_id?: string;
  /** Additional channel-specific metadata */
  metadata?: Record<string, any>;
}

/**
 * Unified reply format to send back to a channel.
 */
export interface ChannelReply {
  /** Whether the operation was successful */
  success: boolean;
  /** Reply content */
  content: string;
  /** Optional error message */
  error?: string;
}

/**
 * Session state for channel-side session management.
 */
export interface SessionState {
  /** Conversation identifier */
  conversation_id: string;
  /** Gateway session ID */
  session_id?: string;
  /** Workspace directory */
  workspace_dir: string;
  /** Dry run mode */
  dry_run: boolean;
  /** Additional metadata */
  metadata?: Record<string, any>;
}

/**
 * Gateway client interface.
 *
 * Channels use this interface to communicate with the Gateway.
 */
export interface IGatewayClient {
  /**
   * Send a message to the Gateway and get a reply.
   */
  chat(request: ChatRequest): Promise<ChatResponse>;

  /**
   * Reset a session's context.
   */
  resetSession(sessionId: string): Promise<boolean>;

  /**
   * Check if the Gateway is healthy.
   */
  healthCheck(): Promise<boolean>;
}

/**
 * Chat request to the Gateway.
 */
export interface ChatRequest {
  /** User message content */
  message: string;
  /** Optional session ID for conversation continuity */
  session_id?: string;
  /** Optional workspace directory */
  workspace_dir?: string;
  /** Optional channel type (e.g., qq, wechat) */
  channel_type?: string;
  /** Optional channel conversation key */
  conversation_id?: string;
  /** Optional sender identifier */
  sender_id?: string;
  /** Optional channel metadata */
  metadata?: Record<string, any>;
  /** If true, don't actually call the LLM */
  dry_run?: boolean;
}

/**
 * Chat response from the Gateway.
 */
export interface ChatResponse {
  /** Session identifier */
  session_id: string;
  /** Assistant reply text */
  reply: string;
  /** Total messages in session */
  message_count: number;
  /** Token usage count */
  token_usage: number;
  /** Workspace directory */
  workspace_dir: string;
  /** Last update timestamp */
  updated_at: string;
}

/**
 * Session store interface for channel-side session management.
 */
export interface ISessionStore {
  /**
   * Get session state for a conversation.
   */
  get(conversationId: string): Promise<SessionState | undefined>;

  /**
   * Save session state for a conversation.
   */
  set(conversationId: string, state: SessionState): Promise<void>;

  /**
   * Delete session state for a conversation.
   */
  delete(conversationId: string): Promise<void>;

  /**
   * Check if a session exists.
   */
  exists(conversationId: string): Promise<boolean>;
}

/**
 * Channel interface.
 *
 * All communication channels must implement this interface.
 */
export interface IChannel {
  /**
   * Get the channel type identifier.
   */
  getChannelType(): string;

  /**
   * Start the channel.
   */
  start(): Promise<void>;

  /**
   * Stop the channel.
   */
  stop(): Promise<void>;

  /**
   * Send a message to a specific conversation.
   */
  sendMessage(conversationId: string, content: string): Promise<ChannelReply>;

  /**
   * Get the Gateway client.
   */
  readonly gatewayClient: IGatewayClient;

  /**
   * Get the session store.
   */
  readonly sessionStore: ISessionStore;
}

/**
 * Channel configuration.
 */
export interface ChannelConfig {
  /** Gateway base URL */
  gatewayBaseUrl: string;
  /** Default workspace directory */
  defaultWorkspace: string;
  /** Default dry run mode */
  defaultDryRun: boolean;
  /** Gateway request timeout in milliseconds */
  timeout?: number;
}
