# Discord AI Bridge

一個簡單的 Discord 訊息記錄與 AI 回覆橋接器。預設只記錄指定頻道；設定 `REPLY_IN_CHANNEL=true` 後，才會把訊息送到 OpenAI 並回覆。

## 安裝

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

編輯 `.env` 後執行：

```bash
python discord_ai_bridge.py
```

## 隱私與安全

- `.env`、`history.json`、`messages.jsonl` 均已由 `.gitignore` 排除。
- `messages.jsonl` 會保存訊息內容、作者顯示名稱、ID 與附件 URL，請只在已告知成員的頻道使用。
- 啟用 AI 回覆時，近期對話內容會送往設定的 OpenAI API。
- 建議設定 `TARGET_CHANNEL_ID`，並定期刪除不再需要的本機歷史紀錄。
- Discord Bot Token 與 OpenAI API Key 只能放在 `.env`，不要寫進原始碼或提交到 Git。

## 必要 Discord 設定

在 Discord Developer Portal 為 Bot 啟用 **Message Content Intent**。
