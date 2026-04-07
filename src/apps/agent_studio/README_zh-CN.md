# Mini-Agent Studio Frontend

多模式可视化前端（Web）：

- `Workspace`：通用 Agent 对话工作台
- `Novel Studio`：小说子程序（生成/改稿/素材）
- `Assets`：封面、插图、音频预览

## 启动

在项目根目录 `C:/Users/Conli/Mini-Agent` 执行：

```powershell
cd .\apps\agent_studio
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5174`

## 配置网关地址

默认请求 `http://127.0.0.1:8008`。如需修改：

```powershell
$env:VITE_API_BASE="http://127.0.0.1:8008"
npm run dev
```

## 构建

```powershell
npm run build
npm run preview
```


## Studio API Key (P17 T5.2 hardening)

If Studio gateway enables token auth (`MINI_AGENT_STUDIO_API_KEYS`), set frontend key before `npm run dev`:

```powershell
$env:VITE_API_BASE="http://127.0.0.1:8008"
$env:VITE_STUDIO_API_KEY="<studio-token>"
npm run dev
```
