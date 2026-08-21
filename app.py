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
# GITHUB
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

        content = base64.b64decode(
            response.json()["content"]
        )

        return pd.read_csv(
            io.BytesIO(content)
        )

    except Exception:

        return pd.DataFrame()


# =========================================================
# HELPERS
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


def format_age(timestamp):

    try:

        if pd.isna(timestamp):
            return "Unknown"

        timestamp = pd.to_datetime(
            timestamp,
            utc=True,
        ).to_pydatetime()

        seconds = max(
            0,
            (
                datetime.now(timezone.utc)
                - timestamp
            ).total_seconds(),
        )

        if seconds < 60:
            return f"{int(seconds)} sec ago"

        if seconds < 3600:
            return f"{int(seconds // 60)} min ago"

        if seconds < 86400:
            return f"{seconds / 3600:.1f} hr ago"

        return f"{seconds / 86400:.1f} days ago"

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
# FIND THE TIMESTAMP COLUMN
# =========================================================

def find_timestamp_column(df):

    possible_columns = [

        "collected_at_utc",

        "timestamp",

        "datetime",

        "date",

        "time",

        "created_at",

        "prediction_time",

        "recorded_at",

    ]

    for column in possible_columns:

        if column in df.columns:

            return column

    return None


# =========================================================
# APPLICATION
# =========================================================

st.title(
    "🥇 Gold Market Monitor"
)

st.caption(
    "Dashboard only — market collection runs "
    "independently through GitHub Actions."
)


# =========================================================
# LOAD DATA
# =========================================================

history = load_history()


if history.empty:

    st.warning(
        "GitHub storage is connected, but "
        "prediction_history.csv is empty or "
        "could not be loaded."
    )

    st.stop()


# =========================================================
# TIMESTAMP COMPATIBILITY
# =========================================================

timestamp_column = find_timestamp_column(
    history
)


if timestamp_column is None:

    st.warning(
        "The existing prediction history uses "
        "an older format that does not contain "
        "a recognizable timestamp."
    )

    st.write(
        "**Columns currently found:**"
    )

    st.code(
        ", ".join(
            history.columns.astype(str)
        )
    )

    st.info(
        "The existing history will not be deleted. "
        "The new collector will begin writing the "
        "new format once GitHub Actions runs."
    )

    st.stop()


# Convert whatever timestamp format we found.

history["_timestamp"] = pd.to_datetime(
    history[timestamp_column],
    errors="coerce",
    utc=True,
)


history = history.dropna(
    subset=["_timestamp"]
)


if history.empty:

    st.warning(
        "The existing history contains timestamps, "
        "but none could be interpreted."
    )

    st.stop()


history = history.sort_values(
    "_timestamp"
)


latest = history.iloc[-1]


# =========================================================
# CURRENT VALUES
# =========================================================

gold_price = safe_float(
    latest.get("gold_price")
)

