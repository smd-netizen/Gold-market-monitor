import os
import time
from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf
import requests
import feedparser


st.set_page_config(
    page_title="Gold Market Monitor",
    page_icon="🥇",
    layout="wide"
)


# ============================================================
# MARKET DATA
# ============================================================

def yf_quote(ticker):
    """Get a quote from Yahoo Finance."""
    try:
        hist = yf.Ticker(ticker).history(
            period="2d",
            interval="1m",
            auto_adjust=False
        )

        if hist.empty or "Close" not in hist.columns:
            return {"error": "No quote data returned."}

        close = pd.to_numeric(
            hist["Close"],
            errors="coerce"
        ).dropna()

        if close.empty:
            return {"error": "No valid price data returned."}

        price = float(close.iloc[-1])
        previous = float(close.iloc[0])

        if previous:
            pct = ((price / previous) - 1) * 100
        else:
            pct = 0.0

        return {
            "price": price,
            "change": price - previous,
            "pct": pct
        }

    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 10-YEAR TREASURY
# ============================================================

def fred_series(series_id):
    """Get a series from the Federal Reserve FRED database."""
    try:
        url = (
            "https://fred.stlouisfed.org/graph/"
            f"fredgraph.csv?id={series_id}"
        )

        df = pd.read_csv(url)

        df[series_id] = pd.to_numeric(
            df[series_id],
            errors="coerce"
        )

        df = df.dropna(subset=[series_id])

        if df.empty:
            return {"error": "No FRED data returned."}

        return {
            "value": float(df.iloc[-1][series_id]),
            "date": df.iloc[-1]["DATE"]
        }

    except Exception as e:
        return {"error": str(e)}


# ============================================================
# ECONOMIC CALENDAR
# ============================================================

def trading_economics_calendar():
    """
    Optional Trading Economics calendar.

    If TE_API_KEY is not configured, the app simply tells the
    user that the calendar isn't configured yet.
    """

    key = os.getenv("TE_API_KEY", "")

    if not key:
        return pd.DataFrame()

    try:
        url = (
            "https://api.tradingeconomics.com/"
            "calendar/country/United%20States/importance/3"
        )

        response = requests.get(
            url,
            params={
                "c": key,
                "d1": datetime.now().date(),
                "d2": datetime.now().date()
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()
        df = pd.DataFrame(data)

        if df.empty:
            return df

        wanted_columns = [
            "Date",
            "Event",
            "Actual",
            "Forecast",
            "Previous",
            "Importance",
            "Country"
        ]

        columns = [
            column
            for column in wanted_columns
            if column in df.columns
        ]

        return df[columns]

    except Exception:
        return pd.DataFrame()


# ============================================================
# NEWS
# ============================================================

def news():
    """
    Gets recent gold/macro headlines.

    If NEWSAPI_KEY is available, NewsAPI is used.
    Otherwise Google News RSS is used as a free fallback.
    """

    try:
        key = os.getenv("NEWSAPI_KEY", "")

        if key:
            response = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": (
                        "gold futures OR gold price OR "
                        "Federal Reserve OR US dollar OR "
                        "Treasury yields"
                    ),
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 15,
                    "apiKey": key
                },
                timeout=10
            )

            articles = response.json().get(
                "articles",
                []
            )

            return [
                (
                    article.get("publishedAt", ""),
                    article.get("title", ""),
                    article.get("url", "")
                )
                for article in articles
            ]

        # Free fallback
        feed = feedparser.parse(
            "https://news.google.com/rss/search?"
            "q=gold%20futures%20OR%20Federal%20Reserve"
            "%20OR%20US%20dollar%20Treasury"
            "&hl=en-US&gl=US&ceid=US:en"
        )

        return [
            (
                entry.get("published", ""),
                entry.get("title", ""),
                entry.get("link", "")
            )
            for entry in feed.entries[:15]
        ]

    except Exception:
        return []


# ============================================================
# GOLD MARKET SCORING
# ============================================================

