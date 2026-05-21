import os
import logging
import requests
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TELEGRAM_BOT_TOKEN = "8967105953:AAEH95HkGCjnKA8uErDKla6Smuv2zG8vspY"
GROQ_API_KEY       = "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"
CHANNEL_USERNAME   = "@mullerapp"
PORT               = int(os.environ.get("PORT", 8080))
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

logging.basicConfig(level=logging.INFO)
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are a helpful assistant in a Telegram group.
- Answer ONLY the question asked â€” keep it brief and clear (2â€“4 sentences max).
- Detect the user's language automatically and reply in the SAME language (Amharic or English).
- Never make up information. If unsure, say so honestly.
- Do not add unnecessary greetings or filler words."""


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, format, *args):
        pass


def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


def clear_conflict():
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
        r = requests.get(url, timeout=10)
        logging.info(f"Webhook cleared: {r.json()}")
    except Exception as e:
        logging.warning(f"Could not clear webhook: {e}")


def ask_groq(system: str, question: str) -> str:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": question}
        ],
        max_tokens=300
    )
    return response.choices[0].message.content.strip()


def get_channel_id() -> str:
    """Get the channel's numeric ID."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat?chat_id={CHANNEL_USERNAME}"
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("ok"):
            return str(data["result"]["id"])
    except Exception as e:
        logging.warning(f"get_channel_id error: {e}")
    return None


def fetch_channel_posts() -> list:
    """Fetch recent posts directly from channel using forwardFrom."""
    try:
        channel_id = get_channel_id()
        if not channel_id:
            logging.warning("Could not get channel ID")
            return []

        # Use getUpdates with channel_post allowed
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?limit=100&allowed_updates=[%22channel_post%22,%22message%22]"
        response = requests.get(url, timeout=10)
        data = response.json()
        posts = []
        if data.get("ok"):
            for update in data.get("result", []):
                msg = update.get("channel_post")
                if msg and msg.get("text"):
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if chat_id == channel_id:
                        posts.append({
                            "text": msg["text"][:500],
                            "message_id": msg["message_id"]
                        })
        logging.info(f"Found {len(posts)} channel posts")
        return posts
    except Exception as e:
        logging.warning(f"fetch_channel_posts error: {e}")
        return []


def find_relevant_post(question: str, posts: list) -> dict | None:
    if not posts:
        return None
    posts_text = "\n\n".join(
        [f"[POST {i+1}]: {p['text']}" for i, p in enumerate(posts)]
    )
    prompt = f"""Given this question: "{question}"

Here are recent channel posts:
{posts_text}

Which post (if any) is most relevant to answering the question?
Reply with ONLY the post number (e.g. "3") or "NONE" if no post is relevant."""
    try:
        result = ask_groq("You are a relevance checker. Reply with only a number or NONE.", prompt)
        result = result.strip()
        if result == "NONE" or not result.isdigit():
            return None
        idx = int(result) - 1
        if 0 <= idx < len(posts):
            matched = posts[idx]
            channel_name = CHANNEL_USERNAME.lstrip("@")
            link = f"https://t.me/{channel_name}/{matched['message_id']}"
            return {"text": matched["text"], "link": link}
    except Exception as e:
        logging.warning(f"find_relevant_post error: {e}")
    return None


async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    bot_username = (await context.bot.get_me()).username
    if f"@{bot_username}" not in message.text:
        return
    question = message.text.replace(f"@{bot_username}", "").strip()
    if not question:
        await message.reply_text("â“ Please ask me a question after mentioning me!")
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    posts = fetch_channel_posts()
    channel_context = find_relevant_post(question, posts)

    if channel_context:
        prompt = f"""Relevant channel post:
\"\"\"{channel_context['text']}\"\"\"

User question: {question}"""
        try:
            answer = ask_groq(SYSTEM_PROMPT, prompt)
            answer += f"\n\nðŸ“Œ *Source:* [View channel post]({channel_context['link']})"
            await message.reply_text(answer, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Groq error: {e}")
            await message.reply_text(f"âš ï¸ Error: {str(e)[:200]}")
    else:
        try:
            answer = ask_groq(SYSTEM_PROMPT, question)
            await message.reply_text(answer)
        except Exception as e:
            logging.error(f"Groq error: {e}")
            await message.reply_text(f"âš ï¸ Error: {str(e)[:200]}")


def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    logging.info(f"Health server started on port {PORT}")
    clear_conflict()
    time.sleep(3)
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mention))
    print("âœ… Bot is running with Groq + Channel Search!")
    app.run_polling(allowed_updates=["message", "channel_post"], drop_pending_updates=True)


if __name__ == "__main__":
    main()
