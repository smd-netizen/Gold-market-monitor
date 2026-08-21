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

        if value is None:
            return None

        if pd.isna(value):
            return None

        return float(value)

    except Exception:

        return None


def safe_string(value, default="N/A"):

    if value is None:
        return default

    try:

        if pd.isna(value):
            return default

    except Exception:
        pass

    text = str(value).strip()

    if not text:
        return default

    return text


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
# TIMESTAMP HELPERS
# ============================================================

def parse_timestamp(value):

    try:

        if value is None:
            return None

        if pd.isna(value):
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


def format_timestamp(value):

    timestamp = parse_timestamp(value)

    if timestamp is None:
        return "Unknown"

    timestamp = timestamp.astimezone(ET)

    return timestamp.strftime(
        "%Y-%m-%d %I:%M:%S %p ET"
    )


def format_age(value):

    timestamp = parse_timestamp(value)

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

        return f"{int(seconds)} sec ago"

    if seconds < 3600:

        return f"{int(seconds // 60)} min ago"

    if seconds < 86400:

        return f"{seconds / 3600:.1f} hr ago"

    return f"{seconds / 86400:.1f} days ago"


# ============================================================
# TIMESTAMP COLUMN
# ============================================================

def find_timestamp_column(dataframe):

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
# LATEST VALUE HELPER
# ============================================================

def latest_value(
    row,
    column,
    default=None,
):

    if column not in row.index:
        return default

    value = row.get(column)

    try:

        if pd.isna(value):
            return default

    except Exception:
        pass

    return value


# ============================================================
# LOAD HISTORY
# ============================================================

history = load_history()


if history.empty:

    st.title(
        "🥇 Gold Market Monitor"
    )

    st.error(
        "The market data file could not be loaded."
    )

    st.info(
        "Make sure the GitHub Action has successfully "
        "run and that GITHUB_TOKEN is configured."
    )

    st.stop()


# ============================================================
# TIMESTAMP COMPATIBILITY
# ============================================================

timestamp_column = find_timestamp_column(
    history
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
        "Columns currently found:"
    )

    st.code(
        ", ".join(
            str(column)
            for column in history.columns
        )
    )

    st.stop()


# ============================================================
# CREATE SAFE INTERNAL TIMESTAMP
# ============================================================

history["_display_timestamp"] = pd.to_datetime(
    history[timestamp_column],
    errors="coerce",
    utc=True,
)

history = history.dropna(
    subset=[
        "_display_timestamp"
    ]
)

if history.empty:

    st.error(
        "The CSV contains no usable timestamps."
    )

    st.stop()


history = history.sort_values(
    "_display_timestamp"
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
    latest_value(
        latest,
        "gold_price",
    )
)


gold_pct = safe_float(
    latest_value(
        latest,
        "gold_pct",
    )
)


dxy = safe_float(
    latest_value(
        latest,
        "dxy_price",
    )
)


dxy_pct = safe_float(
    latest_value(
        latest,
        "dxy_pct",
    )
)


ten_year = safe_float(
    latest_value(
        latest,
        "treasury_yield",
    )
)


ten_year_pct = safe_float(
    latest_value(
        latest,
        "treasury_pct",
    )
)


overall_bias = safe_string(
    latest_value(
        latest,
        "overall_bias",
        "NEUTRAL / WAIT",
    ),
    "NEUTRAL / WAIT",
)


confidence = safe_float(
    latest_value(
        latest,
        "confidence",
    )
)


columns = st.columns(4)


# Gold

columns[0].metric(
    "🥇 Gold — October 2026",
    money(
        gold_price
    ),
    percentage(
        gold_pct
    ),
)


# DXY

columns[1].metric(
    "💵 DXY",
    number(
        dxy,
        3,
    ),
    percentage(
        dxy_pct
    ),
)


# Treasury

columns[2].metric(
    "🇺🇸 10Y Treasury",
    (
        f"{ten_year:.2f}%"
        if ten_year is not None
        else "Unavailable"
    ),
    percentage(
        ten_year_pct
    ),
)


# Bias

confidence_text = None

if confidence is not None:

    confidence_text = (
        f"Confidence {confidence:.0f}/10"
    )


columns[3].metric(
    "Overall Bias",
    overall_bias,
    confidence_text,
)


# ============================================================
# FRESHNESS
# ============================================================

st.subheader(
    "⏱ Data Freshness"
)


freshness = st.columns(3)


def freshness_value(
    row,
    specific_column,
):

    value = latest_value(
        row,
        specific_column,
    )

    if value is not None:
        return value

    return latest_value(
        row,
        "collected_at_utc",
    )


# Gold

gold_timestamp = freshness_value(
    latest,
    "gold_retrieved_at_utc",
)

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

dxy_timestamp = freshness_value(
    latest,
    "dxy_retrieved_at_utc",
)

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

treasury_timestamp = freshness_value(
    latest,
    "treasury_retrieved_at_utc",
)

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


quality_messages = []


# Gold

if gold_price is None:

    quality_messages.append(
        "Gold price unavailable"
    )


if gold_pct is None:

    quality_messages.append(
        "Gold percentage change unavailable"
    )


# DXY

if dxy is None:

    quality_messages.append(
        "DXY unavailable"
    )

elif not 80 <= dxy <= 120:

    quality_messages.append(
        "DXY failed sanity check"
    )


# Treasury

