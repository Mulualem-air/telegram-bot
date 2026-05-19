import logging
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ─────────────────────────────────────────────
# 🔧 CONFIGURATION
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8967105953:AAEIR0RHCrxlkc_u0SVMaoIaKvLa9z0EFt8"
GEMINI_API_KEY     = "AIzaSyAcuHgNdJ4_y0bAIUnuQRwzlTSvgTldRT8"
CHANNEL_USERNAME   = "@mullerapp"
# ─────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

SYSTEM_PROMPT = """You are a helpful assistant in a Telegram group.
- Answer ONLY the question asked — keep it brief and clear (2–4 sentences max).
- Detect the user's language automatically and reply in the SAME language (Amharic or English).
- If context from a channel post is provided, use it to answer accurately.
- Never make up information. If unsure, say so honestly.
- Do not add unnecessary greetings or filler words."""


async def get_channel_context(context: ContextTypes.DEFAULT_TYPE, question: str) -> dict | None:
    """Fetch recent channel posts and find the most relevant one."""
    try:
        posts = []
        async for message in context.bot.get_chat_history(CHANNEL_USERNAME, limit=50):
            if message.text:
                posts.append({
                    "text": message.text[:500],
                    "message_id": message.message_id
                })

        if not posts:
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
        logging.warning(f"Could not fetch channel context: {e}")

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
        await message.reply_text("❓ Please ask me a question after mentioning me!")
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    # Step 1: Try to find relevant content from channel
    channel_context = await get_channel_context(context, question)

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
        answer = "Sorry, I couldn't generate an answer right now. Please try again."

    # Step 4: Reply with source link if found
    if channel_context:
        answer += f"\n\n📌 *Source:* [View channel post]({channel_context['link']})"
        await message.reply_text(answer, parse_mode="Markdown")
    else:
        await message.reply_text(answer)


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_mention))
    print("✅ Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
