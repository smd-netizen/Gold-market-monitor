import base64
import io
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# =========================================================
# CONFIGURATION
# =========================================================

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


# =========================================================
# GITHUB CONNECTION
# =========================================================

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


def load_history():

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
            timeout=15,
        )

        if response.status_code != 200:
            return pd.DataFrame()

        data = response.json()

        content = base64.b64decode(
            data["content"]
        )

        return pd.read_csv(
            io.BytesIO(content)
        )

    except Exception:

        return pd.DataFrame()


# =========================================================
# TIME / FRESHNESS
# =========================================================

def format_age(timestamp):

    try:

        if pd.isna(timestamp):
            return "Unknown"

        timestamp = pd.to_datetime(
            timestamp,
            utc=True,
        ).to_pydatetime()

        current = datetime.now(
            timezone.utc
        )

        seconds = max(
            0,
            (
                current - timestamp
            ).total_seconds(),
        )

        if seconds < 60:

            return (
                f"{int(seconds)} sec ago"
            )

        if seconds < 3600:

            return (
                f"{int(seconds // 60)} min ago"
            )

        if seconds < 86400:

            return (
                f"{seconds / 3600:.1f} hr ago"
            )

        return (
            f"{seconds / 86400:.1f} days ago"
        )

    except Exception:

        return "Unknown"


def format_timestamp(timestamp):

    try:

        dt = pd.to_datetime(
            timestamp,
            utc=True,
        ).tz_convert(ET)

        return dt.strftime(
            "%Y-%m-%d %I:%M:%S %p ET"
        )

    except Exception:

        return "Unknown"


# =========================================================
# SAFE VALUE HELPERS
# =========================================================

def safe_float(value):

    try:

        if pd.isna(value):
            return None

        return float(value)

    except Exception:

        return None


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
        return "Unavailable"

    return f"{value:+.2f}%"


# =========================================================
# APPLICATION HEADER
# =========================================================

st.title(
    "🥇 Gold Market Monitor"
)

st.caption(
    "Dashboard only — market collection runs "
    "independently through GitHub Actions."
)


# =========================================================
# LOAD HISTORY
# =========================================================

history = load_history()


if history.empty:

    st.warning(
        "GitHub storage is connected, but no "
        "prediction history is currently available."
    )

    st.info(
        "The background collector must successfully "
        "run before market data will appear here."
    )

    st.stop()


# =========================================================
# NORMALIZE HISTORY
# =========================================================

if "collected_at_utc" not in history.columns:

    st.error(
        "prediction_history.csv does not contain "
        "the collected_at_utc column."
    )

    st.stop()


history["collected_at_utc"] = pd.to_datetime(
    history["collected_at_utc"],
    errors="coerce",
    utc=True,
)

history = history.dropna(
    subset=["collected_at_utc"]
)

history = history.sort_values(
    "collected_at_utc"
)


if history.empty:

    st.warning(
        "Prediction history contains no valid "
        "collection timestamps."
    )

    st.stop()


latest = history.iloc[-1]


# =========================================================
# CURRENT MARKET VALUES
# =========================================================

gold_price = safe_float(
    latest.get("gold_price")
)

gold_pct = safe_float(
    latest.get("gold_pct")
)

gold_change = safe_float(
    latest.get("gold_change")
)

dxy = safe_float(
    latest.get("dxy")
)

dxy_pct = safe_float(
    latest.get("dxy_pct")
)

ten_year = safe_float(
    latest.get("teny")
)

bias = latest.get(
    "bias",
    "N/A",
)

confidence = latest.get(
    "confidence",
    "N/A",
)


# =========================================================
# TOP METRICS
# =========================================================

st.subheader(
    "Current Market"
)

columns = st.columns(4)


# GOLD

columns[0].metric(
    "🥇 Gold — Oct 2026",
    (
        money(gold_price)
        if gold_price is not None
        else "Unavailable"
    ),
    (
        percentage(gold_pct)
        if gold_pct is not None
        else None
    ),
)


# DXY

columns[1].metric(
    "💵 DXY",
    (
        number(dxy, 3)
        if dxy is not None
        else "Unavailable"
    ),
    (
        percentage(dxy_pct)
        if dxy_pct is not None
        else None
    ),
)


# 10 YEAR

columns[2].metric(
    "🇺🇸 10Y Treasury",
    (
        f"{ten_year:.2f}%"
        if ten_year is not None
        else "Unavailable"
    ),
)


# BIAS

columns[3].metric(
    "Market Bias",
    str(bias),
    (
        f"Confidence {confidence}/10"
        if confidence != "N/A"
        else None
    ),
)


# =========================================================
# COLLECTION TIMESTAMP
# =========================================================

st.subheader(
    "⏱ Data Freshness"
)

fresh_columns = st.columns(3)


gold_time = latest.get(
    "gold_retrieved_at_utc"
)

dxy_time = latest.get(
    "dxy_retrieved_at_utc"
)

ten_year_time = latest.get(
    "teny_retrieved_at_utc"
)


fresh_columns[0].metric(
    "Gold",
    format_age(gold_time),
)

fresh_columns[0].caption(
    format_timestamp(gold_time)
)


fresh_columns[1].metric(
    "DXY",
    format_age(dxy_time),
)

fresh_columns[1].caption(
    format_timestamp(dxy_time)
)


fresh_columns[2].metric(
    "10Y Treasury",
    format_age(ten_year_time),
)

fresh_columns[2].caption(
    format_timestamp(ten_year_time)
)


# =========================================================
# COLLECTION STATUS
# =========================================================

collection_time = latest.get(
    "collected_at_utc"
)

st.write(
    "**Last complete prediction collection:** "
    + format_timestamp(collection_time)
)


