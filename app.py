import base64
import io
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import feedparser
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Gold Market Monitor",
    page_icon="🥇",
    layout="wide",
)

ET = ZoneInfo("America/New_York")

GITHUB_REPO = os.getenv(
    "GITHUB_REPO",
    "smd-netizen/gold-market-monitor",
)

HISTORY_PATH = "prediction_history.csv"

# Gold historical data is used for technical analysis.
# Current Gold price still comes from the working collector/Webull feed.
GOLD_YF_SYMBOL = "GC=F"

DXY_YF_SYMBOL = "DX-Y.NYB"


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_float(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def safe_text(value, default="N/A"):
    try:
        if value is None or pd.isna(value):
            return default
    except Exception:
        pass

    text = str(value).strip()

    return text if text else default


def money(value):
    value = safe_float(value)

    if value is None:
        return "Unavailable"

    return f"${value:,.2f}"


def number(value, decimals=2):
    value = safe_float(value)

    if value is None:
        return "Unavailable"

    return f"{value:.{decimals}f}"


def percentage(value):
    value = safe_float(value)

    if value is None:
        return None

    return f"{value:+.2f}%"


# ============================================================
# TIME HELPERS
# ============================================================

def parse_timestamp(value):

    try:

        if value is None or pd.isna(value):
            return None

        timestamp = pd.to_datetime(
            value,
            errors="coerce",
            utc=True,
        )

        if pd.isna(timestamp):
            return None

        return timestamp.to_pydatetime()

    except Exception:
        return None


def format_et(value):

    timestamp = parse_timestamp(value)

    if timestamp is None:
        return "Unknown"

    return timestamp.astimezone(ET).strftime(
        "%Y-%m-%d %I:%M:%S %p ET"
    )


def age_text(value):

    timestamp = parse_timestamp(value)

    if timestamp is None:
        return "Unknown"

    now = datetime.now(timezone.utc)

    seconds = max(
        0,
        (
            now - timestamp
        ).total_seconds(),
    )

    if seconds < 60:
        return f"{int(seconds)} sec ago"

    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"

    if seconds < 86400:
        return f"{seconds / 3600:.1f} hr ago"

    return f"{seconds / 86400:.1f} days ago"


# ============================================================
# GITHUB
# ============================================================

def github_headers():

    token = os.getenv(
        "GITHUB_TOKEN",
        "",
    )

    if not token:
        return None

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_csv_from_github():

    headers = github_headers()

    if not headers:
        return pd.DataFrame()

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/"
        f"{HISTORY_PATH}?ref=main"
    )

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20,
        )

        if response.status_code != 200:
            return pd.DataFrame()

        payload = response.json()

        content = base64.b64decode(
            payload["content"]
        )

        return pd.read_csv(
            io.BytesIO(content)
        )

    except Exception:
        return pd.DataFrame()


# ============================================================
# LOAD MARKET DATA
# ============================================================

history = load_csv_from_github()

if history.empty:

    st.title("🥇 Gold Market Monitor")

    st.error(
        "Market data could not be loaded from GitHub."
    )

    st.info(
        "Run the GitHub market-data collector first."
    )

    st.stop()


# ============================================================
# FIND TIMESTAMP
# ============================================================

timestamp_candidates = [
    "collected_at_utc",
    "timestamp_utc",
    "timestamp",
    "datetime",
    "date",
    "time",
]

timestamp_column = None

for column in timestamp_candidates:

    if column in history.columns:
        timestamp_column = column
        break


if timestamp_column is None:

    st.error(
        "The CSV does not contain a recognizable timestamp."
    )

    st.code(
        ", ".join(
            str(c)
            for c in history.columns
        )
    )

    st.stop()


history["_timestamp"] = pd.to_datetime(
    history[timestamp_column],
    errors="coerce",
    utc=True,
)

history = history.dropna(
    subset=["_timestamp"]
)

if history.empty:

    st.error(
        "The market-data CSV contains no usable records."
    )

    st.stop()


history = history.sort_values(
    "_timestamp"
)

latest = history.iloc[-1]


# ============================================================
# CURRENT MARKET VALUES
# ============================================================

gold_price = safe_float(
    latest.get("gold_price")
)

gold_pct = safe_float(
    latest.get("gold_pct")
)

