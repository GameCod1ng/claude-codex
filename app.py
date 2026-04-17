import os
import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

st.set_page_config(page_title="뉴스 요약 → 텔레그램", page_icon="📰")
st.title("📰 뉴스 요약 → 텔레그램 전송")


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
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LsaSummarizer()
    result = summarizer(parser.document, sentences)
    return "\n\n".join(f"{i+1}. {s}" for i, s in enumerate(result))


def send_telegram(message: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    return resp.ok


# ── UI ────────────────────────────────────────────────────────
news_url = st.text_input("뉴스 URL", placeholder="https://www.example.com/news/article")

if st.button("요약 후 텔레그램 전송", type="primary"):
    if not news_url.strip():
        st.warning("URL을 입력해주세요.")
        st.stop()

    with st.spinner("기사 불러오는 중..."):
        try:
            article_text = extract_article(news_url)
        except Exception as e:
            st.error(f"기사를 가져올 수 없습니다: {e}")
            st.stop()

    if len(article_text) < 100:
        st.error("기사 내용이 너무 짧습니다. URL을 확인해주세요.")
        st.stop()

    with st.spinner("요약 중..."):
        try:
            summary = summarize(article_text)
        except Exception as e:
            st.error(f"요약 실패: {e}")
            st.stop()

    if not summary.strip():
        st.error("요약 결과가 없습니다. 다른 URL을 시도해주세요.")
        st.stop()

    # 화면에 표시
    st.subheader("📋 요약 결과")
    st.info(summary)

    # 텔레그램 전송
    message = f"📰 뉴스 요약\n\n{summary}\n\n🔗 {news_url}"
    if send_telegram(message):
        st.success("텔레그램으로 전송 완료!")
    else:
        st.error("텔레그램 전송에 실패했습니다.")
