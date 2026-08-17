import os, time, math
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import yfinance as yf
import requests
import feedparser

st.set_page_config(page_title="Gold Market Monitor", page_icon="🥇", layout="wide")

GOLD = "GC=F"
DXY = "DX-Y.NYB"

def yf_quote(ticker):
    try:
        x = yf.Ticker(ticker)
        hist = x.history(period="2d", interval="1m", auto_adjust=False)
        if hist.empty:
            return None
        row = hist.dropna(subset=["Close"]).iloc[-1]
        price = float(row["Close"])
        prev = float(hist["Close"].iloc[0])
        return {"price": price, "change": price-prev, "pct": (price/prev-1)*100}
    except Exception as e:
        return {"error": str(e)}

def fred_series(series_id, api_key=None):
    # FRED public CSV endpoint works without a key for this basic series.
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        df = pd.read_csv(url)
        df["DATE"] = pd.to_datetime(df["DATE"])
        df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
        df = df.dropna(subset=[series_id])
        v = float(df.iloc[-1][series_id])
        return {"value": v, "date": df.iloc[-1]["DATE"]}
    except Exception as e:
        return {"error": str(e)}

def trading_economics_calendar():
    key = os.getenv("TE_API_KEY", "")
    if not key:
        return pd.DataFrame()
    # Trading Economics API format; user supplies an API key.
    url = "https://api.tradingeconomics.com/calendar/country/United%20States/importance/3"
    try:
        r = requests.get(url, params={"c": key, "d1": datetime.now().date(), "d2": datetime.now().date()}, timeout=10)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data)
        if df.empty: return df
        cols = [c for c in ["Date","Event","Actual","Forecast","Previous","Importance","Country"] if c in df.columns]
        return df[cols]
    except Exception:
        return pd.DataFrame()

def news():
    # Optional NewsAPI key. Without it, use Google News RSS as a lightweight fallback.
    q = "gold futures OR gold price OR Federal Reserve OR US dollar OR Treasury yields"
    key = os.getenv("NEWSAPI_KEY", "")
    try:
        if key:
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={"q": q, "language":"en", "sortBy":"publishedAt", "pageSize":15, "apiKey":key},
                timeout=10
            )
            arts = r.json().get("articles", [])
            return [(a.get("publishedAt",""), a.get("title",""), a.get("url","")) for a in arts]
        feed = feedparser.parse("https://news.google.com/rss/search?q=gold%20futures%20OR%20Federal%20Reserve%20OR%20US%20dollar%20Treasury&hl=en-US&gl=US&ceid=US:en")
        return [(e.get("published",""), e.get("title",""), e.get("link","")) for e in feed.entries[:15]]
    except Exception:
        return []

def score(gold, dxy, y10, events):
    # Deliberately simple and transparent: this is a monitoring heuristic, NOT a prediction model.
    s = 0
    reasons = []
    if gold:
        if gold["pct"] > 0.30: s += 2; reasons.append("Gold is rising strongly.")
        elif gold["pct"] > 0.05: s += 1; reasons.append("Gold is rising.")
        elif gold["pct"] < -0.30: s -= 2; reasons.append("Gold is falling strongly.")
        elif gold["pct"] < -0.05: s -= 1; reasons.append("Gold is falling.")
    if dxy:
        if dxy["pct"] < -0.15: s += 2; reasons.append("DXY is falling.")
        elif dxy["pct"] < -0.03: s += 1; reasons.append("DXY is slightly lower.")
        elif dxy["pct"] > 0.15: s -= 2; reasons.append("DXY is rising.")
        elif dxy["pct"] > 0.03: s -= 1; reasons.append("DXY is slightly higher.")
    if y10:
        # FRED DGS10 is daily, so this is context, not intraday confirmation.
        pass
    if s >= 3: bias, conf = "BULLISH", min(10, 6 + s-3)
    elif s <= -3: bias, conf = "BEARISH", min(10, 6 + abs(s)-3)
    else: bias, conf = "NEUTRAL / WAIT", 5
    return bias, conf, reasons

st.title("🥇 Gold Market Monitor — MVP")
st.caption("Transparent monitoring dashboard. It does NOT place trades and its first version is intentionally conservative.")

refresh = st.sidebar.number_input("Refresh interval (seconds)", min_value=15, max_value=900, value=60, step=15)
st.sidebar.info("For actual futures execution, connect a broker/exchange real-time feed later. Yahoo Finance is indicative and may be delayed.")

gold = yf_quote(GOLD)
dxy = yf_quote(DXY)
y10 = fred_series("DGS10")
events = trading_economics_calendar()
bias, conf, reasons = score(gold, dxy, y10, events)

c1,c2,c3,c4 = st.columns(4)
if gold and "price" in gold: c1.metric("Gold futures (GC=F)", f"${gold['price']:,.2f}", f"{gold['pct']:+.2f}%")
else: c1.metric("Gold futures", "Unavailable")
if dxy and "price" in dxy: c2.metric("DXY", f"{dxy['price']:.3f}", f"{dxy['pct']:+.2f}%")
else: c2.metric("DXY", "Unavailable")
if y10 and "value" in y10: c3.metric("10Y Treasury", f"{y10['value']:.2f}%")
else: c3.metric("10Y Treasury", "Unavailable")
c4.metric("Monitor bias", bias, f"Confidence {conf}/10")

st.subheader("What the monitor sees")
for r in reasons or ["Not enough aligned movement to justify a directional bias."]:
    st.write("• " + r)

st.warning("This is an educational signal, not financial advice. The score is a transparent heuristic, not a proven predictive model.")

st.subheader("Today's high-importance economic events")
if events.empty:
    st.info("No Trading Economics calendar data loaded. Set TE_API_KEY to enable this section.")
else:
    st.dataframe(events, use_container_width=True, hide_index=True)

st.subheader("Recent gold / macro headlines")
arts = news()
if arts:
    for published, title, link in arts[:10]:
        st.markdown(f"- **{title}**  \n  {published}  \n  {link}")
else:
    st.info("No headlines returned.")

st.caption("Last refresh: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
time.sleep(refresh)
st.rerun()