dxy = safe_float(
    latest.get("dxy_price")
)

dxy_pct = safe_float(
    latest.get("dxy_pct")
)

treasury = safe_float(
    latest.get("treasury_yield")
)

treasury_pct = safe_float(
    latest.get("treasury_pct")
)

gold_timestamp = latest.get(
    "gold_retrieved_at_utc",
    latest.get("collected_at_utc"),
)

dxy_timestamp = latest.get(
    "dxy_retrieved_at_utc",
    latest.get("collected_at_utc"),
)

treasury_timestamp = latest.get(
    "treasury_retrieved_at_utc",
    latest.get("collected_at_utc"),
)


# ============================================================
# HEADER
# ============================================================

st.title(
    "🥇 Gold Market Monitor"
)

st.caption(
    "Market intelligence dashboard. "
    "Predictions are informational and "
    "do not automatically place trades."
)


# ============================================================
# COMPACT MARKET PANEL
# ============================================================

st.subheader("Current Market")


market = st.container()

with market:

    c1, c2, c3 = st.columns(3)

    with c1:

        st.metric(
            "🥇 Gold — October 2026",
            money(gold_price),
            percentage(gold_pct),
        )

        st.caption(
            f"Updated {age_text(gold_timestamp)}"
        )

        st.caption(
            format_et(gold_timestamp)
        )

    with c2:

        st.metric(
            "💵 DXY",
            number(dxy, 3),
            percentage(dxy_pct),
        )

        st.caption(
            f"Updated {age_text(dxy_timestamp)}"
        )

        st.caption(
            format_et(dxy_timestamp)
        )

    with c3:

        st.metric(
            "🇺🇸 10Y Treasury",
            (
                f"{treasury:.2f}%"
                if treasury is not None
                else "Unavailable"
            ),
            percentage(treasury_pct),
        )

        st.caption(
            f"Updated {age_text(treasury_timestamp)}"
        )

        st.caption(
            format_et(treasury_timestamp)
        )


# ============================================================
# DATA QUALITY
# ============================================================

quality_errors = []

if gold_price is None:
    quality_errors.append("Gold price unavailable")

if gold_pct is None:
    quality_errors.append("Gold percentage unavailable")

if dxy is None:
    quality_errors.append("DXY unavailable")

if dxy is not None and not 80 <= dxy <= 120:
    quality_errors.append("DXY failed sanity check")

if treasury is None:
    quality_errors.append("10Y Treasury unavailable")

if treasury is not None and not 0 <= treasury <= 15:
    quality_errors.append(
        "10Y Treasury failed sanity check"
    )


if quality_errors:

    st.warning(
        "🟡 Data quality warning: "
        + "; ".join(quality_errors)
    )

else:

    st.success(
        "🟢 DATA QUALITY: PASS"
    )


# ============================================================
# GOLD CONTRACT
# ============================================================

with st.expander(
    "🥇 Gold Contract / Data Source",
    expanded=False,
):

    contract = safe_text(
        latest.get("contract"),
        "1OZV6.CMX",
    )

    contract_name = safe_text(
        latest.get("contract_name"),
        "1-Ounce Gold — October 2026",
    )

    gold_source = safe_text(
        latest.get("gold_source"),
        "Webull public page",
    )

    a, b, c = st.columns(3)

    a.write(
        f"**Contract:** {contract}"
    )

    b.write(
        f"**Contract Name:** {contract_name}"
    )

    c.write(
        "**Market:** COMEX"
    )

    st.write(
        f"**Gold Source:** {gold_source}"
    )


# ============================================================
# TECHNICAL DATA
# ============================================================

@st.cache_data(ttl=300)
def get_gold_history():

    try:

        data = yf.download(
            GOLD_YF_SYMBOL,
            period="5d",
            interval="5m",
            progress=False,
            auto_adjust=False,
        )

        if data is None or data.empty:
            return pd.DataFrame()

        if isinstance(
            data.columns,
            pd.MultiIndex,
        ):

            data.columns = [
                column[0]
                for column in data.columns
            ]

        required = [
            "Close",
            "High",
            "Low",
        ]

        for column in required:

            if column not in data.columns:
                return pd.DataFrame()

        data = data.dropna(
            subset=required
        )

        return data

    except Exception:

        return pd.DataFrame()


