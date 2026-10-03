import asyncio
import json
import os
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import discord
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
HISTORY_FILE = BASE_DIR / "history.json"
MESSAGE_LOG_FILE = BASE_DIR / "messages.jsonl"


def load_simple_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_simple_env(BASE_DIR / ".env")

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", "0"))
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "你是 Gary 的 Discord 助手。請用繁體中文、簡潔、直接、口語自然地回覆。",
)
MAX_HISTORY_TURNS = int(os.environ.get("MAX_HISTORY_TURNS", "12"))
HISTORY_CONTEXT_TURNS = int(os.environ.get("HISTORY_CONTEXT_TURNS", "8"))
REPLY_IN_CHANNEL = os.environ.get("REPLY_IN_CHANNEL", "false").lower() in {"1", "true", "yes", "y", "on"}

if not DISCORD_TOKEN:
    raise SystemExit("Missing DISCORD_TOKEN")
if REPLY_IN_CHANNEL and not OPENAI_API_KEY:
    raise SystemExit("Missing OPENAI_API_KEY (required when REPLY_IN_CHANNEL=true)")

ai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# channel_id -> deque[(role, content)]
histories = defaultdict(lambda: deque(maxlen=MAX_HISTORY_TURNS * 2))


def load_histories() -> None:
    if not HISTORY_FILE.exists():
        return
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    for channel_id_str, turns in data.items():
        dq = histories[int(channel_id_str)]
        for item in turns[-dq.maxlen :]:
            if isinstance(item, list) and len(item) == 2:
                dq.append((item[0], item[1]))


def save_histories() -> None:
    payload = {str(cid): list(turns) for cid, turns in histories.items()}
    HISTORY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def log_message(message: discord.Message) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "channel_id": message.channel.id,
        "channel_name": getattr(message.channel, "name", None),
        "message_id": message.id,
        "author_id": message.author.id,
        "author_name": message.author.display_name,
        "content": message.content,
        "attachments": [a.url for a in message.attachments],
        "mentions": [m.id for m in message.mentions],
    }
    with MESSAGE_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


load_histories()


def recent_context(channel_id: int):
    turns = list(histories[channel_id])[-HISTORY_CONTEXT_TURNS * 2 :]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content in turns:
        if role in {"user", "assistant", "system"}:
            messages.append({"role": role, "content": content})
    return messages


def strip_prefix(content: str, bot_id: int) -> str:
    content = content.strip()
    if content.startswith("!g"):
        return content[2:].strip()
    content = re.sub(rf"<@!?{bot_id}>", "", content).strip()
    return content


async def ask_openai(channel_id: int, user_name: str, text: str) -> str:
    if ai is None:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    histories[channel_id].append(("user", f"{user_name}: {text}"))

    def _call():
        return ai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=recent_context(channel_id),
            temperature=0.5,
        )

    resp = await asyncio.to_thread(_call)
    reply = (resp.choices[0].message.content or "").strip()
    if not reply:
        reply = "我剛剛沒有產生有效回覆，再試一次。"
    histories[channel_id].append(("assistant", reply))
    save_histories()
    return reply


@client.event
async def on_ready():
    print(f"Logged in as {client.user} (id={client.user.id})")
    print(f"Target channel: {TARGET_CHANNEL_ID or 'all readable channels'}")
    print(f"Reply in channel: {REPLY_IN_CHANNEL}")
    print(f"Logging messages to: {MESSAGE_LOG_FILE}")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if TARGET_CHANNEL_ID and message.channel.id != TARGET_CHANNEL_ID:
        return

    content = message.content.strip()
    if not content:
        return

    log_message(message)

    if not REPLY_IN_CHANNEL:
        return

    prompt = content
    if not prompt:
        return

    async with message.channel.typing():
        try:
            reply = await ask_openai(message.channel.id, message.author.display_name, prompt)
        except Exception:
            reply = "抱歉，處理失敗，請稍後再試。"

    if len(reply) > 2000:
        reply = reply[:1990] + "…"

    await message.reply(reply, mention_author=False)


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
