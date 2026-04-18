import os
import json
import requests
import streamlit as st
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer
import yake
from apscheduler.schedulers.background import BackgroundScheduler
import db

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNELS_FILE = Path(__file__).parent / "channels.json"

# ── 초기화 ────────────────────────────────────────────────────
db.init()

if not CHANNELS_FILE.exists():
    CHANNELS_FILE.write_text(
        json.dumps([{"name": "개인 채팅", "chat_id": os.getenv("TELEGRAM_CHAT_ID", "")}], ensure_ascii=False),
        encoding="utf-8",
    )


def load_channels():
    return json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))


def save_channels(channels):
    CHANNELS_FILE.write_text(json.dumps(channels, ensure_ascii=False, indent=2), encoding="utf-8")


# ── APScheduler (예약 전송) ───────────────────────────────────
@st.cache_resource
def get_scheduler():
    def check_and_send():
        for item in db.get_pending():
            ok = _send_telegram(item["message"], item["channel_id"])
            if ok:
                db.mark_sent(item["id"])
                db.add_history(item["url"], item["message"], "", item["channel_name"])

    scheduler = BackgroundScheduler()
    scheduler.add_job(check_and_send, "interval", seconds=30)
    scheduler.start()
    return scheduler

get_scheduler()


# ── 핵심 함수 ─────────────────────────────────────────────────
def extract_article(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    node = soup.find("article") or soup.find("main")
    text = node.get_text(" ", strip=True) if node else soup.get_text(" ", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return " ".join(lines)


def summarize(text: str, n: int = 3) -> str:
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    result = LexRankSummarizer()(parser.document, n)
    return "\n".join(f"{i+1}. {s}" for i, s in enumerate(result))


def extract_keywords(text: str, n: int = 5) -> list[str]:
    kw = yake.KeywordExtractor(lan="en", n=2, dedupLim=0.7, top=n)
    return [k for k, _ in kw.extract_keywords(text[:3000])]


def build_message(url: str, summary: str, keywords: list, fmt: str) -> str:
    tags = " ".join(f"#{k.replace(' ', '_')}" for k in keywords)
    if fmt == "마크다운":
        return f"📰 *뉴스 요약*\n\n{summary}\n\n🏷 {tags}\n🔗 {url}"
    return f"📰 뉴스 요약\n\n{summary}\n\n🏷 {tags}\n🔗 {url}"


def _send_telegram(message: str, chat_id: str, fmt: str = "기본") -> bool:
    parse_mode = "Markdown" if fmt == "마크다운" else None
    payload = {"chat_id": chat_id, "text": message}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload)
    return r.ok


# ── Streamlit UI ──────────────────────────────────────────────
st.set_page_config(page_title="뉴스 요약 → 텔레그램", page_icon="📰", layout="wide")
st.title("📰 뉴스 요약 → 텔레그램 전송")

# ── 사이드바: 채널 관리 ───────────────────────────────────────
with st.sidebar:
    st.header("📡 채널 관리")
    channels = load_channels()
    ch_names = [c["name"] for c in channels]
    selected_ch_name = st.selectbox("전송 채널", ch_names)
    selected_ch = next(c for c in channels if c["name"] == selected_ch_name)

    with st.expander("채널 추가/삭제"):
        new_name = st.text_input("채널 이름")
        new_id = st.text_input("Chat ID")
        if st.button("추가"):
            if new_name and new_id:
                channels.append({"name": new_name, "chat_id": new_id})
                save_channels(channels)
                st.success("추가됨")
                st.rerun()
        del_target = st.selectbox("삭제할 채널", [""] + ch_names)
        if st.button("삭제") and del_target:
            channels = [c for c in channels if c["name"] != del_target]
            save_channels(channels)
            st.success("삭제됨")
            st.rerun()

    st.markdown("---")
    st.header("⚙️ 설정")
    n_sentences = st.slider("요약 문장 수", 1, 5, 3)
    msg_format = st.radio("메시지 포맷", ["기본", "마크다운"])

# ── 탭 ───────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📨 요약 & 전송", "📋 전송 이력", "⏰ 예약 목록"])

# ── 탭1: 요약 & 전송 ─────────────────────────────────────────
with tab1:
    raw_input = st.text_area(
        "뉴스 URL (여러 개는 줄바꿈으로 구분)",
        placeholder="https://...\nhttps://...",
        height=120,
    )
    urls = [u.strip() for u in raw_input.splitlines() if u.strip().startswith("http")]

    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        do_summarize = st.button("요약하기", type="primary")

    if do_summarize and urls:
        results = []
        for url in urls:
            if db.is_duplicate(url):
                st.warning(f"이미 전송된 URL입니다: {url}")
                continue
            with st.spinner(f"처리 중... {url[:50]}"):
                try:
                    article = extract_article(url)
                    if len(article) < 100:
                        st.error(f"내용 부족: {url}")
                        continue
                    summary = summarize(article, n_sentences)
                    keywords = extract_keywords(article)
                    results.append({
                        "url": url,
                        "article": article,
                        "summary": summary,
                        "keywords": keywords,
                    })
                except Exception as e:
                    st.error(f"오류 ({url[:40]}): {e}")
        st.session_state["results"] = results

    if not urls and do_summarize:
        st.warning("URL을 입력해주세요.")

    # 결과 표시
    for i, item in enumerate(st.session_state.get("results", [])):
        st.markdown(f"---")
        url = item["url"]
        summary = item["summary"]
        keywords = item["keywords"]
        article = item["article"]
        message = build_message(url, summary, keywords, msg_format)

        # 통계
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("원문 글자 수", f"{len(article):,}")
        col_b.metric("요약 글자 수", f"{len(summary):,}")
        col_c.metric("압축률", f"{len(summary)/max(len(article),1)*100:.1f}%")

        # 키워드
        st.markdown("**🏷 키워드:** " + "  ".join(f"`{k}`" for k in keywords))

        # 원문 미리보기
        with st.expander("원문 미리보기"):
            st.write(article[:2000] + ("..." if len(article) > 2000 else ""))

        # 요약 결과
        st.subheader("📋 요약")
        st.info(summary)

        # 텔레그램 메시지 미리보기
        with st.expander("📱 텔레그램 메시지 미리보기"):
            st.code(message, language=None)

        # 전송 버튼
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("📤 즉시 전송", key=f"send_{i}"):
                if _send_telegram(message, selected_ch["chat_id"], msg_format):
                    db.add_history(url, summary, ", ".join(keywords), selected_ch["name"])
                    st.success(f"✅ [{selected_ch['name']}] 전송 완료!")
                    st.session_state["results"].pop(i)
                    st.rerun()
                else:
                    st.error("전송 실패")

        with col2:
            sched_col1, sched_col2 = st.columns(2)
            with sched_col1:
                sched_date = st.date_input("예약 날짜", datetime.now().date(), key=f"date_{i}")
            with sched_col2:
                sched_time = st.time_input("예약 시간",
                    (datetime.now() + timedelta(minutes=5)).time(), key=f"time_{i}")

            if st.button("⏰ 예약 전송", key=f"sched_{i}"):
                send_at = datetime.combine(sched_date, sched_time).strftime("%Y-%m-%d %H:%M")
                db.add_scheduled(url, message, selected_ch["chat_id"], selected_ch["name"], send_at)
                st.success(f"✅ {send_at} 예약 완료!")
                st.session_state["results"].pop(i)
                st.rerun()

# ── 탭2: 전송 이력 ───────────────────────────────────────────
with tab2:
    st.subheader("📋 전송 이력")
    history = db.get_history()
    if not history:
        st.info("전송 이력이 없습니다.")
    else:
        for row in history:
            with st.expander(f"[{row['sent_at']}] {row['url'][:60]}..."):
                st.markdown(f"**채널:** {row['channel']}")
                st.markdown(f"**키워드:** {row['keywords']}")
                st.write(row["summary"])
                col1, col2 = st.columns([1, 5])
                with col1:
                    if st.button("삭제", key=f"del_{row['id']}"):
                        db.delete_history(row["id"])
                        st.rerun()

# ── 탭3: 예약 목록 ───────────────────────────────────────────
with tab3:
    st.subheader("⏰ 예약 목록")
    scheduled = db.get_scheduled()
    if not scheduled:
        st.info("예약된 항목이 없습니다.")
    else:
        for row in scheduled:
            status_icon = {"pending": "⏳", "sent": "✅", "cancelled": "❌"}.get(row["status"], "")
            with st.expander(f"{status_icon} [{row['send_at']}] {row['url'][:50]}..."):
                st.markdown(f"**채널:** {row['channel_name']}  |  **상태:** {row['status']}")
                st.code(row["message"], language=None)
                if row["status"] == "pending":
                    if st.button("취소", key=f"cancel_{row['id']}"):
                        db.cancel_scheduled(row["id"])
                        st.rerun()