gold_history = get_gold_history()


# ============================================================
# TECHNICAL CALCULATIONS
# ============================================================

technical_bias = "N/A"
technical_score = None
support = None
resistance = None
ma20 = None
ma50 = None
last_technical_price = None


if not gold_history.empty:

    close = pd.to_numeric(
        gold_history["Close"],
        errors="coerce",
    ).dropna()

    high = pd.to_numeric(
        gold_history["High"],
        errors="coerce",
    ).dropna()

    low = pd.to_numeric(
        gold_history["Low"],
        errors="coerce",
    ).dropna()

    if len(close) >= 20:

        ma20 = float(
            close.tail(20).mean()
        )

        support = float(
            low.tail(20).min()
        )

        resistance = float(
            high.tail(20).max()
        )

    if len(close) >= 50:

        ma50 = float(
            close.tail(50).mean()
        )

    last_technical_price = float(
        close.iloc[-1]
    )

    score = 0.0

    if ma20 is not None:

        if last_technical_price > ma20:
            score += 1
        else:
            score -= 1

    if ma50 is not None:

        if last_technical_price > ma50:
            score += 1
        else:
            score -= 1

    if (
        ma20 is not None
        and ma50 is not None
    ):

        if ma20 > ma50:
            score += 1
        else:
            score -= 1

    technical_score = score

    if score >= 2:

        technical_bias = "BULLISH"

    elif score <= -2:

        technical_bias = "BEARISH"

    else:

        technical_bias = "NEUTRAL / WAIT"


# ============================================================
# TECHNICAL DISPLAY
# ============================================================

st.subheader(
    "📈 Technical Analysis"
)

tech = st.columns(5)

tech[0].metric(
    "Technical Bias",
    technical_bias,
)

tech[1].metric(
    "Technical Score",
    (
        f"{technical_score:.1f}"
        if technical_score is not None
        else "N/A"
    ),
)

tech[2].metric(
    "Support",
    money(support),
)

tech[3].metric(
    "Resistance",
    money(resistance),
)

tech[4].metric(
    "20 / 50 MA",
    (
        f"{money(ma20)} / {money(ma50)}"
        if ma20 is not None
        and ma50 is not None
        else "N/A"
    ),
)


# ============================================================
# MACRO ANALYSIS
# ============================================================

st.subheader(
    "🌎 Macro Analysis"
)

macro_score = 0

macro_reasons = []


# DXY
#
# A weaker dollar is generally supportive of gold.
# A stronger dollar is generally a headwind.

if dxy_pct is not None:

    if dxy_pct < -0.10:

        macro_score += 1

        macro_reasons.append(
            "DXY is falling"
        )

    elif dxy_pct > 0.10:

        macro_score -= 1

        macro_reasons.append(
            "DXY is rising"
        )


# Treasury

if treasury_pct is not None:

    if treasury_pct < -0.10:

        macro_score += 1

        macro_reasons.append(
            "Treasury yield is falling"
        )

    elif treasury_pct > 0.10:

        macro_score -= 1

        macro_reasons.append(
            "Treasury yield is rising"
        )


if macro_score >= 2:

    macro_bias = "BULLISH"

elif macro_score <= -2:

    macro_bias = "BEARISH"

else:

    macro_bias = "NEUTRAL / WAIT"


macro_confidence = min(
    10,
    max(
        1,
        5 + abs(macro_score) * 2,
    ),
)


macro_cols = st.columns(3)

macro_cols[0].metric(
    "Macro Bias",
    macro_bias,
)

macro_cols[1].metric(
    "Macro Confidence",
    f"{macro_confidence}/10",
)

macro_cols[2].metric(
    "Treasury Yield",
    (
        f"{treasury:.2f}%"
        if treasury is not None
        else "N/A"
    ),
)


if macro_reasons:

    st.caption(
        " • ".join(macro_reasons)
    )


# ============================================================
# OVERALL PREDICTION
# ============================================================

overall_score = 0


if technical_score is not None:

    if technical_score > 0:
        overall_score += 2

    elif technical_score < 0:
        overall_score -= 2


if macro_score > 0:

    overall_score += 1

elif macro_score < 0:

    overall_score -= 1