gold_pct = safe_float(
    latest.get("gold_pct")
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
# MARKET METRICS
# =========================================================

st.subheader(
    "Current Market"
)

columns = st.columns(4)


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


columns[2].metric(
    "🇺🇸 10Y Treasury",

    (
        f"{ten_year:.2f}%"
        if ten_year is not None
        else "Unavailable"
    ),
)


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
# FRESHNESS
# =========================================================

st.subheader(
    "⏱ Data Freshness"
)


fresh = st.columns(3)


gold_time = latest.get(
    "gold_retrieved_at_utc",
    latest["_timestamp"],
)

dxy_time = latest.get(
    "dxy_retrieved_at_utc",
    latest["_timestamp"],
)

ten_year_time = latest.get(
    "teny_retrieved_at_utc",
    latest["_timestamp"],
)


fresh[0].metric(
    "Gold",
    format_age(gold_time),
)

fresh[0].caption(
    format_timestamp(gold_time)
)


fresh[1].metric(
    "DXY",
    format_age(dxy_time),
)

fresh[1].caption(
    format_timestamp(dxy_time)
)


fresh[2].metric(
    "10Y Treasury",
    format_age(ten_year_time),
)

fresh[2].caption(
    format_timestamp(ten_year_time)
)


st.write(
    "**Last prediction collection:** "
    + format_timestamp(
        latest["_timestamp"]
    )
)


# =========================================================
# DATA QUALITY
# =========================================================

quality = str(
    latest.get(
        "data_quality",
        "LEGACY DATA",
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

elif quality == "LEGACY DATA":

    st.info(
        "🔵 LEGACY DATA — this observation "
        "was created by the previous version "
        "of the monitor."
    )

else:

    st.error(
        f"🔴 DATA QUALITY: {quality}"
    )


# =========================================================
# GOLD
# =========================================================

st.subheader(
    "🥇 Gold Contract"
)


gold_columns = st.columns(3)


gold_columns[0].write(
    "**Contract:** "
    + str(
        latest.get(
            "gold_symbol",
            "1OZV6",
        )
    )
)


gold_columns[1].write(
    "**Market:** COMEX"
)


gold_columns[2].write(
    "**Month:** October 2026"
)


# =========================================================
# GOLD LEVELS
# =========================================================

st.subheader(
    "📈 Gold Levels"
)


levels = st.columns(5)


level_values = [

    (
        "Today's High",
        latest.get("gold_high"),
    ),

    (
        "Today's Low",
        latest.get("gold_low"),
    ),

    (
        "Support",
        latest.get("support"),
    ),

    (
        "Resistance",
        latest.get("resistance"),
    ),

    (
        "Breakout",
        latest.get("breakout"),
    ),

]


for column, (
    label,
    value,
) in zip(
    levels,
    level_values,
):

    column.metric(
        label,
        money(value),
    )


# =========================================================
# PREDICTION
# =========================================================

st.subheader(
    "🔮 Current Prediction"
)


prediction = st.columns(3)


prediction[0].metric(
    "Overall Bias",
    str(
        latest.get(
            "bias",
            "N/A",
        )
    ),
)


prediction[1].metric(
    "Macro",
    str(
        latest.get(
            "macro_bias",
            "N/A",
        )
    ),
)


prediction[2].metric(
    "Technical",
    str(
        latest.get(
            "technical_bias",
            "N/A",
        )
    ),
)


st.info(
    "**Trade Setup:** "
    + str(
        latest.get(
            "setup",
            "N/A",
        )
    )
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
                "• "
                + reason.strip()
            )


# =========================================================
# PREDICTION PERFORMANCE
# =========================================================

st.subheader(
    "🎯 Prediction Performance"
)


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

        correct = int(
            valid[
                "prediction_correct"
            ]
            .astype(bool)
            .sum()
        )

        total = len(valid)

        accuracy = (
            correct
            / total
            * 100
        )


        performance = st.columns(3)


        performance[0].metric(
            "Correct",
            correct,
        )


        performance[1].metric(
            "Evaluated",
            total,
        )


        performance[2].metric(
            "Accuracy",
            f"{accuracy:.1f}%",
        )

    else:

        st.info(
            "No predictions have been evaluated yet."
        )

else:

    st.info(
        "Prediction accuracy will appear once "
        "the new collector begins evaluating "
        "previous predictions."
    )


# =========================================================
# HISTORY
# =========================================================

st.subheader(
    "📚 Prediction History"
)


display_history = history.copy()


# Remove our internal compatibility column.

if "_timestamp" in display_history.columns:

    display_history = (
        display_history.drop(
            columns=["_timestamp"]
        )
    )


# Put newest first.

if timestamp_column in display_history.columns:

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


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Gold Market Monitor — "
    "background collection is handled "
    "by GitHub Actions."
)

st.caption(
    "Dashboard viewed: "
    + datetime.now(ET).strftime(
        "%Y-%m-%d %I:%M:%S %p ET"
    )
)