def score(gold, dxy, treasury):
    """
    Very simple and transparent first-pass scoring system.

    This is NOT intended to predict the market yet.
    It simply identifies whether the available data is
    leaning bullish, bearish, or neutral.
    """

    score_value = 0
    reasons = []

    # --------------------------------------------------------
    # GOLD
    # --------------------------------------------------------

    # IMPORTANT FIX:
    # We verify that "pct" exists before trying to use it.
    if gold and "pct" in gold:

        gold_pct = gold["pct"]

        if gold_pct > 0.30:
            score_value += 2
            reasons.append(
                "Gold is rising strongly."
            )

        elif gold_pct > 0.05:
            score_value += 1
            reasons.append(
                "Gold is rising."
            )

        elif gold_pct < -0.30:
            score_value -= 2
            reasons.append(
                "Gold is falling strongly."
            )

        elif gold_pct < -0.05:
            score_value -= 1
            reasons.append(
                "Gold is falling."
            )

    else:

        reasons.append(
            "Gold quote unavailable from the current data source."
        )

    # --------------------------------------------------------
    # DXY
    # --------------------------------------------------------

    # IMPORTANT FIX:
    # Same protection for DXY.
    if dxy and "pct" in dxy:

        dxy_pct = dxy["pct"]

        if dxy_pct < -0.15:
            score_value += 2
            reasons.append(
                "DXY is falling."
            )

        elif dxy_pct < -0.03:
            score_value += 1
            reasons.append(
                "DXY is slightly lower."
            )

        elif dxy_pct > 0.15:
            score_value -= 2
            reasons.append(
                "DXY is rising."
            )

        elif dxy_pct > 0.03:
            score_value -= 1
            reasons.append(
                "DXY is slightly higher."
            )

    else:

        reasons.append(
            "DXY quote unavailable from the current data source."
        )

    # --------------------------------------------------------
    # TREASURY
    # --------------------------------------------------------

    if not treasury or "value" not in treasury:

        reasons.append(
            "10-year Treasury data unavailable."
        )

    else:

        reasons.append(
            "10-year Treasury yield is available for context."
        )

    # --------------------------------------------------------
    # FINAL BIAS
    # --------------------------------------------------------

    if score_value >= 3:

        bias = "BULLISH"

        confidence = min(
            10,
            6 + score_value - 3
        )

    elif score_value <= -3:

        bias = "BEARISH"

        confidence = min(
            10,
            6 + abs(score_value) - 3
        )

    else:

        bias = "NEUTRAL / WAIT"

        confidence = 5

    return bias, confidence, reasons


# ============================================================
# DASHBOARD
# ============================================================

st.title(
    "🥇 Gold Market Monitor — MVP"
)

st.caption(
    "Automated market-monitoring dashboard. "
    "It does NOT place trades."
)


# ============================================================
# SETTINGS
# ============================================================

refresh = st.sidebar.number_input(
    "Refresh interval (seconds)",
    min_value=15,
    max_value=900,
    value=60,
    step=15
)

st.sidebar.info(
    "Version 1 uses public/indicative data. "
    "Do not use this as the execution price for "
    "leveraged futures."
)


# ============================================================
# GET DATA
# ============================================================

gold = yf_quote("GC=F")

dxy = yf_quote("DX-Y.NYB")

treasury = fred_series("DGS10")

events = trading_economics_calendar()

bias, confidence, reasons = score(
    gold,
    dxy,
    treasury
)


# ============================================================
# TOP METRICS
# ============================================================

column1, column2, column3, column4 = st.columns(4)


# GOLD

if gold and "price" in gold:

    column1.metric(
        "Gold futures (GC=F)",
        f"${gold['price']:,.2f}",
        f"{gold['pct']:+.2f}%"
    )

else:

    column1.metric(
        "Gold futures (GC=F)",
        "Unavailable"
    )


# DXY

if dxy and "price" in dxy:

    column2.metric(
        "DXY",
        f"{dxy['price']:.3f}",
        f"{dxy['pct']:+.2f}%"
    )

else:

    column2.metric(
        "DXY",
        "Unavailable"
    )


# 10 YEAR

if treasury and "value" in treasury:

    column3.metric(
        "10Y Treasury",
        f"{treasury['value']:.2f}%"
    )

else:

    column3.metric(
        "10Y Treasury",
        "Unavailable"
    )


# BIAS

column4.metric(
    "Monitor bias",
    bias,
    f"Confidence {confidence}/10"
)


# ============================================================
# ANALYSIS
# ============================================================

st.subheader(
    "What the monitor sees"
)

for reason in reasons:

    st.write(
        "• " + reason
    )


st.warning(
    "This is an educational monitoring heuristic, "
    "not financial advice and not a proven trading strategy."
)


# ============================================================
# ECONOMIC CALENDAR
# ============================================================

st.subheader(
    "Today's high-importance economic events"
)

if events.empty:

    st.info(
        "No Trading Economics calendar data is "
        "configured yet. That's normal for the "
        "first launch."
    )

else:

    st.dataframe(
        events,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# NEWS
# ============================================================

st.subheader(
    "Recent gold / macro headlines"
)

articles = news()

if articles:

    for published, title, link in articles[:10]:

        st.markdown(
            f"- **{title}**  \n"
            f"{published}  \n"
            f"{link}"
        )

else:

    st.info(
        "No headlines returned."
    )


# ============================================================
# REFRESH
# ============================================================

st.caption(
    "Last refresh: "
    + datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )
)

time.sleep(refresh)

st.rerun()