if overall_score >= 2:

    overall_bias = "BULLISH"

elif overall_score <= -2:

    overall_bias = "BEARISH"

else:

    overall_bias = "NEUTRAL / WAIT"


confidence = min(
    10,
    max(
        1,
        5 + abs(overall_score),
    ),
)


# ============================================================
# OVERALL SIGNAL
# ============================================================

st.subheader(
    "🎯 Current Signal"
)

signal_col1, signal_col2 = st.columns(2)

signal_col1.metric(
    "Overall Bias",
    overall_bias,
)

signal_col2.metric(
    "Confidence",
    f"{confidence}/10",
)


# ============================================================
# PRICE PREDICTIONS
# ============================================================

st.subheader(
    "🎯 Prediction Targets"
)


prediction_base = (
    gold_price
    if gold_price is not None
    else last_technical_price
)


# Approximate short-term movement based on:
# - current technical direction
# - recent 5-minute volatility
#
# These are model estimates, NOT guaranteed prices.

volatility = 0.0


if not gold_history.empty:

    close = pd.to_numeric(
        gold_history["Close"],
        errors="coerce",
    ).dropna()

    if len(close) >= 10:

        returns = (
            close
            .pct_change()
            .dropna()
            .tail(50)
        )

        if not returns.empty:

            volatility = float(
                returns.std()
            )


if volatility <= 0:

    volatility = 0.00035


direction = 0

if overall_bias == "BULLISH":

    direction = 1

elif overall_bias == "BEARISH":

    direction = -1


def predicted_price(minutes):

    if prediction_base is None:
        return None

    steps = minutes / 5

    expected_move = (
        direction
        * volatility
        * (steps ** 0.5)
        * 0.75
    )

    return (
        prediction_base
        * (1 + expected_move)
    )


target_15 = predicted_price(15)
target_30 = predicted_price(30)
target_60 = predicted_price(60)
target_120 = predicted_price(120)


targets = st.columns(4)

targets[0].metric(
    "15 Minutes",
    money(target_15),
)

targets[1].metric(
    "30 Minutes",
    money(target_30),
)

targets[2].metric(
    "1 Hour",
    money(target_60),
)

targets[3].metric(
    "2 Hours",
    money(target_120),
)


# ============================================================
# TRADE INTERPRETATION
# ============================================================

st.subheader(
    "🧭 Trade Interpretation"
)


if overall_bias == "BULLISH":

    st.success(
        "BULLISH — confirmation required"
    )

    st.write(
        "The technical and macro picture currently "
        "leans bullish. This is not an automatic "
        "entry signal. Ideally, price should hold "
        "above support and continue making higher "
        "highs before considering a long setup."
    )

    if resistance is not None:

        st.caption(
            f"Watch resistance near {money(resistance)}."
        )


elif overall_bias == "BEARISH":

    st.error(
        "BEARISH — confirmation required"
    )

    st.write(
        "The technical and macro picture currently "
        "leans bearish. Ideally, price should fail "
        "to reclaim resistance and continue making "
        "lower highs before considering a short setup."
    )

    if support is not None:

        st.caption(
            f"Watch support near {money(support)}."
        )


else:

    st.warning(
        "NEUTRAL / WAIT"
    )

    st.write(
        "The indicators are mixed. This is generally "
        "a wait-for-confirmation environment rather "
        "than a strong directional setup."
    )


# ============================================================
# NEWS
# ============================================================

st.subheader(
    "📰 Recent Gold & Macro News"
)


RSS_FEEDS = [

    (
        "Reuters Business",
        "https://feeds.reuters.com/reuters/businessNews",
    ),

    (
        "Kitco Gold",
        "https://www.kitco.com/rss/news.xml",
    ),

    (
        "Google News — Gold",
        "https://news.google.com/rss/search?"
        "q=gold+price+when:1d&hl=en-US&gl=US&ceid=US:en",
    ),

]


