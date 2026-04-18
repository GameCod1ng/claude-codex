import os
import sqlite3
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import requests

load_dotenv()
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

st.set_page_config(page_title="주가 차트", page_icon="📈", layout="wide")
st.title("📈 주가 차트")

# ── DB ────────────────────────────────────────────────────────
ALERT_DB = Path(__file__).parent / "alerts.db"

def init_alert_db():
    with sqlite3.connect(ALERT_DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS alerts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker    TEXT,
            name      TEXT,
            cond      TEXT,
            value     REAL,
            triggered INTEGER DEFAULT 0
        )""")

def get_alerts():
    with sqlite3.connect(ALERT_DB) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM alerts ORDER BY id DESC")]

def add_alert(ticker, name, cond, value):
    with sqlite3.connect(ALERT_DB) as c:
        c.execute("INSERT INTO alerts VALUES (NULL,?,?,?,?,0)", (ticker, name, cond, value))

def delete_alert(aid):
    with sqlite3.connect(ALERT_DB) as c:
        c.execute("DELETE FROM alerts WHERE id=?", (aid,))

def mark_triggered(aid):
    with sqlite3.connect(ALERT_DB) as c:
        c.execute("UPDATE alerts SET triggered=1 WHERE id=?", (aid,))

def reset_triggered(aid):
    with sqlite3.connect(ALERT_DB) as c:
        c.execute("UPDATE alerts SET triggered=0 WHERE id=?", (aid,))

init_alert_db()

# ── 텔레그램 전송 ─────────────────────────────────────────────
def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
        timeout=5,
    )

# ── 알림 체크 (APScheduler) ───────────────────────────────────
def check_alerts():
    alerts = get_alerts()
    for a in alerts:
        if a["triggered"]:
            continue
        try:
            price = yf.Ticker(a["ticker"]).fast_info["lastPrice"]
        except Exception:
            continue
        hit = (a["cond"] == "이상" and price >= a["value"]) or \
              (a["cond"] == "이하" and price <= a["value"]) or \
              (a["cond"] == "등락률+" and
               (price - yf.download(a["ticker"], period="2d", interval="1d", progress=False)["Close"].iloc[-2]) /
               yf.download(a["ticker"], period="2d", interval="1d", progress=False)["Close"].iloc[-2] * 100 >= a["value"]) or \
              (a["cond"] == "등락률-" and
               (price - yf.download(a["ticker"], period="2d", interval="1d", progress=False)["Close"].iloc[-2]) /
               yf.download(a["ticker"], period="2d", interval="1d", progress=False)["Close"].iloc[-2] * 100 <= -a["value"])
        if hit:
            cond_str = {"이상": f"≥ {a['value']:,.0f}", "이하": f"≤ {a['value']:,.0f}",
                        "등락률+": f"+{a['value']}% 이상", "등락률-": f"-{a['value']}% 이상"}[a["cond"]]
            send_telegram(
                f"📈 주가 알림\n\n종목: {a['name']} ({a['ticker']})\n"
                f"현재가: {price:,.0f}\n조건: {cond_str}\n\n✅ 조건 도달!"
            )
            mark_triggered(a["id"])

@st.cache_resource
def get_scheduler():
    s = BackgroundScheduler()
    s.add_job(check_alerts, "interval", minutes=3)
    s.start()
    return s

get_scheduler()

# ── 상수 ─────────────────────────────────────────────────────
PERIODS = {
    "1일": ("1d", "5m"),
    "1주": ("5d", "30m"),
    "1개월": ("1mo", "1d"),
    "3개월": ("3mo", "1d"),
    "6개월": ("6mo", "1d"),
    "1년": ("1y", "1d"),
}
POPULAR = {
    "삼성전자": "005930.KS", "SK하이닉스": "000660.KS",
    "NAVER": "035420.KS",   "카카오": "035720.KS",
    "애플": "AAPL",          "엔비디아": "NVDA",
    "테슬라": "TSLA",         "마이크로소프트": "MSFT",
}

# ── 사이드바 ──────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 종목 검색")
    ticker_input = st.text_input("티커 입력", placeholder="005930.KS / AAPL")
    st.markdown("**인기 종목**")
    for name, t in POPULAR.items():
        if st.button(name, use_container_width=True):
            st.session_state["ticker"] = t
    st.markdown("---")
    show_ma = st.checkbox("이동평균선", value=True)
    if show_ma:
        ma5  = st.checkbox("MA5",  value=True)
        ma20 = st.checkbox("MA20", value=True)
        ma60 = st.checkbox("MA60", value=True)
    else:
        ma5 = ma20 = ma60 = False

ticker = ticker_input or st.session_state.get("ticker", "")

# ── 탭 ───────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📊 차트", "🔔 가격 알림"])

# ── 탭1: 차트 ────────────────────────────────────────────────
with tab1:
    if not ticker:
        st.info("왼쪽에서 종목을 선택하거나 티커를 입력하세요.")
        st.stop()

    selected = st.radio("기간", list(PERIODS.keys()), index=2, horizontal=True)
    period, interval = PERIODS[selected]

    @st.cache_data(ttl=300)
    def load(ticker, period, interval):
        tk = yf.Ticker(ticker)
        return tk.history(period=period, interval=interval), tk.fast_info

    with st.spinner("데이터 불러오는 중..."):
        try:
            df, info = load(ticker, period, interval)
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")
            st.stop()

    if df.empty:
        st.error("데이터가 없습니다. 티커를 확인해주세요.")
        st.stop()

    cur  = df["Close"].iloc[-1]
    prev = df["Close"].iloc[-2] if len(df) > 1 else cur
    chg  = cur - prev
    pct  = chg / prev * 100

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("현재가", f"{cur:,.0f}", f"{chg:+,.0f} ({pct:+.2f}%)")
    col2.metric("고가",   f"{df['High'].max():,.0f}")
    col3.metric("저가",   f"{df['Low'].min():,.0f}")
    col4.metric("거래량", f"{df['Volume'].iloc[-1]:,.0f}")

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="주가",
        increasing_line_color="#FF4B4B", decreasing_line_color="#4B9DFF",
    ), row=1, col=1)

    if show_ma:
        for label, n, on in [("MA5",5,ma5),("MA20",20,ma20),("MA60",60,ma60)]:
            if on and len(df) >= n:
                fig.add_trace(go.Scatter(
                    x=df.index, y=df["Close"].rolling(n).mean(), name=label,
                    line=dict(color={"MA5":"#FFA500","MA20":"#00CED1","MA60":"#DA70D6"}[label], width=1.5),
                ), row=1, col=1)

    vol_colors = ["#FF4B4B" if c >= o else "#4B9DFF"
                  for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=vol_colors,
                         name="거래량", showlegend=False), row=2, col=1)

    fig.update_layout(height=650, xaxis_rangeslider_visible=False,
                      plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
                      font_color="#FAFAFA", legend=dict(orientation="h", y=1.02),
                      margin=dict(l=10, r=10, t=30, b=10))
    fig.update_xaxes(gridcolor="#1E2530")
    fig.update_yaxes(gridcolor="#1E2530")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("※ Yahoo Finance 기준, 최대 15분 지연")

# ── 탭2: 가격 알림 ────────────────────────────────────────────
with tab2:
    st.subheader("🔔 텔레그램 가격 알림 설정")
    st.info("조건 충족 시 텔레그램으로 알림을 보냅니다. 서버가 실행 중인 동안 3분마다 체크합니다.")

    # 알림 추가
    with st.form("alert_form"):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
        a_name   = c1.text_input("종목명", placeholder="삼성전자")
        a_ticker = c2.text_input("티커",   placeholder="005930.KS")
        a_cond   = c3.selectbox("조건", ["이상", "이하", "등락률+", "등락률-"])
        a_value  = c4.number_input(
            "기준값 (가격 또는 %)",
            min_value=0.0, value=0.0, step=100.0,
        )
        submitted = st.form_submit_button("➕ 알림 추가", use_container_width=True)
        if submitted:
            if a_ticker and a_value > 0:
                add_alert(a_ticker, a_name or a_ticker, a_cond, a_value)
                st.success("알림이 추가됐습니다!")
                st.rerun()
            else:
                st.warning("티커와 기준값을 입력해주세요.")

    st.markdown("---")
    st.subheader("📋 알림 목록")

    alerts = get_alerts()
    if not alerts:
        st.info("등록된 알림이 없습니다.")
    else:
        for a in alerts:
            cond_label = {"이상": f"≥ {a['value']:,.0f}",
                          "이하": f"≤ {a['value']:,.0f}",
                          "등락률+": f"+{a['value']}% 이상",
                          "등락률-": f"-{a['value']}% 이상"}[a["cond"]]
            status = "✅ 발송됨" if a["triggered"] else "⏳ 대기중"
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            col1.write(f"**{a['name']}** `{a['ticker']}`")
            col2.write(cond_label)
            col3.write(status)
            with col4:
                bcol1, bcol2 = st.columns(2)
                if a["triggered"]:
                    if bcol1.button("↺", key=f"reset_{a['id']}", help="재활성화"):
                        reset_triggered(a["id"])
                        st.rerun()
                if bcol2.button("🗑", key=f"del_{a['id']}", help="삭제"):
                    delete_alert(a["id"])
                    st.rerun()
