import os
import logging
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def extract_article(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    article = soup.find("article") or soup.find("main")
    text = article.get_text(" ", strip=True) if article else soup.get_text(" ", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return " ".join(lines)


def summarize(text: str, sentences: int = 3) -> str:
    parser = PlaintextParser.from_string(text, Tokenizer("korean"))
    summarizer = LsaSummarizer()
    result = summarizer(parser.document, sentences)
    return " ".join(str(s) for s in result)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "안녕하세요! 📰 뉴스 요약 봇입니다.\n\n"
        "뉴스 기사 URL을 보내주시면 3문장으로 요약해드립니다."
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("올바른 URL을 보내주세요. (http:// 또는 https://로 시작)")
        return

    msg = await update.message.reply_text("📥 기사를 가져오는 중...")

    try:
        article_text = extract_article(url)
    except Exception as e:
        await msg.edit_text(f"❌ 기사를 가져올 수 없습니다.\n{e}")
        return

    if len(article_text) < 100:
        await msg.edit_text("❌ 기사 내용이 너무 짧습니다. URL을 확인해주세요.")
        return

    await msg.edit_text("✍️ 요약 중...")

    try:
        summary = summarize(article_text)
    except Exception as e:
        await msg.edit_text(f"❌ 요약 중 오류가 발생했습니다.\n{e}")
        return

    if not summary.strip():
        await msg.edit_text("❌ 요약 결과가 없습니다. 다른 URL을 시도해주세요.")
        return

    await msg.edit_text(f"📋 *뉴스 요약*\n\n{summary}", parse_mode="Markdown")


def main():
    if not TELEGRAM_TOKEN:
        raise ValueError(".env 파일에 TELEGRAM_TOKEN을 설정해주세요.")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    logger.info("봇 시작됨")
    app.run_polling()


if __name__ == "__main__":
    main()