def get_news():

    articles = []

    for source, url in RSS_FEEDS:

        try:

            feed = feedparser.parse(
                url
            )

            for entry in feed.entries[:10]:

                title = safe_text(
                    entry.get(
                        "title"
                    ),
                    "",
                )

                link = safe_text(
                    entry.get(
                        "link"
                    ),
                    "",
                )

                published = safe_text(
                    entry.get(
                        "published",
                    ),
                    "",
                )

                if not title or not link:
                    continue

                title_lower = title.lower()

                relevant_terms = [

                    "gold",
                    "fed",
                    "federal reserve",
                    "inflation",
                    "cpi",
                    "ppi",
                    "pce",
                    "treasury",
                    "yield",
                    "dollar",
                    "dxy",
                    "interest rate",
                    "jobs",
                    "employment",
                    "economy",

                ]

                if not any(
                    term in title_lower
                    for term in relevant_terms
                ):
                    continue

                articles.append({

                    "title": title,

                    "link": link,

                    "source": source,

                    "published": published,

                })

        except Exception:
            continue

    return articles


news = get_news()


if news:

    seen = set()

    count = 0

    for article in news:

        title = article["title"]

        if title in seen:
            continue

        seen.add(title)

        st.markdown(
            f"**{title}**"
        )

        st.caption(
            f"{article['source']} "
            f"• {article['published']}"
        )

        st.markdown(
            f"[Read article]({article['link']})"
        )

        count += 1

        if count >= 8:
            break

else:

    st.info(
        "No recent relevant news was returned."
    )


# ============================================================
# HISTORICAL PERFORMANCE
# ============================================================

st.subheader(
    "🏆 Historical Performance"
)


result_columns = [
    "result_15m",
    "result_30m",
    "result_1h",
    "result_2h",
]


performance_rows = []


for result_column in result_columns:

    if result_column not in history.columns:
        continue

    values = (
        history[result_column]
        .dropna()
        .astype(str)
        .str.upper()
        .str.strip()
    )

    correct = values.isin(
        [
            "CORRECT",
            "WIN",
            "SUCCESS",
            "TRUE",
        ]
    ).sum()

    incorrect = values.isin(
        [
            "INCORRECT",
            "LOSS",
            "FAIL",
            "FALSE",
        ]
    ).sum()

    total = correct + incorrect

    if total == 0:
        continue

    accuracy = (
        correct
        / total
        * 100
    )

    performance_rows.append({

        "Time Horizon":
            result_column.replace(
                "result_",
                "",
            ),

        "Correct":
            int(correct),

        "Incorrect":
            int(incorrect),

        "Accuracy":
            f"{accuracy:.1f}%",

    })


if performance_rows:

    st.dataframe(
        pd.DataFrame(
            performance_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

else:

    st.info(
        "Historical prediction performance will "
        "appear here after predictions have been "
        "collected and evaluated."
    )


# ============================================================
# RAW COLLECTION HISTORY
# ============================================================

with st.expander(
    "📚 Market Collection History",
    expanded=False,
):

    display_history = history.copy()

    if "_timestamp" in display_history.columns:

        display_history = display_history.drop(
            columns=[
                "_timestamp"
            ]
        )

    timestamp_columns = [

        "collected_at_utc",
        "timestamp_utc",
        "timestamp",
        "datetime",
        "date",
        "time",
        "created_at",
        "prediction_time",
        "recorded_at",
        "gold_retrieved_at_utc",
        "dxy_retrieved_at_utc",
        "treasury_retrieved_at_utc",

    ]

    for column in timestamp_columns:

        if column not in display_history.columns:
            continue

        parsed = pd.to_datetime(
            display_history[column],
            errors="coerce",
            utc=True,
        )

        formatted = (
            parsed
            .dt.tz_convert(ET)
            .dt.strftime(
                "%Y-%m-%d %I:%M:%S %p ET"
            )
        )

        display_history[column] = (
            formatted.fillna("")
        )


    # Convert every remaining object column to
    # ordinary strings. This prevents PyArrow errors.

    for column in display_history.columns:

        if (
            display_history[column]
            .dtype
            == "object"
        ):

            display_history[column] = (
                display_history[column]
                .fillna("")
                .astype(str)
            )


    display_history = (
        display_history
        .head(100)
        .reset_index(drop=True)
    )


    st.dataframe(
        display_history,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Gold Market Monitor"
)

st.caption(
    "Dashboard viewed: "
    + datetime.now(
        ET
    ).strftime(
        "%Y-%m-%d %I:%M:%S %p ET"
    )
)
