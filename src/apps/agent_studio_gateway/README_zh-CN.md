# Mini-Agent Studio Gateway锛堜腑鏂囪鏄庯級

杩欐槸缁欏彲瑙嗗寲鍓嶇浣跨敤鐨?FastAPI 缃戝叧锛岀洰鏍囨槸鎶?Mini-Agent 鑳藉姏缁熶竴鏆撮湶涓?HTTP API锛屽苟鎵胯浇灏忚瀛愮▼搴忥紙Demo锛夈€?
## 鍚姩

鍦ㄩ」鐩牴鐩綍 `C:/Users/Conli/Mini-Agent` 鎵ц锛?
```powershell
uv pip install --python .\.venv\Scripts\python.exe -r .\apps\agent_studio_gateway\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn apps.agent_studio_gateway.main:app --host 127.0.0.1 --port 8008 --reload
```

鍙闂細

- 鍋ュ悍妫€鏌ワ細`http://127.0.0.1:8008/api/v1/system/health`
- 闈欐€佹枃浠讹細`http://127.0.0.1:8008/api/files/...`

---

## 浼氳瘽涓庨€氱敤鑱婂ぉ鎺ュ彛

- `GET /api/v1/agent/sessions`锛氫細璇濆垪琛?- `DELETE /api/v1/agent/sessions/{session_id}`锛氬垹闄や細璇?- `POST /api/v1/agent/sessions/{session_id}/reset`锛氶噸缃細璇濅笂涓嬫枃
- `POST /api/v1/agent/chat`锛氱粡鍏镐竴娆℃€у洖澶?- `GET /api/v1/agent/chat/stream`锛歋SE 娴佸紡鍥炲

### `GET /api/v1/agent/chat/stream` 鏌ヨ鍙傛暟

- `message`锛氱敤鎴疯緭鍏?- `session_id`锛氬彲閫夛紝浼氳瘽澶嶇敤
- `workspace_dir`锛氬彲閫夛紝宸ヤ綔鐩綍
- `dry_run`锛氬彲閫夛紝涓嶈皟鐢ㄧ湡瀹炴ā鍨?
### SSE 浜嬩欢绫诲瀷

- `session`锛氳繑鍥炰細璇濅俊鎭?- `status`锛氳繍琛岀姸鎬?- `heartbeat`锛氬績璺?- `delta`锛氬閲忔枃鏈墖娈?- `done`锛氬畬鎴愶紙鍖呭惈鏈€缁堜俊鎭級
- `error`锛氬紓甯?
---

## 灏忚瀛愮▼搴忔帴鍙?
- `GET /api/v1/novel/config`
- `POST /api/v1/novel/setup`
- `POST /api/v1/novel/write`
- `POST /api/v1/novel/finalize`
- `POST /api/v1/novel/cover`
- `POST /api/v1/novel/illustrate`
- `GET /api/v1/novel/chapters`
- `GET /api/v1/novel/chapter/{chapter_number}`
- `PUT /api/v1/novel/chapter/{chapter_number}`
- `GET /api/v1/novel/chapter/{chapter_number}/versions`
- `GET /api/v1/novel/chapter/{chapter_number}/version/{version_id}`
- `PATCH /api/v1/novel/chapter/{chapter_number}/version/{version_id}`
- `POST /api/v1/novel/chapter/{chapter_number}/rollback`
- `GET /api/v1/novel/chapter/{chapter_number}/diff`
- `GET /api/v1/novel/assets`

---

## 绔犺妭鐗堟湰蹇収鏈哄埗

缃戝叧浼氬湪浠ヤ笅鏃舵満鑷姩鍐欏叆鐗堟湰鍘嗗彶锛圝SONL锛夛細

- 鍐欎綔鐢熸垚锛歚source=generate_write`
- 瀹岀姝ラ锛歚source=finalize_step4`
- 鎵嬪姩淇濆瓨锛歚source=manual_save`

鍘嗗彶鏂囦欢浣嶇疆锛?
`workspace/<project_dir>/chapters/.history/chapter_{n}_{draft|final}.jsonl`

### 鐗堟湰鍏冩暟鎹?
姣忎釜鐗堟湰鏀寔锛?
- `note`锛氬娉?- `tags`锛氭爣绛炬暟缁?
鍙€氳繃 `PATCH /api/v1/novel/chapter/{chapter_number}/version/{version_id}` 鏇存柊銆?
### 涓€閿洖婊?
鍙€氳繃 `POST /api/v1/novel/chapter/{chapter_number}/rollback` 鎸?`version_id` 鍥炴粴绔犺妭鍐呭銆?
- 浼氭妸鐩爣鐗堟湰鍐呭鍐欏洖褰撳墠绔犺妭鏂囦欢
- 鍚屾椂杩藉姞涓€鏉℃柊蹇収锛坄source=rollback`锛夌敤浜庡璁′笌缁х画姣旇緝

---

## 璇存槑

- 缃戝叧榛樿鍏佽璺ㄥ煙锛屾柟渚垮墠绔湰鍦板紑鍙戙€?- `dry_run=true` 鍙敤浜庡墠鍚庣鑱旇皟锛屼笉浼氱湡瀹炴秷鑰楁ā鍨嬭皟鐢ㄣ€?
## 澶栭儴閫氳娓犻亾

浠撳簱宸叉柊澧?QQ Bot 妗ユ帴娓犻亾锛堢嫭绔嬭繘绋嬶級锛?
- `apps/qqbot_channel`
- 閫氳繃 QQ 瀹樻柟鏈哄櫒浜?SDK 鎺ユ敹娑堟伅鍚庯紝杞彂鍒版湰缃戝叧 `POST /api/v1/agent/chat`

---

## Studio Ops Security (P17 T5.2 hardening)

- `MINI_AGENT_STUDIO_API_KEYS`
  - Optional comma-separated Studio API tokens.
  - When non-empty, `/api/v1/ops/*` requires `Authorization: Bearer <token>` or `x-api-key: <token>`.
- `MINI_AGENT_STUDIO_ALLOWED_ROOTS`
  - Optional comma-separated extra roots for `workspace_dir` and `catalog_path`.
  - Defaults already include repo root and `workspace/`.

Smoke check:

```powershell
.\.venv\Scripts\python.exe .\scripts\studio_ops_smoke.py `
  --base-url http://127.0.0.1:8008 `
  --token <studio-token> `
  --expect-auth
```


