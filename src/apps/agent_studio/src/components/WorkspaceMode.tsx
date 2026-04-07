import { FormEvent, KeyboardEvent, useEffect, useState } from "react";

import type { ChatMessage } from "../types";

interface WorkspaceModeProps {
  sessionId: string;
  workspaceDir: string;
  dryRun: boolean;
  streamMode: boolean;
  sending: boolean;
  messages: ChatMessage[];
  onDryRunChange: (value: boolean) => void;
  onStreamModeChange: (value: boolean) => void;
  onWorkspaceDirChange: (workspaceDir: string) => void;
  onSend: (message: string) => Promise<void>;
  onCancelSend: () => void;
}

export function WorkspaceMode(props: WorkspaceModeProps) {
  const {
    sessionId,
    workspaceDir,
    dryRun,
    streamMode,
    sending,
    messages,
    onDryRunChange,
    onStreamModeChange,
    onWorkspaceDirChange,
    onSend,
    onCancelSend
  } = props;
  const [input, setInput] = useState("");
  const [workspaceDraft, setWorkspaceDraft] = useState(workspaceDir);

  useEffect(() => {
    setWorkspaceDraft(workspaceDir);
  }, [workspaceDir]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const text = input.trim();
    if (!text || sending) {
      return;
    }
    setInput("");
    await onSend(text);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit(event as unknown as FormEvent);
    }
  };

  return (
    <section className="mode-panel workspace-layout">
      <header className="card top-card">
        <div className="row between">
          <div>
            <h2>工作台</h2>
            <p className="muted">通用对话模式：与 Mini-Agent 持续对话并执行开发任务。</p>
          </div>
          <div className="pill">会话：{sessionId || "新建"}</div>
        </div>
        <div className="row wrap">
          <label className="field grow">
            <span>工作目录</span>
            <input
              value={workspaceDraft}
              onChange={(event) => setWorkspaceDraft(event.target.value)}
              placeholder="C:/Users/Conli/Mini-Agent"
            />
          </label>
          <button
            type="button"
            onClick={() => onWorkspaceDirChange(workspaceDraft.trim())}
            className="ghost-button"
          >
            应用
          </button>
          <label className="field small">
            <span>试运行</span>
            <select
              value={String(dryRun)}
              onChange={(event) => onDryRunChange(event.target.value === "true")}
            >
              <option value="false">关闭</option>
              <option value="true">开启</option>
            </select>
          </label>
          <label className="field small">
            <span>返回模式</span>
            <select
              value={String(streamMode)}
              onChange={(event) => onStreamModeChange(event.target.value === "true")}
            >
              <option value="true">SSE 流式</option>
              <option value="false">普通响应</option>
            </select>
          </label>
        </div>
      </header>

      <div className="card message-list">
        {messages.length === 0 ? (
          <div className="empty">
            先发第一条消息，例如：「请先给我一份本项目可视化改造计划」。
          </div>
        ) : (
          messages.map((message) => (
            <article key={message.id} className={`bubble ${message.role}`}>
              <header>
                <strong>{message.role === "assistant" ? "Mini-Agent" : "你"}</strong>
                <span>{message.time}</span>
              </header>
              <p>{message.content}</p>
            </article>
          ))
        )}
      </div>

      <form className="card composer" onSubmit={submit}>
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入任务说明，Enter 发送，Shift+Enter 换行"
          rows={4}
        />
        <div className="row end">
          {sending && streamMode ? (
            <button type="button" onClick={onCancelSend} className="warn-button">
              取消流式
            </button>
          ) : null}
          <button type="submit" disabled={sending || !input.trim()} className="primary-button">
            {sending ? "发送中..." : "发送给 Agent"}
          </button>
        </div>
      </form>
    </section>
  );
}
