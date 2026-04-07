import { FormEvent, useMemo, useState } from "react";

import { sendChannelMessage } from "../api";
import type { ChannelMessageResponse } from "../types";

const DEFAULT_METADATA = `{
  "intent": "chat"
}`;

export function ChannelMode() {
  const [channelType, setChannelType] = useState("qq");
  const [conversationId, setConversationId] = useState("group:demo");
  const [senderId, setSenderId] = useState("user-001");
  const [workspaceDir, setWorkspaceDir] = useState("C:/Users/Conli/Mini-Agent");
  const [sessionId, setSessionId] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [message, setMessage] = useState("你好，主 Agent。请给我今天的开发建议。");
  const [metadataText, setMetadataText] = useState(DEFAULT_METADATA);
  const [sending, setSending] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [response, setResponse] = useState<ChannelMessageResponse | null>(null);

  const metadataHint = useMemo(
    () => "metadata 为可选 JSON 对象，可用于 novel_action 或业务扩展。",
    []
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (sending || !message.trim()) {
      return;
    }
    setSending(true);
    setErrorText("");
    try {
      let metadata: Record<string, unknown> | undefined = undefined;
      const trimmed = metadataText.trim();
      if (trimmed) {
        const parsed = JSON.parse(trimmed);
        if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
          throw new Error("metadata 必须是 JSON 对象。");
        }
        metadata = parsed as Record<string, unknown>;
      }

      const payload = await sendChannelMessage({
        channel_type: channelType,
        conversation_id: conversationId,
        sender_id: senderId || undefined,
        message: message.trim(),
        session_id: sessionId || undefined,
        workspace_dir: workspaceDir || undefined,
        dry_run: dryRun,
        metadata
      });
      setResponse(payload);
      setSessionId(payload.session_id);
    } catch (error) {
      setErrorText(String(error));
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="mode-panel">
      <header className="card top-card">
        <div className="row between">
          <div>
            <h2>渠道联调</h2>
            <p className="muted">快速验证 QQ/微信入口消息是否正确进入主 Agent 流程。</p>
          </div>
          <div className="pill">{sending ? "发送中..." : "就绪"}</div>
        </div>
      </header>

      <form className="card top-card" onSubmit={submit}>
        <div className="row wrap">
          <label className="field small">
            <span>渠道类型</span>
            <select value={channelType} onChange={(event) => setChannelType(event.target.value)}>
              <option value="qq">qq</option>
              <option value="wechat">wechat</option>
            </select>
          </label>
          <label className="field grow">
            <span>会话 ID</span>
            <input value={conversationId} onChange={(event) => setConversationId(event.target.value)} />
          </label>
          <label className="field grow">
            <span>发送者 ID</span>
            <input value={senderId} onChange={(event) => setSenderId(event.target.value)} />
          </label>
        </div>

        <div className="row wrap">
          <label className="field grow">
            <span>workspace_dir</span>
            <input value={workspaceDir} onChange={(event) => setWorkspaceDir(event.target.value)} />
          </label>
          <label className="field grow">
            <span>session_id（可选）</span>
            <input value={sessionId} onChange={(event) => setSessionId(event.target.value)} />
          </label>
          <label className="field small">
            <span>试运行</span>
            <select value={String(dryRun)} onChange={(event) => setDryRun(event.target.value === "true")}>
              <option value="true">开启</option>
              <option value="false">关闭</option>
            </select>
          </label>
        </div>

        <label className="field">
          <span>消息内容</span>
          <textarea
            rows={4}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="输入要发送给渠道入口的消息。"
          />
        </label>

        <label className="field">
          <span>metadata（JSON，可选）</span>
          <textarea
            rows={5}
            value={metadataText}
            onChange={(event) => setMetadataText(event.target.value)}
            placeholder='{"intent":"chat"}'
          />
          <small className="muted">{metadataHint}</small>
        </label>

        <div className="row end">
          <button type="submit" className="primary-button" disabled={sending || !message.trim()}>
            {sending ? "发送中..." : "发送到渠道入口"}
          </button>
        </div>
        {errorText ? <p className="error-text">{errorText}</p> : null}
      </form>

      <section className="card">
        <div className="row between">
          <h3>响应</h3>
          <span className="muted">{response ? `session=${response.session_id}` : "暂无响应"}</span>
        </div>
        <pre className="diff-box">{response ? JSON.stringify(response, null, 2) : "等待请求结果..."}</pre>
      </section>
    </section>
  );
}
