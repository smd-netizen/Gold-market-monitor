import base64
import io
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ============================================================
# PAGE CONFIGURATION
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
        "Authorization":
            f"Bearer {token}",

        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            "2022-11-28",
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
            timeout=20,
        )


        if response.status_code != 200:

            return pd.DataFrame()


        content = base64.b64decode(
            response.json()["content"]
        )


        return pd.read_csv(
            io.BytesIO(content)
        )


    except Exception:

        return pd.DataFrame()


# ============================================================
# SAFE HELPERS
# ============================================================

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


# ============================================================
# TIMESTAMP HELPERS
# ============================================================

def parse_timestamp(value):

    try:

        if pd.isna(value):

            return None

        timestamp = pd.to_datetime(
            value,
            utc=True,
        )


        if pd.isna(timestamp):

            return None


        return timestamp.to_pydatetime()


    except Exception:

        return None


def format_timestamp(value):

    timestamp = parse_timestamp(
        value
    )


    if timestamp is None:

        return "Unknown"


    timestamp = timestamp.astimezone(
        ET
    )


    return timestamp.strftime(
        "%Y-%m-%d %I:%M:%S %p ET"
    )


def format_age(value):

    timestamp = parse_timestamp(
        value
    )


    if timestamp is None:

        return "Unknown"


    now = datetime.now(
        timezone.utc
    )


    seconds = max(
        0,
        (
            now - timestamp
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


# ============================================================
# FIND TIMESTAMP
# ============================================================

def find_timestamp_column(
    dataframe
):

    candidates = [

        "collected_at_utc",

        "timestamp_utc",

        "timestamp",

        "datetime",

        "date",

        "time",

        "created_at",

        "prediction_time",

        "recorded_at",
    ]


    for column in candidates:

        if column in dataframe.columns:

            return column


    return None


# ============================================================
# LOAD HISTORY
# ============================================================

history = load_history()


if history.empty:

    st.title(
        "🥇 Gold Market Monitor"
    )

    st.warning(
        "GitHub storage is connected, but "
        "prediction_history.csv could not "
        "be loaded."
    )

    st.stop()


# ============================================================
# TIMESTAMP COMPATIBILITY
# ============================================================

timestamp_column = (
    find_timestamp_column(
        history
    )
)


if timestamp_column is None:

    st.title(
        "🥇 Gold Market Monitor"
    )

    st.error(
        "No recognizable timestamp was found "
        "in prediction_history.csv."
    )

    st.write(
        "Columns found:"
    )

    st.code(
        ", ".join(
            history.columns.astype(str)
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
        "The prediction history contains "
        "no usable timestamps."
    )

    st.stop()


history = history.sort_values(
    "_timestamp"
)


latest = history.iloc[-1]


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
# CURRENT MARKET
# ============================================================

st.subheader(
    "Current Market"
)


gold_price = safe_float(
    latest.get(
        "gold_price"
    )
)


# The original CSV calls this dxy_price,
# not dxy.

dxy = safe_float(
    latest.get(
        "dxy_price"
    )
)


dxy_pct = safe_float(
    latest.get(
        "dxy_pct"
    )
)


ten_year = safe_float(
    latest.get(
        "treasury_yield"
    )
)


ten_year_pct = safe_float(
    latest.get(
        "treasury_pct"
    )
)


overall_bias = latest.get(
    "overall_bias",
    "N/A",
)


confidence = safe_float(
    latest.get(
        "confidence"
    )
)


columns = st.columns(4)


columns[0].metric(
    "🥇 Gold — Oct 2026",
    money(
        gold_price
    ),
)


columns[1].metric(
    "💵 DXY",
    number(
        dxy,
        3,
    ),
    (
        percentage(
            dxy_pct
        )
        if dxy_pct is not None
        else None
    ),
)


columns[2].metric(
    "🇺🇸 10Y Treasury",
    (
        f"{ten_year:.2f}%"
        if ten_year is not None
        else "Unavailable"
    ),
    (
        percentage(
            ten_year_pct
        )
        if ten_year_pct is not None
        else None
    ),
)


columns[3].metric(
    "Overall Bias",
    str(
        overall_bias
    ),
    (
        f"Confidence {confidence:.0f}/10"
        if confidence is not None
        else None
    ),
)


# ============================================================
# FRESHNESS
# ============================================================

st.subheader(
    "⏱ Data Freshness"
)


freshness = st.columns(3)


# Gold

gold_timestamp = latest.get(
    "gold_retrieved_at_utc"
)


if pd.isna(
    gold_timestamp
):

    gold_timestamp = latest[
        "_timestamp"
    ]


freshness[0].metric(
    "Gold",
    format_age(
        gold_timestamp
    ),
)


freshness[0].caption(
    format_timestamp(
        gold_timestamp
    )
)


# DXY

dxy_timestamp = latest.get(
    "dxy_retrieved_at_utc"
)


if pd.isna(
    dxy_timestamp
):

    dxy_timestamp = latest[
        "_timestamp"
    ]


freshness[1].metric(
    "DXY",
    format_age(
        dxy_timestamp
    ),
)


freshness[1].caption(
    format_timestamp(
        dxy_timestamp
    )
)


# Treasury

treasury_timestamp = latest.get(
    "treasury_retrieved_at_utc"
)


if pd.isna(
    treasury_timestamp
):

    treasury_timestamp = latest[
        "_timestamp"
    ]


freshness[2].metric(
    "10Y Treasury",
    format_age(
        treasury_timestamp
    ),
)


freshness[2].caption(
    format_timestamp(
        treasury_timestamp
    )
)


# ============================================================
# DATA QUALITY
# ============================================================

st.subheader(
    "📊 Data Quality"
)


if (
    "data_quality"
    in history.columns
):

    quality = str(
        latest.get(
            "data_quality"
        )
    )


    if quality == "PASS":

        st.success(
            "🟢 DATA QUALITY: PASS"
        )


    elif quality == "WARN":

        st.warning(
            "🟡 DATA QUALITY: WARNING"
        )


    else:

        st.info(
            f"Data quality status: {quality}"
        )


else:

    st.info(
        "Existing records were created before "
        "the new data-quality system was added."
    )


# ============================================================
# GOLD INFORMATION
# ============================================================

st.subheader(
    "🥇 Gold Contract"
)


gold_info = st.columns(3)


gold_info[0].write(
    "**Contract:** "
    + str(
        latest.get(
            "contract",
            "1OZV6",
        )
    )
)


gold_info[1].write(
    "**Contract Name:** "
    + str(
        latest.get(
            "contract_name",
            "1-Ounce Gold October 2026",
        )
    )
)


gold_info[2].write(
    "**Market:** COMEX"
)


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

st.subheader(
    "📈 Technical Analysis"
)


technical = st.columns(4)


technical_bias = latest.get(
    "technical_bias",
    "N/A",
)


technical_score = safe_float(
    latest.get(
        "technical_score"
    )
)


support = safe_float(
    latest.get(
        "support"
    )
)


resistance = safe_float(
    latest.get(
        "resistance"
    )
)


technical[0].metric(
    "Technical Bias",
    str(
        technical_bias
    ),
)


technical[1].metric(
    "Technical Score",
    (
        f"{technical_score:.1f}"
        if technical_score is not None
        else "N/A"
    ),
)


technical[2].metric(
    "Support",
    money(
        support
    ),
)


technical[3].metric(
    "Resistance",
    money(
        resistance
    ),
)


# ============================================================
# MOVING AVERAGES
# ============================================================

ma20 = safe_float(
    latest.get(
        "ma20"
    )
)


ma50 = safe_float(
    latest.get(
        "ma50"
    )
)


ma_columns = st.columns(2)


ma_columns[0].metric(
    "20-Period MA",
    money(
        ma20
    ),
)


ma_columns[1].metric(
    "50-Period MA",
    money(
        ma50
    ),
)


# ============================================================
# MACRO
# ============================================================

st.subheader(
    "🌎 Macro Analysis"
)


macro = st.columns(3)


macro_bias = latest.get(
    "macro_bias",
    "N/A",
)


macro_confidence = safe_float(
    latest.get(
        "macro_confidence"
    )
)


macro[0].metric(
    "Macro Bias",
    str(
        macro_bias
    ),
)


macro[1].metric(
    "Macro Confidence",
    (
        f"{macro_confidence:.0f}/10"
        if macro_confidence is not None
        else "N/A"
    ),
)


macro[2].metric(
    "Treasury Yield",
    (
        f"{ten_year:.2f}%"
        if ten_year is not None
        else "N/A"
    ),
)


# ============================================================
# TARGETS
# ============================================================

st.subheader(
    "🎯 Prediction Targets"
)


targets = st.columns(4)


target_fields = [

    (
        "15 Minutes",
        "target_15m",
    ),

    (
        "30 Minutes",
        "target_30m",
    ),

    (
        "1 Hour",
        "target_1h",
    ),

    (
        "2 Hours",
        "target_2h",
    ),

]


for column, (
    label,
    field,
) in zip(
    targets,
    target_fields,
):

    column.metric(
        label,
        money(
            latest.get(
                field
            )
        ),
    )


# ============================================================
# RESULTS
# ============================================================

st.subheader(
    "📊 Prediction Results"
)


result_columns = st.columns(4)


result_fields = [

    (
        "15 Minutes",
        "result_15m",
    ),

    (
        "30 Minutes",
        "result_30m",
    ),

    (
        "1 Hour",
        "result_1h",
    ),

    (
        "2 Hours",
        "result_2h",
    ),

]


for column, (
    label,
    field,
) in zip(
    result_columns,
    result_fields,
):

    value = latest.get(
        field
    )


    if pd.isna(value):

        value = "Pending"


    column.metric(
        label,
        str(value),
    )


# ============================================================
# TRADE SETUP
# ============================================================

st.subheader(
    "🧭 Trade Interpretation"
)


if str(
    overall_bias
).upper() == "BULLISH":

    st.success(
        "The model currently has a bullish bias."
    )

    st.write(
        "That does **not** automatically mean "
        "enter the trade. The next step is to "
        "look for price confirmation around "
        "support/resistance and make sure DXY "
        "and Treasury yields are not contradicting "
        "the setup."
    )


elif str(
    overall_bias
).upper() == "BEARISH":

    st.error(
        "The model currently has a bearish bias."
    )

    st.write(
        "The bearish signal should still be "
        "confirmed by price action and the "
        "macro environment before considering "
        "a trade."
    )


else:

    st.warning(
        "The model currently has a neutral/mixed bias."
    )

    st.write(
        "This is generally a wait-for-confirmation "
        "environment rather than a strong directional setup."
    )


# ============================================================
# PERFORMANCE
# ============================================================

st.subheader(
    "🏆 Historical Performance"
)


performance_rows = []


for period in [
    "15m",
    "30m",
    "1h",
    "2h",
]:

    result_column = (
        f"result_{period}"
    )


    if result_column not in history.columns:

        continue


    values = history[
        result_column
    ].dropna()


    if values.empty:

        continue


    values = (
        values.astype(str)
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


    evaluated = (
        correct
        + incorrect
    )


    if evaluated == 0:

        continue


    accuracy = (
        correct
        / evaluated
        * 100
    )


    performance_rows.append({

        "Time Horizon":
            period,

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
        "There are not enough evaluated "
        "predictions yet to calculate performance."
    )


# ============================================================
# HISTORY
# ============================================================

st.subheader(
    "📚 Prediction History"
)


display_history = history.copy()


if "_timestamp" in display_history.columns:

    display_history = (
        display_history.drop(
            columns=[
                "_timestamp"
            ]
        )
    )


display_history = (
    display_history
    .sort_values(
        timestamp_column,
        ascending=False,
    )
    .head(100)
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