if ten_year is None:

    quality_messages.append(
        "10Y Treasury unavailable"
    )

elif not 0 <= ten_year <= 15:

    quality_messages.append(
        "10Y Treasury failed sanity check"
    )


if quality_messages:

    st.warning(
        "🟡 DATA QUALITY WARNING: "
        + "; ".join(
            quality_messages
        )
    )

else:

    st.success(
        "🟢 DATA QUALITY: PASS"
    )


# ============================================================
# GOLD CONTRACT
# ============================================================

st.subheader(
    "🥇 Gold Contract"
)


gold_info = st.columns(4)


gold_info[0].write(
    "**Contract:** "
    + safe_string(
        latest_value(
            latest,
            "contract",
        ),
        "1OZV6.CMX",
    )
)


gold_info[1].write(
    "**Contract Name:** "
    + safe_string(
        latest_value(
            latest,
            "contract_name",
        ),
        "1-Ounce Gold — October 2026",
    )
)


gold_info[2].write(
    "**Market:** COMEX"
)


gold_source = safe_string(
    latest_value(
        latest,
        "gold_source",
    ),
    "Webull public page",
)


gold_info[3].write(
    "**Gold Source:** Webull"
)

gold_info[3].caption(
    gold_source
)


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

st.subheader(
    "📈 Technical Analysis"
)


technical_bias = safe_string(
    latest_value(
        latest,
        "technical_bias",
    ),
    "N/A",
)


technical_score = safe_float(
    latest_value(
        latest,
        "technical_score",
    )
)


support = safe_float(
    latest_value(
        latest,
        "support",
    )
)


resistance = safe_float(
    latest_value(
        latest,
        "resistance",
    )
)


technical = st.columns(4)


technical[0].metric(
    "Technical Bias",
    technical_bias,
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
    latest_value(
        latest,
        "ma20",
    )
)


ma50 = safe_float(
    latest_value(
        latest,
        "ma50",
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
# MACRO ANALYSIS
# ============================================================

st.subheader(
    "🌎 Macro Analysis"
)


macro_bias = safe_string(
    latest_value(
        latest,
        "macro_bias",
    ),
    "N/A",
)


macro_confidence = safe_float(
    latest_value(
        latest,
        "macro_confidence",
    )
)


macro = st.columns(3)


macro[0].metric(
    "Macro Bias",
    macro_bias,
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
# PREDICTION TARGETS
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

    value = latest_value(
        latest,
        field,
    )

    if value is None:

        column.metric(
            label,
            "Not generated",
        )

    else:

        column.metric(
            label,
            money(value),
        )


# ============================================================
# PREDICTION RESULTS
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

    value = latest_value(
        latest,
        field,
    )

    if value is None:

        value = "Pending"

    column.metric(
        label,
        str(value),
    )


# ============================================================
# TRADE INTERPRETATION
# ============================================================

st.subheader(
    "🧭 Trade Interpretation"
)


bias_upper = overall_bias.upper()


if "BULLISH" in bias_upper:

    st.success(
        "The model currently has a bullish bias."
    )

    st.write(
        "This is a directional signal, not an "
        "automatic entry. Look for price confirmation "
        "near support/resistance and check whether "
        "DXY and Treasury yields support the move."
    )


elif "BEARISH" in bias_upper:

    st.error(
        "The model currently has a bearish bias."
    )

    st.write(
        "This is a directional signal, not an "
        "automatic entry. Look for price confirmation "
        "near support/resistance and check whether "
        "DXY and Treasury yields support the move."
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
# HISTORICAL PERFORMANCE
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

    values = (
        history[result_column]
        .dropna()
        .astype(str)
        .str.upper()
        .str.strip()
    )

    if values.empty:
        continue

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
        "Prediction performance will appear "
        "here once evaluated predictions are "
        "available."
    )


# ============================================================
# PREDICTION HISTORY
# ============================================================

st.subheader(
    "📚 Prediction History"
)


display_history = history.copy()


# Remove internal helper column.

if "_display_timestamp" in display_history.columns:

    display_history = display_history.drop(
        columns=[
            "_display_timestamp"
        ]
    )


# ------------------------------------------------------------
# IMPORTANT:
# Convert timestamp columns to strings before giving the
# dataframe to Streamlit/PyArrow.
#
# This prevents the OverflowError caused by malformed or
# mixed datetime values in older CSV records.
# ------------------------------------------------------------

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

    converted = pd.to_datetime(
        display_history[column],
        errors="coerce",
        utc=True,
    )

    display_history[column] = (
        converted
        .dt.strftime(
            "%Y-%m-%d %I:%M:%S %p UTC"
        )
        .fillna(
            ""
        )
    )


# ------------------------------------------------------------
# Convert numeric-looking object columns safely.
# ------------------------------------------------------------

for column in display_history.columns:

    if (
        display_history[column]
        .dtype
        == "object"
    ):

        display_history[column] = (
            display_history[column]
            .astype(str)
        )


# Newest first.

sort_column = None

for candidate in [

    "collected_at_utc",

    "timestamp_utc",

    "timestamp",

]:

    if candidate in display_history.columns:

        sort_column = candidate
        break


if sort_column is not None:

    display_history = (
        display_history
        .sort_values(
            sort_column,
            ascending=False,
        )
    )


display_history = (
    display_history
    .head(100)
    .reset_index(
        drop=True
    )
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
