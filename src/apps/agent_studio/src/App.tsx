import { useMemo, useState } from "react";

import { AssetsMode } from "./components/AssetsMode";
import { ChannelMode } from "./components/ChannelMode";
import { KnowledgeBaseMode } from "./components/KnowledgeBaseMode";
import { NovelStudioMode } from "./components/NovelStudioMode";
import { StudioOpsMode } from "./components/StudioOpsMode";
import { WorkspaceMode } from "./components/WorkspaceMode";
import { STUDIO_MODES } from "./features/navigation/modes";
import { useWorkspaceChat } from "./features/workspace/useWorkspaceChat";
import type { ModeKey } from "./types";

const DEFAULT_WORKSPACE_DIR = "C:/Users/Conli/Mini-Agent";

function currentDateLabel(): string {
  const date = new Date();
  return date.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  });
}

export default function App() {
  const [mode, setMode] = useState<ModeKey>("workspace");
  const [assetsRefreshNonce, setAssetsRefreshNonce] = useState(0);
  const workspaceChat = useWorkspaceChat(DEFAULT_WORKSPACE_DIR);

  const modeMeta = useMemo(
    () => STUDIO_MODES.find((item) => item.key === mode) ?? STUDIO_MODES[0],
    [mode]
  );

  return (
    <main className="app-shell">
      <aside className="side-nav">
        <header>
          <h1>Mini-Agent Studio</h1>
          <p>主 Agent 与业务流可视化控制台</p>
        </header>
        <nav>
          {STUDIO_MODES.map((item) => (
            <button
              key={item.key}
              type="button"
              className={item.key === mode ? "active" : ""}
              onClick={() => setMode(item.key)}
            >
              <strong>{item.title}</strong>
              <span>{item.description}</span>
            </button>
          ))}
        </nav>
        <footer>
          <small>日期：{currentDateLabel()}</small>
          <small>状态：开发测试</small>
        </footer>
      </aside>

      <section className="content-shell">
        <header className="content-header">
          <div>
            <h2>{modeMeta.title}</h2>
            <p>{modeMeta.description}</p>
          </div>
          <div className="badge-list">
            <span className="chip">
              {workspaceChat.sessionId ? `会话：${workspaceChat.sessionId.slice(0, 8)}` : "会话：新建"}
            </span>
            <span className="chip">模式数：{STUDIO_MODES.length}</span>
          </div>
        </header>

        {mode === "workspace" ? (
          <WorkspaceMode
            sessionId={workspaceChat.sessionId}
            workspaceDir={workspaceChat.workspaceDir}
            dryRun={workspaceChat.dryRun}
            streamMode={workspaceChat.streamMode}
            sending={workspaceChat.sending}
            messages={workspaceChat.messages}
            onDryRunChange={workspaceChat.setDryRun}
            onStreamModeChange={workspaceChat.setStreamMode}
            onWorkspaceDirChange={workspaceChat.setWorkspaceDir}
            onSend={workspaceChat.send}
            onCancelSend={workspaceChat.cancel}
          />
        ) : null}

        {mode === "knowledge_base" ? <KnowledgeBaseMode /> : null}

        {mode === "channel" ? <ChannelMode /> : null}

        {mode === "novel_studio" ? (
          <NovelStudioMode onAssetsDirty={() => setAssetsRefreshNonce((value) => value + 1)} />
        ) : null}

        {mode === "assets" ? <AssetsMode refreshNonce={assetsRefreshNonce} /> : null}

        {mode === "studio_ops" ? <StudioOpsMode /> : null}
      </section>
    </main>
  );
}
