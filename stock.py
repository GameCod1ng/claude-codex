import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

st.set_page_config(page_title="주가 차트", page_icon="📈", layout="wide")
st.title("📈 주가 차트")

# ── 기간 설정 ─────────────────────────────────────────────────
PERIODS = {
    "1일": ("1d", "5m"),
    "1주": ("5d", "30m"),
    "1개월": ("1mo", "1d"),
    "3개월": ("3mo", "1d"),
    "6개월": ("6mo", "1d"),
    "1년": ("1y", "1d"),
}

# ── 인기 종목 단축키 ──────────────────────────────────────────
POPULAR = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "NAVER": "035420.KS",
    "카카오": "035720.KS",
    "애플": "AAPL",
    "엔비디아": "NVDA",
    "테슬라": "TSLA",
    "마이크로소프트": "MSFT",
}

# ── 사이드바 ──────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 종목 검색")
    ticker_input = st.text_input(
        "티커 입력",
        placeholder="005930.KS / AAPL",
        help="한국: 종목코드.KS (예: 005930.KS)\n미국: 티커 (예: AAPL)",
    )
    st.markdown("**인기 종목**")
    for name, ticker in POPULAR.items():
        if st.button(name, use_container_width=True):
            ticker_input = ticker
            st.session_state["ticker"] = ticker

    st.markdown("---")
    show_ma = st.checkbox("이동평균선", value=True)
    if show_ma:
        ma5  = st.checkbox("MA5",  value=True)
        ma20 = st.checkbox("MA20", value=True)
        ma60 = st.checkbox("MA60", value=True)

# ── 티커 결정 ─────────────────────────────────────────────────
ticker = ticker_input or st.session_state.get("ticker", "")

if not ticker:
    st.info("왼쪽에서 종목을 선택하거나 티커를 입력하세요.")
    st.stop()

# ── 기간 선택 버튼 ────────────────────────────────────────────
selected = st.radio("기간", list(PERIODS.keys()), index=2, horizontal=True)
period, interval = PERIODS[selected]

# ── 데이터 로드 ───────────────────────────────────────────────
@st.cache_data(ttl=300)
def load(ticker, period, interval):
    tk = yf.Ticker(ticker)
    df = tk.history(period=period, interval=interval)
    info = tk.fast_info
    return df, info

with st.spinner("데이터 불러오는 중..."):
    try:
        df, info = load(ticker, period, interval)
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

if df.empty:
    st.error("데이터가 없습니다. 티커를 확인해주세요.")
    st.stop()

# ── 현재가 지표 ───────────────────────────────────────────────
cur  = df["Close"].iloc[-1]
prev = df["Close"].iloc[-2] if len(df) > 1 else cur
chg  = cur - prev
pct  = chg / prev * 100

col1, col2, col3, col4 = st.columns(4)
col1.metric("현재가", f"{cur:,.0f}", f"{chg:+,.0f} ({pct:+.2f}%)")
col2.metric("고가", f"{df['High'].max():,.0f}")
col3.metric("저가", f"{df['Low'].min():,.0f}")
col4.metric("거래량", f"{df['Volume'].iloc[-1]:,.0f}")

# ── 차트 ─────────────────────────────────────────────────────
fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    row_heights=[0.75, 0.25],
    vertical_spacing=0.03,
)

# 캔들차트
fig.add_trace(
    go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        name="주가",
        increasing_line_color="#FF4B4B",
        decreasing_line_color="#4B9DFF",
    ),
    row=1, col=1,
)

# 이동평균선
if show_ma:
    colors = {"MA5": "#FFA500", "MA20": "#00CED1", "MA60": "#DA70D6"}
    for label, n, enabled in [("MA5", 5, ma5), ("MA20", 20, ma20), ("MA60", 60, ma60)]:
        if enabled and len(df) >= n:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["Close"].rolling(n).mean(),
                    name=label,
                    line=dict(color=colors[label], width=1.5),
                ),
                row=1, col=1,
            )

# 거래량
colors_vol = ["#FF4B4B" if c >= o else "#4B9DFF"
              for c, o in zip(df["Close"], df["Open"])]
fig.add_trace(
    go.Bar(x=df.index, y=df["Volume"], name="거래량",
           marker_color=colors_vol, showlegend=False),
    row=2, col=1,
)

fig.update_layout(
    height=650,
    xaxis_rangeslider_visible=False,
    plot_bgcolor="#0E1117",
    paper_bgcolor="#0E1117",
    font_color="#FAFAFA",
    legend=dict(orientation="h", y=1.02),
    margin=dict(l=10, r=10, t=30, b=10),
)
fig.update_xaxes(gridcolor="#1E2530", showgrid=True)
fig.update_yaxes(gridcolor="#1E2530", showgrid=True)

st.plotly_chart(fig, use_container_width=True)
st.caption("※ 데이터는 Yahoo Finance 기준, 최대 15분 지연될 수 있습니다.")