# =========================================================
# DATA QUALITY
# =========================================================

quality = str(
    latest.get(
        "data_quality",
        "UNKNOWN",
    )
)


st.subheader(
    "📊 Data Quality"
)


if quality == "PASS":

    st.success(
        "🟢 DATA QUALITY: PASS"
    )

elif quality == "WARN":

    st.warning(
        "🟡 DATA QUALITY: WARNING"
    )

    st.caption(
        "Gold is being collected from a public quote "
        "page. The collector records when it retrieved "
        "the page, but does not claim that timestamp is "
        "the exchange timestamp."
    )

else:

    st.error(
        f"🔴 DATA QUALITY: {quality}"
    )


# =========================================================
# GOLD CONTRACT INFORMATION
# =========================================================

st.subheader(
    "🥇 Gold Contract"
)

contract = latest.get(
    "gold_symbol",
    "1OZV6",
)

gold_status = latest.get(
    "gold_status",
    "Unknown",
)


contract_columns = st.columns(3)


contract_columns[0].write(
    f"**Contract:** {contract}"
)

contract_columns[1].write(
    "**Market:** COMEX"
)

contract_columns[2].write(
    "**Month:** October 2026"
)


st.caption(
    f"Gold data status: {gold_status}"
)


# =========================================================
# MARKET LEVELS
# =========================================================

st.subheader(
    "📈 Gold Levels"
)

level_columns = st.columns(5)


gold_high = safe_float(
    latest.get("gold_high")
)

gold_low = safe_float(
    latest.get("gold_low")
)

support = safe_float(
    latest.get("support")
)

resistance = safe_float(
    latest.get("resistance")
)

breakout = safe_float(
    latest.get("breakout")
)


level_columns[0].metric(
    "Today's High",
    money(gold_high),
)

level_columns[1].metric(
    "Today's Low",
    money(gold_low),
)

level_columns[2].metric(
    "Support",
    money(support),
)

level_columns[3].metric(
    "Resistance",
    money(resistance),
)

level_columns[4].metric(
    "Breakout",
    money(breakout),
)


# =========================================================
# PREDICTION
# =========================================================

st.subheader(
    "🔮 Current Prediction"
)


prediction_columns = st.columns(3)


prediction_columns[0].metric(
    "Overall Bias",
    str(
        latest.get(
            "bias",
            "N/A",
        )
    ),
)


prediction_columns[1].metric(
    "Macro",
    str(
        latest.get(
            "macro_bias",
            "N/A",
        )
    ),
)


prediction_columns[2].metric(
    "Technical",
    str(
        latest.get(
            "technical_bias",
            "N/A",
        )
    ),
)


setup = latest.get(
    "setup",
    "N/A",
)


st.info(
    f"**Trade Setup:** {setup}"
)


# =========================================================
# REASONS
# =========================================================

reasons = latest.get(
    "reasons"
)


if pd.notna(reasons):

    st.subheader(
        "Why the Model Says This"
    )

    for reason in str(
        reasons
    ).split(" | "):

        if reason.strip():

            st.write(
                "• " + reason.strip()
            )


# =========================================================
# NEWS COUNT
# =========================================================

news_count = latest.get(
    "news_count"
)


if pd.notna(news_count):

    st.caption(
        f"Recent news articles considered: "
        f"{int(float(news_count))}"
    )


# =========================================================
# PERFORMANCE
# =========================================================

st.subheader(
    "🎯 Prediction Performance"
)


# Only calculate validated performance
# when outcome columns actually exist.

if (
    "prediction_correct"
    in history.columns
):

    valid = history[
        history[
            "prediction_correct"
        ].notna()
    ]

    if not valid.empty:

        correct = (
            valid[
                "prediction_correct"
            ]
            .astype(bool)
            .sum()
        )

        total = len(valid)

        accuracy = (
            correct / total * 100
        )

        p1, p2, p3 = st.columns(3)

        p1.metric(
            "Correct",
            correct,
        )

        p2.metric(
            "Evaluated",
            total,
        )

        p3.metric(
            "Accuracy",
            f"{accuracy:.1f}%",
        )

    else:

        st.info(
            "Prediction outcomes have not "
            "been evaluated yet."
        )

else:

    st.info(
        "Prediction performance will appear "
        "once predictions have enough subsequent "
        "market data to be evaluated."
    )


# =========================================================
# HISTORY
# =========================================================

st.subheader(
    "📚 Prediction History"
)


display_history = history.copy()


# Legacy data remains stored.
# We simply don't mix it into future
# validated performance calculations.

if "legacy" in display_history.columns:

    legacy_mask = (
        display_history["legacy"]
        .fillna(False)
        .astype(str)
        .str.lower()
        == "true"
    )

    display_history = (
        display_history[
            ~legacy_mask
        ]
    )


display_history = (
    display_history
    .sort_values(
        "collected_at_utc",
        ascending=False,
    )
    .head(100)
)


# Convert timestamps to something
# human-readable.

if "collected_at_utc" in display_history:

    display_history[
        "collected_at_utc"
    ] = (
        pd.to_datetime(
            display_history[
                "collected_at_utc"
            ],
            utc=True,
        )
        .dt.tz_convert(ET)
        .dt.strftime(
            "%Y-%m-%d %I:%M:%S %p ET"
        )
    )


st.dataframe(
    display_history,
    use_container_width=True,
    hide_index=True,
)


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Gold Market Monitor — "
    "background collection is handled by "
    "GitHub Actions, not by the dashboard."
)

st.caption(
    "Dashboard viewed: "
    + datetime.now(ET).strftime(
        "%Y-%m-%d %I:%M:%S %p ET"
    )
)
