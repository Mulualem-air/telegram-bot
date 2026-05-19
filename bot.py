import os
import logging
import requests
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ðŸ”§ CONFIGURATION
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TELEGRAM_BOT_TOKEN = "8967105953:AAEIR0RHCrxlkc_u0SVMaoIaKvLa9z0EFt8"
GROQ_API_KEY       = "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"
CHANNEL_USERNAME   = "@mullerapp"
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

logging.basicConfig(level=logging.INFO)
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are a helpful assistant in a Telegram group.
- Answer ONLY the question asked â€” keep it brief and clear (2â€“4 sentences max).
- Detect the user's language automatically and reply in the SAME language (Amharic or English).
- If context from a channel post is provided, use it to answer accurately.
- Never make up information. If unsure, say so honestly.
- Do not add unnecessary greetings or filler words."""


def ask_groq(prompt: str) -> str:
    """Send prompt to Groq and get response."""
    response = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        max_tokens=300
    )
    return response.choices[0].message.content.strip()


def fetch_channel_posts() -> list:
    """Fetch recent posts from channel using Telegram Bot API."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?limit=100&allowed_updates=[\"channel_post\"]"
        response = requests.get(url, timeout=10)
        data = response.json()
        posts = []
        if data.get("ok"):
            for update in data.get("result", []):
                msg = update.get("channel_post")
                if msg and msg.get("text"):
                    chat = msg.get("chat", {})
                    username = chat.get("username", "")
                    if username.lower() == CHANNEL_USERNAME.lstrip("@").lower():
                        posts.append({
                            "text": msg["text"][:500],
                            "message_id": msg["message_id"]
                        })
        return posts
    except Exception as e:
        logging.warning(f"fetch_channel_posts error: {e}")
        return []


def find_relevant_post(question: str, posts: list) -> dict | None:
    """Use Groq to find the most relevant channel post."""
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
        result = ask_groq(prompt)
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
    """Handle messages where the bot is mentioned."""
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

    # Search channel for relevant post
    posts = fetch_channel_posts()
    channel_context = find_relevant_post(question, posts)

    # Build prompt
    if channel_context:
        prompt = f"""Relevant channel post:
\"\"\"{channel_context['text']}\"\"\"

User question: {question}"""
    else:
        prompt = question

    # Generate answer
    try:
        answer = ask_groq(prompt)
    except Exception as e:
        logging.error(f"Groq error: {e}")
        await message.reply_text(f"âš ï¸ Error: {str(e)[:200]}")
        return

    # Reply
    if channel_context:
        answer += f"\n\nðŸ“Œ *Source:* [View channel post]({channel_context['link']})"
        await message.reply_text(answer, parse_mode="Markdown")
    else:
        await message.reply_text(answer)


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_mention))
    print("âœ… Bot is running with Groq!")
    app.run_polling()


if __name__ == "__main__":
    main()
