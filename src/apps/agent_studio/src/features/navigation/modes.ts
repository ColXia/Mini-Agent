import type { ModeKey } from "../../types";

export interface StudioModeMeta {
  key: ModeKey;
  title: string;
  description: string;
}

export const STUDIO_MODES: StudioModeMeta[] = [
  {
    key: "workspace",
    title: "工作台",
    description: "主 Agent 对话与任务执行。"
  },
  {
    key: "knowledge_base",
    title: "知识库",
    description: "文档上传、索引维护与混合检索调试。"
  },
  {
    key: "channel",
    title: "渠道联调",
    description: "QQ/微信消息入口联调，统一接入主 Agent。"
  },
  {
    key: "novel_studio",
    title: "小说工坊",
    description: "小说子程序：写作、定稿、版本与回滚。"
  },
  {
    key: "assets",
    title: "素材库",
    description: "预览封面、插图与音频产物。"
  },
  {
    key: "studio_ops",
    title: "运维面板",
    description: "模型提供方与记忆数据管理。"
  }
];
