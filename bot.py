import os
import logging
import requests
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ðŸ”§ CONFIGURATION
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8967105953:AAEIR0RHCrxlkc_u0SVMaoIaKvLa9z0EFt8")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "AIzaSyCAdJbq3iVeRsk7PHD5i5IlWxa6lwChIYo")
CHANNEL_USERNAME   = os.environ.get("CHANNEL_USERNAME", "@mullerapp")
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

logging.basicConfig(level=logging.INFO)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

SYSTEM_PROMPT = """You are a helpful assistant in a Telegram group.
- Answer ONLY the question asked â€” keep it brief and clear (2â€“4 sentences max).
- Detect the user's language automatically and reply in the SAME language (Amharic or English).
- If context from a channel post is provided, use it to answer accurately.
- Never make up information. If unsure, say so honestly.
- Do not add unnecessary greetings or filler words."""


def fetch_channel_posts() -> list:
    """Fetch recent posts from the channel using Telegram Bot API directly."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        # Use forwardMessages approach â€” fetch channel posts via bot API
        channel = CHANNEL_USERNAME.lstrip("@")
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChatHistory"

        # Use search messages endpoint instead
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?limit=100"
        response = requests.get(url, timeout=10)
        data = response.json()

        posts = []
        if data.get("ok"):
            for update in data.get("result", []):
                # Check for channel posts
                msg = update.get("channel_post") or update.get("message")
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


async def get_channel_context(question: str) -> dict | None:
    """Find the most relevant channel post for the question."""
    try:
        posts = fetch_channel_posts()

        if not posts:
            logging.info("No channel posts found, using Gemini directly.")
            return None

        posts_text = "\n\n".join(
            [f"[POST {i+1}]: {p['text']}" for i, p in enumerate(posts)]
        )

        relevance_prompt = f"""
Given this question: "{question}"

Here are recent channel posts:
{posts_text}

Which post (if any) is most relevant to answering the question?
Reply with ONLY the post number (e.g. "3") or "NONE" if no post is relevant.
"""
        result = model.generate_content(relevance_prompt)
        response_text = result.text.strip()

        if response_text == "NONE" or not response_text.isdigit():
            return None

        idx = int(response_text) - 1
        if 0 <= idx < len(posts):
            matched = posts[idx]
            channel_name = CHANNEL_USERNAME.lstrip("@")
            link = f"https://t.me/{channel_name}/{matched['message_id']}"
            return {"text": matched["text"], "link": link}

    except Exception as e:
        logging.warning(f"get_channel_context error: {e}")

    return None


async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages where the bot is mentioned."""
    message = update.message
    if not message or not message.text:
        return

    bot_username = (await context.bot.get_me()).username

    # Only respond when bot is @mentioned
    if f"@{bot_username}" not in message.text:
        return

    # Clean the question
    question = message.text.replace(f"@{bot_username}", "").strip()

    if not question:
        await message.reply_text("â“ Please ask me a question after mentioning me!")
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    # Step 1: Try to find relevant content from channel
    channel_context = await get_channel_context(question)

    # Step 2: Build prompt
    if channel_context:
        prompt = f"""{SYSTEM_PROMPT}

Relevant channel post content:
\"\"\"{channel_context['text']}\"\"\"

User question: {question}"""
    else:
        prompt = f"""{SYSTEM_PROMPT}

User question: {question}"""

    # Step 3: Generate answer with Gemini
    try:
        result = model.generate_content(prompt)
        answer = result.text.strip()
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        await message.reply_text(f"âš ï¸ Error: {str(e)[:200]}")
        return

    # Step 4: Reply with source link if found
    if channel_context:
        answer += f"\n\nðŸ“Œ *Source:* [View channel post]({channel_context['link']})"
        await message.reply_text(answer, parse_mode="Markdown")
    else:
        await message.reply_text(answer)


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_mention))
    print("âœ… Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
