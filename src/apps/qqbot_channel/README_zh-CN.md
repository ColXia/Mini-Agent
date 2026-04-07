# Mini-Agent QQ Bot 閫氳娓犻亾

鏈洰褰曞熀浜庤吘璁畼鏂?`qq-official-bot` SDK锛屼负 Mini-Agent 澧炲姞 QQ 瀹樻柟鏈哄櫒浜洪€氳娓犻亾銆?
鍙傝€冿細

- [openclaw-qqbot README.zh.md](https://github.com/tencent-connect/openclaw-qqbot/blob/main/README.zh.md)
- [qq-official-bot 鎸囦护绯荤粺璇存槑](https://zhinjs.github.io/qq-official-bot/guide/instruction.html)

## 鍔熻兘

- 鎺ユ敹 QQ 鏈哄櫒浜烘秷鎭苟杞彂鍒?Mini-Agent 缃戝叧 `POST /api/v1/channel/message`
- 姣忎釜浼氳瘽鐙珛缁存姢 `session_id/workspace/dry_run`
- 鍐呯疆甯哥敤鎺у埗鎸囦护

## 鎸囦护

- `/help`锛氭煡鐪嬪府鍔?- `/status`锛氭煡鐪嬪綋鍓嶄細璇濈姸鎬?- `/workspace <path>`锛氳缃綋鍓嶄細璇濆伐浣滅洰褰?- `/dryrun <on|off>`锛氬垏鎹?dry run
- `/reset`锛氶噸缃綋鍓嶄細璇濓紙璋冪敤缃戝叧 reset锛?- `/clear`锛氭竻鐞嗘湰鍦颁細璇濈紦瀛?
## 浣跨敤

1. 澶嶅埗閰嶇疆妯℃澘

```powershell
Copy-Item .\.env.example .\.env
```

2. 缂栬緫 `.env`锛岃嚦灏戝～鍐欙細

- `QQBOT_APPID`
- `QQBOT_SECRET`
- `MINI_AGENT_GATEWAY_BASE`锛堥粯璁?`http://127.0.0.1:8008`锛?
3. 瀹夎渚濊禆骞跺惎鍔?
```powershell
cd .\apps\qqbot_channel
npm install
npm run start
```

## 妯″紡璇存槑

- `QQBOT_MODE=websocket`锛堥粯璁わ級锛氶€傚悎鏈湴寮€鍙?- `QQBOT_MODE=webhook`锛氶渶鎸夊畼鏂瑰钩鍙拌姹傞厤缃叕缃戝彲璁块棶鍦板潃

## 寤鸿

- 濡傛灉浣犺鍦ㄧ敓浜т笂鐢紝寤鸿鎺ュ叆鎸佷箙鍖栧瓨鍌紙鏇挎崲褰撳墠鍐呭瓨 `Map`锛?- 寤鸿涓烘満鍣ㄤ汉渚у啀鍋氱櫧鍚嶅崟涓庨檺娴佷繚鎶?
## 鏃犲洖澶嶆帓鏌?
1. 鏌ョ湅鏃ュ織锛歚apps/qqbot_channel/runtime.log`
2. 鍏堝彂 `/ping` 娴嬭瘯
3. 缇ゅ満鏅纭宸?`@鏈哄櫒浜篳
4. 妫€鏌?`QQBOT_SANDBOX` 鏄惁涓庢満鍣ㄤ汉鐜涓€鑷达紙娌欑/姝ｅ紡锛?5. 妫€鏌?`QQBOT_INTENTS` 鏄惁鍖呭惈锛?   - `GUILD_MESSAGES`
   - `DIRECT_MESSAGE`
   - `GROUP_AT_MESSAGE_CREATE`
   - `C2C_MESSAGE_CREATE`
   - `PUBLIC_GUILD_MESSAGES`

