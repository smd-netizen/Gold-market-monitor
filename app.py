import os
import time
import base64
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from io import StringIO
from urllib.parse import quote

import feedparser
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Gold Market Monitor",
    page_icon="🥇",
    layout="wide"
)


# ============================================================
# TIMEZONE
# ============================================================

EASTERN = ZoneInfo(
    "America/New_York"
)


# ============================================================
# CURRENT GOLD CONTRACT
# ============================================================

GOLD_TICKER = "1OZV26.CMX"

GOLD_CONTRACT_NAME = (
    "1-Ounce Gold — October 2026"
)

GOLD_CME_SYMBOL = "1OZV6"


# ============================================================
# OTHER MARKET SYMBOLS
# ============================================================

DXY_TICKER = "DX-Y.NYB"

TREASURY_TICKER = "^TNX"


# ============================================================
# APP SETTINGS
# ============================================================

NEWS_MAX_AGE_HOURS = 48

PREDICTION_THRESHOLD = 5.00

PREDICTION_INTERVAL_MINUTES = 15

PREDICTION_HORIZONS = {
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120
}


# ============================================================
# REQUEST HEADERS
# ============================================================

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


# ============================================================
# GITHUB SETTINGS
# ============================================================

def get_secret(name, default=""):
    """
    Read from Streamlit Secrets first.

    Environment variables are used only as a fallback.
    """

    try:

        if name in st.secrets:

            value = st.secrets[name]

            if value is not None:

                return str(
                    value
                ).strip()

    except Exception:

        pass

    return os.getenv(
        name,
        default
    ).strip()


GITHUB_TOKEN = get_secret(
    "GITHUB_TOKEN"
)

GITHUB_REPO = get_secret(
    "GITHUB_REPO"
)

GITHUB_BRANCH = get_secret(
    "GITHUB_BRANCH",
    "main"
)

GITHUB_HISTORY_FILE = get_secret(
    "GITHUB_HISTORY_FILE",
    "prediction_history.csv"
)


# ============================================================
# HISTORY DATABASE COLUMNS
# ============================================================

HISTORY_COLUMNS = [
    "prediction_id",
    "timestamp_utc",
    "timestamp_et",
    "contract",
    "contract_name",
    "gold_price",
    "dxy_price",
    "dxy_pct",
    "treasury_yield",
    "treasury_pct",
    "macro_bias",
    "macro_confidence",
    "technical_bias",
    "technical_score",
    "overall_bias",
    "confidence",
    "support",
    "resistance",
    "ma20",
    "ma50",
    "target_15m",
    "target_30m",
    "target_1h",
    "target_2h",
    "result_15m",
    "result_30m",
    "result_1h",
    "result_2h",
    "price_15m",
    "price_30m",
    "price_1h",
    "price_2h",
    "checked_15m",
    "checked_30m",
    "checked_1h",
    "checked_2h"
]


# ============================================================
# GITHUB API HELPERS
# ============================================================

def github_headers():

    return {
        "Authorization":
            f"Bearer {GITHUB_TOKEN}",

        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            "2022-11-28"
    }


def github_file_url():

    return (
        "https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/"
        f"{GITHUB_HISTORY_FILE}"
    )


# ============================================================
# GITHUB CONNECTION TEST
# ============================================================

def test_github_connection():

    if not GITHUB_TOKEN:

        return (
            False,
            "GITHUB_TOKEN is missing from Streamlit Secrets."
        )

    if not GITHUB_REPO:

        return (
            False,
            "GITHUB_REPO is missing from Streamlit Secrets."
        )

    try:

        response = requests.get(
            (
                "https://api.github.com/repos/"
                f"{GITHUB_REPO}"
            ),
            headers=github_headers(),
            timeout=15
        )

        if response.status_code == 200:

            return (
                True,
                "GitHub authentication successful."
            )

        if response.status_code == 401:

            return (
                False,
                "GitHub rejected the token (401 Unauthorized). "
                "The token being supplied to the app is not "
                "being accepted by GitHub."
            )

        if response.status_code == 403:

            return (
                False,
                "GitHub returned 403 Forbidden. "
                "The token is recognized, but GitHub is "
                "blocking this request."
            )

        if response.status_code == 404:

            return (
                False,
                "GitHub returned 404. "
                "Check the repository name."
            )

        return (
            False,
            f"GitHub returned HTTP {response.status_code}."
        )

    except Exception as e:

        return (
            False,
            f"Could not contact GitHub: {e}"
        )


github_connected, github_message = (
    test_github_connection()
)


# ============================================================
# LOAD HISTORY FROM GITHUB
# ============================================================

def load_history():

    if not github_connected:

        return pd.DataFrame(
            columns=HISTORY_COLUMNS
        )

    try:

        response = requests.get(
            github_file_url(),
            headers=github_headers(),
            params={
                "ref":
                    GITHUB_BRANCH
            },
            timeout=15
        )

        if response.status_code == 404:

            return pd.DataFrame(
                columns=HISTORY_COLUMNS
            )

        response.raise_for_status()

        data = response.json()

        encoded_content = data.get(
            "content",
            ""
        )

        if not encoded_content:

            return pd.DataFrame(
                columns=HISTORY_COLUMNS
            )

        decoded = base64.b64decode(
            encoded_content
        ).decode(
            "utf-8"
        )

        df = pd.read_csv(
            StringIO(
                decoded
            )
        )

        for column in HISTORY_COLUMNS:

            if column not in df.columns:

                df[column] = ""

        return df[
            HISTORY_COLUMNS
        ]

    except Exception as e:

        st.error(
            "Could not load prediction history "
            f"from GitHub: {e}"
        )

        return pd.DataFrame(
            columns=HISTORY_COLUMNS
        )


# ============================================================
# SAVE HISTORY TO GITHUB
# ============================================================

def save_history(
    df,
    commit_message
):

    if not github_connected:

        return False

    try:

        csv_content = df.to_csv(
            index=False
        )

        encoded_content = (
            base64.b64encode(
                csv_content.encode(
                    "utf-8"
                )
            )
            .decode(
                "utf-8"
            )
        )

        get_response = requests.get(
            github_file_url(),
            headers=github_headers(),
            params={
                "ref":
                    GITHUB_BRANCH
            },
            timeout=15
        )

        existing_sha = None

        if get_response.status_code == 200:

            existing_sha = (
                get_response.json()
                .get("sha")
            )

        elif get_response.status_code != 404:

            get_response.raise_for_status()

        payload = {
            "message":
                commit_message,

            "content":
                encoded_content,

            "branch":
                GITHUB_BRANCH
        }

        if existing_sha:

            payload["sha"] = existing_sha

        response = requests.put(
            github_file_url(),
            headers=github_headers(),
            json=payload,
            timeout=20
        )

        response.raise_for_status()

        return True

    except Exception as e:

        st.error(
            "Could not save prediction history "
            f"to GitHub: {e}"
        )

        return False


# ============================================================
# YAHOO FINANCE QUOTE
# ============================================================

def yf_quote(
    ticker,
    multiplier=1.0
):

    try:

        stock = yf.Ticker(
            ticker
        )

        intraday = stock.history(
            period="2d",
            interval="1m",
            auto_adjust=False
        )

        if (
            not intraday.empty
            and "Close" in intraday.columns
        ):

            closes = pd.to_numeric(
                intraday["Close"],
                errors="coerce"
            ).dropna()

        else:

            closes = pd.Series(
                dtype=float
            )

        if closes.empty:

            daily = stock.history(
                period="10d",
                interval="1d",
                auto_adjust=False
            )

            if (
                daily.empty
                or "Close" not in daily.columns
            ):

                return {
                    "error":
                        "No Yahoo Finance data."
                }

            closes = pd.to_numeric(
                daily["Close"],
                errors="coerce"
            ).dropna()

        if closes.empty:

            return {
                "error":
                    "No valid price data."
            }

        raw_price = float(
            closes.iloc[-1]
        )

        daily = stock.history(
            period="10d",
            interval="1d",
            auto_adjust=False
        )

        if (
            not daily.empty
            and "Close" in daily.columns
        ):

            daily_closes = pd.to_numeric(
                daily["Close"],
                errors="coerce"
            ).dropna()

        else:

            daily_closes = pd.Series(
                dtype=float
            )

        if len(daily_closes) >= 2:

            previous_raw = float(
                daily_closes.iloc[-2]
            )

        else:

            previous_raw = raw_price

        price = (
            raw_price
            * multiplier
        )

        previous_close = (
            previous_raw
            * multiplier
        )

        change = (
            price
            - previous_close
        )

        if previous_close != 0:

            pct = (
                (
                    price
                    / previous_close
                ) - 1
            ) * 100

        else:

            pct = 0.0

        return {
            "price":
                price,

            "previous_close":
                previous_close,

            "change":
                change,

            "pct":
                pct
        }

    except Exception as e:

        return {
            "error":
                str(e)
        }


# ============================================================
# 10-YEAR TREASURY
# ============================================================

def get_10y_treasury():

    # ^TNX is quoted as 10x the actual yield.
    # Example: 44.50 -> 4.45%
    return yf_quote(
        TREASURY_TICKER,
        multiplier=0.1
    )


# ============================================================
# GOLD TECHNICAL DATA
# ============================================================

def get_gold_technical_data():

    try:

        ticker = yf.Ticker(
            GOLD_TICKER
        )

        data = ticker.history(
            period="5d",
            interval="15m",
            auto_adjust=False
        )

        if data.empty:

            return {
                "error":
                    "No Gold technical data."
            }

        for column in [
            "Open",
            "High",
            "Low",
            "Close"
        ]:

            data[column] = pd.to_numeric(
                data[column],
                errors="coerce"
            )

        data = data.dropna(
            subset=[
                "High",
                "Low",
                "Close"
            ]
        )

        if data.empty:

            return {
                "error":
                    "No valid Gold technical data."
            }

        current_price = float(
            data[
                "Close"
            ].iloc[-1]
        )

        ma20 = float(
            data[
                "Close"
            ]
            .rolling(20)
            .mean()
            .iloc[-1]
        )

        ma50 = float(
            data[
                "Close"
            ]
            .rolling(50)
            .mean()
            .iloc[-1]
        )

        if data.index.tz is not None:

            eastern_index = (
                data.index
                .tz_convert(
                    EASTERN
                )
            )

        else:

            eastern_index = (
                data.index
                .tz_localize(
                    "UTC"
                )
                .tz_convert(
                    EASTERN
                )
            )

        dates = eastern_index.date

        today = datetime.now(
            EASTERN
        ).date()

        today_data = data[
            dates == today
        ]

        if today_data.empty:

            today_data = data.tail(
                min(
                    26,
                    len(data)
                )
            )

        today_high = float(
            today_data[
                "High"
            ].max()
        )

        today_low = float(
            today_data[
                "Low"
            ].min()
        )

        previous_dates = sorted(
            set(
                date
                for date in dates
                if date < today
            )
        )

        if previous_dates:

            previous_date = (
                previous_dates[-1]
            )

            previous_data = data[
                dates == previous_date
            ]

        else:

            previous_data = data.tail(
                min(
                    26,
                    len(data)
                )
            )

        previous_day_high = float(
            previous_data[
                "High"
            ].max()
        )

        previous_day_low = float(
            previous_data[
                "Low"
            ].min()
        )

        recent = data.tail(
            min(
                100,
                len(data)
            )
        )

        highs = recent[
            "High"
        ].tolist()

        lows = recent[
            "Low"
        ].tolist()

        swing_highs = []

        swing_lows = []

        for i in range(
            2,
            len(highs) - 2
        ):

            if (
                highs[i]
                >= highs[i - 1]
                and highs[i]
                >= highs[i - 2]
                and highs[i]
                >= highs[i + 1]
                and highs[i]
                >= highs[i + 2]
            ):

                swing_highs.append(
                    highs[i]
                )

        for i in range(
            2,
            len(lows) - 2
        ):

            if (
                lows[i]
                <= lows[i - 1]
                and lows[i]
                <= lows[i - 2]
                and lows[i]
                <= lows[i + 1]
                and lows[i]
                <= lows[i + 2]
            ):

                swing_lows.append(
                    lows[i]
                )

        resistance_candidates = [
            x
            for x in (
                swing_highs
                + [previous_day_high]
            )
            if x > current_price
        ]

        support_candidates = [
            x
            for x in (
                swing_lows
                + [previous_day_low]
            )
            if x < current_price
        ]

        resistance = (
            min(
                resistance_candidates
            )
            if resistance_candidates
            else today_high
        )

        support = (
            max(
                support_candidates
            )
            if support_candidates
            else today_low
        )

        return {
            "price":
                current_price,

            "today_high":
                today_high,

            "today_low":
                today_low,

            "previous_day_high":
                previous_day_high,

            "previous_day_low":
                previous_day_low,

            "ma20":
                ma20,

            "ma50":
                ma50,

            "support":
                support,

            "resistance":
                resistance
        }

    except Exception as e:

        return {
            "error":
                str(e)
        }


# ============================================================
# TECHNICAL SCORE
# ============================================================

def technical_score(
    technical
):

    if (
        not technical
        or "price" not in technical
    ):

        return (
            "UNAVAILABLE",
            0,
            []
        )

    price = technical["price"]

    ma20 = technical["ma20"]

    ma50 = technical["ma50"]

    support = technical["support"]

    resistance = technical["resistance"]

    score = 0

    reasons = []

    if price > ma20:

        score += 1

        reasons.append(
            "Gold is above its "
            "20-period moving average."
        )

    else:

        score -= 1

        reasons.append(
            "Gold is below its "
            "20-period moving average."
        )

    if price > ma50:

        score += 1

        reasons.append(
            "Gold is above its "
            "50-period moving average."
        )

    else:

        score -= 1

        reasons.append(
            "Gold is below its "
            "50-period moving average."
        )

    if ma20 > ma50:

        score += 1

        reasons.append(
            "The 20-period average is "
            "above the 50-period average."
        )

    elif ma20 < ma50:

        score -= 1

        reasons.append(
            "The 20-period average is "
            "below the 50-period average."
        )

    else:

        reasons.append(
            "The moving averages are flat."
        )

    if score >= 2:

        bias = "BULLISH"

    elif score <= -2:

        bias = "BEARISH"

    else:

        bias = "MIXED"

    resistance_distance = (
        (
            resistance - price
        )
        / price
        * 100
        if resistance > price
        else 0
    )

    support_distance = (
        (
            price - support
        )
        / price
        * 100
        if support < price
        else 0
    )

    if (
        0 < resistance_distance <= 0.30
    ):

        reasons.append(
            "⚠️ Gold is very close "
            "to resistance."
        )

    elif (
        0 < resistance_distance <= 0.60
    ):

        reasons.append(
            "Gold is approaching resistance."
        )

    if (
        0 < support_distance <= 0.30
    ):

        reasons.append(
            "⚠️ Gold is very close "
            "to support."
        )

    elif (
        0 < support_distance <= 0.60
    ):

        reasons.append(
            "Gold is approaching support."
        )

    return (
        bias,
        score,
        reasons
    )


# ============================================================
# MACRO SCORE
# ============================================================

def macro_score(
    gold,
    dxy,
    treasury
):

    score = 0

    reasons = []

    if gold and "pct" in gold:

        pct = gold["pct"]

        if pct > 0.50:

            score += 3

            reasons.append(
                "Gold is rising strongly."
            )

        elif pct > 0.05:

            score += 2

            reasons.append(
                "Gold is rising."
            )

        elif pct < -0.50:

            score -= 3

            reasons.append(
                "Gold is falling strongly."
            )

        elif pct < -0.05:

            score -= 2

            reasons.append(
                "Gold is falling."
            )

        else:

            reasons.append(
                "Gold is relatively flat."
            )

    else:

        reasons.append(
            "Gold quote unavailable."
        )

    if dxy and "pct" in dxy:

        pct = dxy["pct"]

        if pct < -0.20:

            score += 3

            reasons.append(
                "DXY is falling strongly, "
                "supporting gold."
            )

        elif pct < -0.03:

            score += 2

            reasons.append(
                "DXY is falling, "
                "supporting gold."
            )

        elif pct > 0.20:

            score -= 3

            reasons.append(
                "DXY is rising strongly, "
                "pressuring gold."
            )

        elif pct > 0.03:

            score -= 2

            reasons.append(
                "DXY is rising, "
                "which is a headwind for gold."
            )

        else:

            reasons.append(
                "DXY is relatively flat."
            )

    else:

        reasons.append(
            "DXY quote unavailable."
        )

    if treasury and "pct" in treasury:

        pct = treasury["pct"]

        if pct < -0.10:

            score += 2

            reasons.append(
                "The 10Y yield is falling, "
                "supporting gold."
            )

        elif pct < -0.02:

            score += 1

            reasons.append(
                "The 10Y yield is slightly lower."
            )

        elif pct > 0.10:

            score -= 2

            reasons.append(
                "The 10Y yield is rising, "
                "pressuring gold."
            )

        elif pct > 0.02:

            score -= 1

            reasons.append(
                "The 10Y yield is slightly higher."
            )

        else:

            reasons.append(
                "The 10Y yield is relatively flat."
            )

    else:

        reasons.append(
            "10Y Treasury data unavailable."
        )

    if score >= 3:

        bias = "BULLISH"

    elif score <= -3:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL / WAIT"

    confidence = round(
        5 + (
            abs(score)
            / 8
        ) * 5
    )

    confidence = max(
        1,
        min(
            10,
            confidence
        )
    )

    return (
        bias,
        confidence,
        reasons,
        score
    )


# ============================================================
# COMBINE MACRO + TECHNICAL
# ============================================================

def combined_bias(
    macro_bias,
    macro_confidence,
    technical_bias
):

    score = 0

    if macro_bias == "BULLISH":

        score += 2

    elif macro_bias == "BEARISH":

        score -= 2

    if technical_bias == "BULLISH":

        score += 2

    elif technical_bias == "BEARISH":

        score -= 2

    if score >= 3:

        bias = "BULLISH"

    elif score <= -3:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL / WAIT"

    confidence = macro_confidence

    if (
        macro_bias == "BULLISH"
        and technical_bias == "BULLISH"
    ):

        confidence += 1

    elif (
        macro_bias == "BEARISH"
        and technical_bias == "BEARISH"
    ):

        confidence += 1

    elif (
        macro_bias != "NEUTRAL / WAIT"
        and technical_bias == "MIXED"
    ):

        confidence -= 1

    confidence = max(
        1,
        min(
            10,
            confidence
        )
    )

    return (
        bias,
        confidence
    )


# ============================================================
# PREDICTION ID
# ============================================================

def prediction_id():

    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d%H%M%S%f"
    )


# ============================================================
# CREATE PREDICTION
# ============================================================

def create_prediction(
    history,
    gold,
    dxy,
    treasury,
    technical,
    macro_bias,
    macro_confidence,
    technical_bias,
    technical_score_value,
    overall_bias,
    overall_confidence
):

    if (
        not gold
        or "price" not in gold
        or not technical
        or "price" not in technical
    ):

        return history

    now_utc = datetime.now(
        timezone.utc
    )

    now_et = now_utc.astimezone(
        EASTERN
    )

    price = float(
        gold["price"]
    )

    if overall_bias == "BULLISH":

        target = (
            price
            + PREDICTION_THRESHOLD
        )

    elif overall_bias == "BEARISH":

        target = (
            price
            - PREDICTION_THRESHOLD
        )

    else:

        target = price

    row = {
        "prediction_id":
            prediction_id(),

        "timestamp_utc":
            now_utc.isoformat(),

        "timestamp_et":
            now_et.strftime(
                "%Y-%m-%d %I:%M:%S %p ET"
            ),

        "contract":
            GOLD_TICKER,

        "contract_name":
            GOLD_CONTRACT_NAME,

        "gold_price":
            price,

        "dxy_price":
            dxy.get(
                "price",
                ""
            )
            if dxy
            else "",

        "dxy_pct":
            dxy.get(
                "pct",
                ""
            )
            if dxy
            else "",

        "treasury_yield":
            treasury.get(
                "price",
                ""
            )
            if treasury
            else "",

        "treasury_pct":
            treasury.get(
                "pct",
                ""
            )
            if treasury
            else "",

        "macro_bias":
            macro_bias,

        "macro_confidence":
            macro_confidence,

        "technical_bias":
            technical_bias,

        "technical_score":
            technical_score_value,

        "overall_bias":
            overall_bias,

        "confidence":
            overall_confidence,

        "support":
            technical.get(
                "support",
                ""
            ),

        "resistance":
            technical.get(
                "resistance",
                ""
            ),

        "ma20":
            technical.get(
                "ma20",
                ""
            ),

        "ma50":
            technical.get(
                "ma50",
                ""
            ),

        "target_15m":
            target,

        "target_30m":
            target,

        "target_1h":
            target,

        "target_2h":
            target,

        "result_15m":
            "",

        "result_30m":
            "",

        "result_1h":
            "",

        "result_2h":
            "",

        "price_15m":
            "",

        "price_30m":
            "",

        "price_1h":
            "",

        "price_2h":
            "",

        "checked_15m":
            "",

        "checked_30m":
            "",

        "checked_1h":
            "",

        "checked_2h":
            ""
    }

    new_row = pd.DataFrame(
        [row],
        columns=HISTORY_COLUMNS
    )

    return pd.concat(
        [
            history,
            new_row
        ],
        ignore_index=True
    )


# ============================================================
# GET LATEST PREDICTION
# ============================================================

def get_latest_prediction(
    history
):

    if history.empty:

        return None

    current = history[
        history["contract"]
        == GOLD_TICKER
    ].copy()

    if current.empty:

        return None

    current[
        "timestamp_utc"
    ] = pd.to_datetime(
        current[
            "timestamp_utc"
        ],
        utc=True,
        errors="coerce"
    )

    current = current.dropna(
        subset=[
            "timestamp_utc"
        ]
    )

    if current.empty:

        return None

    current = current.sort_values(
        "timestamp_utc"
    )

    return current.iloc[-1]


# ============================================================
# CHECK PAST PREDICTIONS
# ============================================================

def check_predictions(
    history
):

    if history.empty:

        return (
            history,
            False
        )

    changed = False

    now = datetime.now(
        timezone.utc
    )

    timestamps = pd.to_datetime(
        history[
            "timestamp_utc"
        ],
        utc=True,
        errors="coerce"
    )

    for index in history.index:

        timestamp = timestamps.loc[
            index
        ]

        if pd.isna(timestamp):

            continue

        age_minutes = (
            now
            - timestamp.to_pydatetime()
        ).total_seconds() / 60

        original_price = pd.to_numeric(
            pd.Series(
                [
                    history.at[
                        index,
                        "gold_price"
                    ]
                ]
            ),
            errors="coerce"
        ).iloc[0]

        if pd.isna(
            original_price
        ):

            continue

        bias = history.at[
            index,
            "overall_bias"
        ]

        for horizon_name, minutes in (
            PREDICTION_HORIZONS.items()
        ):

            result_column = (
                f"result_{horizon_name}"
            )

            price_column = (
                f"price_{horizon_name}"
            )

            checked_column = (
                f"checked_{horizon_name}"
            )

            existing = history.at[
                index,
                result_column
            ]

            if (
                pd.notna(existing)
                and str(
                    existing
                ).strip() != ""
            ):

                continue

            if age_minutes < minutes:

                continue

            try:

                ticker = yf.Ticker(
                    history.at[
                        index,
                        "contract"
                    ]
                )

                data = ticker.history(
                    period="5d",
                    interval="15m",
                    auto_adjust=False
                )

                if (
                    data.empty
                    or "Close"
                    not in data.columns
                ):

                    continue

                data["Close"] = pd.to_numeric(
                    data["Close"],
                    errors="coerce"
                )

                data = data.dropna(
                    subset=[
                        "Close"
                    ]
                )

                if data.empty:

                    continue

                if data.index.tz is None:

                    data.index = (
                        data.index
                        .tz_localize(
                            "UTC"
                        )
                    )

                else:

                    data.index = (
                        data.index
                        .tz_convert(
                            "UTC"
                        )
                    )

                target_time = (
                    timestamp
                    + pd.Timedelta(
                        minutes=minutes
                    )
                )

                differences = abs(
                    data.index
                    - target_time
                )

                position = differences.argmin()

                if (
                    differences[position]
                    .total_seconds()
                    > 20 * 60
                ):

                    continue

                future_price = float(
                    data[
                        "Close"
                    ].iloc[position]
                )

                move = (
                    future_price
                    - float(
                        original_price
                    )
                )

                if bias == "BULLISH":

                    if move >= PREDICTION_THRESHOLD:

                        result = "CORRECT"

                    elif move <= -PREDICTION_THRESHOLD:

                        result = "WRONG"

                    else:

                        result = "FLAT"

                elif bias == "BEARISH":

                    if move <= -PREDICTION_THRESHOLD:

                        result = "CORRECT"

                    elif move >= PREDICTION_THRESHOLD:

                        result = "WRONG"

                    else:

                        result = "FLAT"

                else:

                    if abs(
                        move
                    ) < PREDICTION_THRESHOLD:

                        result = "CORRECT"

                    else:

                        result = "MOVED"

                history.at[
                    index,
                    result_column
                ] = result

                history.at[
                    index,
                    price_column
                ] = future_price

                history.at[
                    index,
                    checked_column
                ] = datetime.now(
                    timezone.utc
                ).isoformat()

                changed = True

            except Exception:

                continue

    return (
        history,
        changed
    )


# ============================================================
# PERFORMANCE
# ============================================================

def performance_stats(
    history,
    contract=None
):

    if history.empty:

        return {}

    df = history.copy()

    if contract:

        df = df[
            df["contract"]
            == contract
        ]

    results = {}

    for horizon in PREDICTION_HORIZONS:

        column = (
            f"result_{horizon}"
        )

        values = (
            df[column]
            .astype(str)
            .str.upper()
        )

        correct = (
            values == "CORRECT"
        ).sum()

        wrong = (
            values == "WRONG"
        ).sum()

        total = (
            correct
            + wrong
        )

        results[horizon] = {
            "correct":
                int(correct),

            "wrong":
                int(wrong),

            "total":
                int(total),

            "accuracy":
                (
                    correct
                    / total
                    * 100
                    if total
                    else None
                )
        }

    return results


# ============================================================
# NEWS
# ============================================================

def parse_news_date(
    value
):

    if not value:

        return None

    try:

        parsed = pd.to_datetime(
            value,
            utc=True,
            errors="coerce"
        )

        if pd.isna(parsed):

            return None

        return parsed.to_pydatetime()

    except Exception:

        return None


def news():

    articles = []

    now = datetime.now(
        timezone.utc
    )

    cutoff = (
        now
        - timedelta(
            hours=NEWS_MAX_AGE_HOURS
        )
    )

    # --------------------------------------------------------
    # NewsAPI
    # --------------------------------------------------------

    newsapi_key = get_secret(
        "NEWSAPI_KEY"
    )

    if newsapi_key:

        try:

            response = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": (
                        '"gold" OR '
                        '"gold futures" OR '
                        '"Federal Reserve" OR '
                        '"Treasury yields" OR '
                        '"US dollar" OR '
                        '"inflation"'
                    ),
                    "language":
                        "en",

                    "sortBy":
                        "publishedAt",

                    "pageSize":
                        50,

                    "apiKey":
                        newsapi_key
                },
                headers=REQUEST_HEADERS,
                timeout=15
            )

            if response.status_code == 200:

                data = response.json()

                for article in data.get(
                    "articles",
                    []
                ):

                    published = parse_news_date(
                        article.get(
                            "publishedAt"
                        )
                    )

                    if (
                        published is None
                        or published < cutoff
                        or published > now + timedelta(
                            minutes=5
                        )
                    ):

                        continue

                    articles.append(
                        {
                            "published":
                                published,

                            "title":
                                article.get(
                                    "title",
                                    ""
                                ),

                            "url":
                                article.get(
                                    "url",
                                    ""),

                            "source":
                                article.get(
                                    "source",
                                    {}
                                ).get(
                                    "name",
                                    ""
                                )
                        }
                    )

        except Exception:

            pass

    # --------------------------------------------------------
    # Google News RSS fallback / supplement
    # --------------------------------------------------------

    searches = [
        "gold futures gold price",
        "gold Federal Reserve Fed",
        "gold Treasury yields",
        "gold US dollar DXY",
        "gold inflation CPI PCE PPI"
    ]

    for search_term in searches:

        try:

            url = (
                "https://news.google.com/rss/search?"
                f"q={quote(search_term)}"
                "&hl=en-US"
                "&gl=US"
                "&ceid=US:en"
            )

            feed = feedparser.parse(
                url
            )

            for entry in feed.entries:

                published = parse_news_date(
                    entry.get(
                        "published",
                        ""
                    )
                )

                if (
                    published is None
                    or published < cutoff
                    or published > now + timedelta(
                        minutes=5
                    )
                ):

                    continue

                source = ""

                try:

                    source = entry.source.get(
                        "title",
                        ""
                    )

                except Exception:

                    pass

                articles.append(
                    {
                        "published":
                            published,

                        "title":
                            entry.get(
                                "title",
                                ""
                            ),

                        "url":
                            entry.get(
                                "link",
                                ""
                            ),

                        "source":
                            source
                    }
                )

        except Exception:

            continue

    # --------------------------------------------------------
    # Remove duplicates
    # --------------------------------------------------------

    unique = {}

    for article in articles:

        key = (
            article["title"]
            .strip()
            .lower()
        )

        if key and key not in unique:

            unique[key] = article

    articles = list(
        unique.values()
    )

    articles.sort(
        key=lambda x:
            x["published"],
        reverse=True
    )

    return articles[:20]


# ============================================================
# LOAD MARKET DATA
# ============================================================

gold = yf_quote(
    GOLD_TICKER
)

dxy = yf_quote(
    DXY_TICKER
)

treasury = get_10y_treasury()

technical = get_gold_technical_data()

articles = news()


# ============================================================
# CALCULATE SCORES
# ============================================================

(
    macro_bias,
    macro_confidence,
    macro_reasons,
    macro_total
) = macro_score(
    gold,
    dxy,
    treasury
)

(
    technical_bias,
    technical_total,
    technical_reasons
) = technical_score(
    technical
)

(
    overall_bias,
    overall_confidence
) = combined_bias(
    macro_bias,
    macro_confidence,
    technical_bias
)


# ============================================================
# LOAD PREDICTION HISTORY
# ============================================================

history = load_history()


# ============================================================
# CREATE NEW PREDICTION
# ============================================================

latest = get_latest_prediction(
    history
)

should_create = False

if latest is None:

    should_create = True

else:

    latest_time = pd.to_datetime(
        latest[
            "timestamp_utc"
        ],
        utc=True,
        errors="coerce"
    )

    if not pd.isna(
        latest_time
    ):

        age_minutes = (
            datetime.now(
                timezone.utc
            )
            - latest_time.to_pydatetime()
        ).total_seconds() / 60

        if age_minutes >= (
            PREDICTION_INTERVAL_MINUTES
        ):

            should_create = True


if should_create:

    history = create_prediction(
        history,
        gold,
        dxy,
        treasury,
        technical,
        macro_bias,
        macro_confidence,
        technical_bias,
        technical_total,
        overall_bias,
        overall_confidence
    )

    save_history(
        history,
        "New Gold Market Monitor prediction"
    )


# ============================================================
# CHECK COMPLETED PREDICTIONS
# ============================================================

history, changed = check_predictions(
    history
)

if changed:

    save_history(
        history,
        "Update Gold Market Monitor prediction results"
    )


# ============================================================
# PAGE TITLE
# ============================================================

st.title(
    "🥇 Gold Market Monitor — MVP"
)

st.caption(
    "Automated market-monitoring dashboard. "
    "It does NOT place trades."
)

st.info(
    f"Currently monitoring: "
    f"**{GOLD_CONTRACT_NAME}**"
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "Settings"
)

refresh = st.sidebar.selectbox(
    "Refresh interval",
    [
        15,
        30,
        60,
        120,
        300,
        900
    ],
    index=2,
    format_func=lambda x:
        (
            f"{x} seconds"
            if x < 60
            else (
                "1 minute"
                if x == 60
                else f"{x // 60} minutes"
            )
        )
)

st.sidebar.info(
    "The dashboard refreshes automatically. "
    "A new prediction snapshot is normally "
    "created every 15 minutes."
)

st.sidebar.markdown(
    f"""
### Current Contract

🥇 **{GOLD_CONTRACT_NAME}**

Yahoo:

`{GOLD_TICKER}`

CME:

`{GOLD_CME_SYMBOL}`
"""
)

if github_connected:

    st.sidebar.success(
        "💾 GitHub storage: CONNECTED"
    )

else:

    st.sidebar.error(
        "💾 GitHub storage: NOT CONNECTED"
    )


# ============================================================
# GITHUB DIAGNOSTICS
# ============================================================

with st.sidebar.expander(
    "GitHub connection details"
):

    if GITHUB_TOKEN:

        st.write(
            "Token detected: ✅"
        )

        # We deliberately DO NOT display the token.

        if GITHUB_TOKEN.startswith(
            "github_pat_"
        ):

            st.write(
                "Token type: Fine-grained ✅"
            )

        else:

            st.write(
                "Token type: Not recognized "
                "as a fine-grained token ⚠️"
            )

    else:

        st.write(
            "Token detected: ❌"
        )

    st.write(
        f"Repository: `{GITHUB_REPO or 'MISSING'}`"
    )

    st.write(
        f"Branch: `{GITHUB_BRANCH}`"
    )

    st.write(
        f"History file: `{GITHUB_HISTORY_FILE}`"
    )

    st.write(
        github_message
    )


# ============================================================
# TOP METRICS
# ============================================================

col1, col2, col3, col4 = st.columns(4)


if gold and "price" in gold:

    col1.metric(
        "🥇 Gold — Oct 2026",
        f"${gold['price']:,.2f}",
        f"{gold['pct']:+.2f}%"
    )

else:

    col1.metric(
        "🥇 Gold — Oct 2026",
        "Unavailable"
    )


if dxy and "price" in dxy:

    col2.metric(
        "💵 DXY",
        f"{dxy['price']:.3f}",
        f"{dxy['pct']:+.2f}%"
    )

else:

    col2.metric(
        "💵 DXY",
        "Unavailable"
    )


if treasury and "price" in treasury:

    col3.metric(
        "🇺🇸 10Y Treasury",
        f"{treasury['price']:.2f}%",
        f"{treasury['pct']:+.2f}%"
    )

else:

    col3.metric(
        "🇺🇸 10Y Treasury",
        "Unavailable"
    )


col4.metric(
    "📊 Overall Bias",
    overall_bias,
    f"Confidence {overall_confidence}/10"
)


# ============================================================
# CURRENT ASSESSMENT
# ============================================================

st.subheader(
    "🎯 Current Market Assessment"
)

a1, a2 = st.columns(2)

with a1:

    st.metric(
        "Macro",
        macro_bias,
        f"Confidence {macro_confidence}/10"
    )

with a2:

    st.metric(
        "Technical",
        technical_bias
    )


# ============================================================
# TECHNICAL LEVELS
# ============================================================

st.subheader(
    "📐 Gold Technical Levels"
)

if technical and "price" in technical:

    l1, l2, l3, l4 = st.columns(4)

    l1.metric(
        "Support",
        f"${technical['support']:,.2f}"
    )

    l2.metric(
        "Resistance",
        f"${technical['resistance']:,.2f}"
    )

    l3.metric(
        "20 MA",
        f"${technical['ma20']:,.2f}"
    )

    l4.metric(
        "50 MA",
        f"${technical['ma50']:,.2f}"
    )

    h1, h2, h3, h4 = st.columns(4)

    h1.metric(
        "Today's High",
        f"${technical['today_high']:,.2f}"
    )

    h2.metric(
        "Today's Low",
        f"${technical['today_low']:,.2f}"
    )

    h3.metric(
        "Previous Day High",
        f"${technical['previous_day_high']:,.2f}"
    )

    h4.metric(
        "Previous Day Low",
        f"${technical['previous_day_low']:,.2f}"
    )

else:

    st.warning(
        "Technical Gold data unavailable."
    )


# ============================================================
# ANALYSIS
# ============================================================

st.subheader(
    "🔎 What the Monitor Sees"
)

for reason in technical_reasons:

    st.write(
        "• " + reason
    )

for reason in macro_reasons:

    st.write(
        "• " + reason
    )


if overall_bias == "BULLISH":

    st.success(
        f"🟢 Overall environment: "
        f"BULLISH — "
        f"Confidence {overall_confidence}/10"
    )

elif overall_bias == "BEARISH":

    st.error(
        f"🔴 Overall environment: "
        f"BEARISH — "
        f"Confidence {overall_confidence}/10"
    )

else:

    st.warning(
        f"🟡 Overall environment: "
        f"NEUTRAL / WAIT — "
        f"Confidence {overall_confidence}/10"
    )


# ============================================================
# PREDICTION TRACKER
# ============================================================

st.subheader(
    "🧪 Prediction Tracker"
)

st.caption(
    "The monitor records its own predictions "
    "and later checks whether the market moved "
    "in the predicted direction."
)

current_history = history[
    history["contract"]
    == GOLD_TICKER
].copy()

if not current_history.empty:

    current_history[
        "timestamp_utc"
    ] = pd.to_datetime(
        current_history[
            "timestamp_utc"
        ],
        utc=True,
        errors="coerce"
    )

    current_history = (
        current_history
        .sort_values(
            "timestamp_utc",
            ascending=False
        )
    )

    display_columns = [
        "timestamp_et",
        "gold_price",
        "overall_bias",
        "confidence",
        "macro_bias",
        "technical_bias",
        "result_15m",
        "result_30m",
        "result_1h",
        "result_2h"
    ]

    display = current_history[
        display_columns
    ].head(15)

    display = display.rename(
        columns={
            "timestamp_et":
                "Prediction Time",

            "gold_price":
                "Gold Price",

            "overall_bias":
                "Signal",

            "confidence":
                "Confidence",

            "macro_bias":
                "Macro",

            "technical_bias":
                "Technical",

            "result_15m":
                "15m",

            "result_30m":
                "30m",

            "result_1h":
                "1 Hour",

            "result_2h":
                "2 Hours"
        }
    )

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "Waiting for the first prediction."
    )


# ============================================================
# PERFORMANCE
# ============================================================

st.subheader(
    "📊 Prediction Performance"
)

stats = performance_stats(
    history,
    GOLD_TICKER
)

p1, p2, p3, p4 = st.columns(4)

for column, horizon, label in [
    (
        p1,
        "15m",
        "15 Minute"
    ),
    (
        p2,
        "30m",
        "30 Minute"
    ),
    (
        p3,
        "1h",
        "1 Hour"
    ),
    (
        p4,
        "2h",
        "2 Hour"
    )
]:

    item = stats.get(
        horizon,
        {}
    )

    accuracy = item.get(
        "accuracy"
    )

    if accuracy is not None:

        column.metric(
            label,
            f"{accuracy:.1f}%",
            f"{item['correct']} correct / "
            f"{item['total']} tested"
        )

    else:

        column.metric(
            label,
            "Not enough data"
        )


# ============================================================
# DATABASE STATUS
# ============================================================

st.subheader(
    "💾 Prediction Database"
)

db1, db2, db3 = st.columns(3)

db1.metric(
    "Total Predictions",
    len(history)
)

db2.metric(
    "October 2026",
    len(
        history[
            history["contract"]
            == GOLD_TICKER
        ]
    )
)

db3.metric(
    "Contracts Tracked",
    (
        history["contract"].nunique()
        if not history.empty
        else 0
    )
)

if github_connected:

    st.success(
        "GitHub persistent storage is connected. "
        "Prediction history will survive contract rolls."
    )

else:

    st.error(
        "GitHub persistent storage is not connected."
    )


# ============================================================
# NEWS
# ============================================================

st.subheader(
    "📰 Recent Gold / Macro News"
)

if articles:

    st.caption(
        f"Only articles from the last "
        f"{NEWS_MAX_AGE_HOURS} hours are shown. "
        "All timestamps are converted to Eastern Time."
    )

    for article in articles[:10]:

        published = article[
            "published"
        ]

        eastern_time = (
            published
            .astimezone(
                EASTERN
            )
        )

        age_minutes = int(
            (
                datetime.now(
                    timezone.utc
                )
                - published
            ).total_seconds()
            / 60
        )

        if age_minutes < 1:

            age_text = "just now"

        elif age_minutes < 60:

            age_text = (
                f"{age_minutes}m ago"
            )

        elif age_minutes < 1440:

            age_text = (
                f"{age_minutes // 60}h ago"
            )

        else:

            age_text = (
                f"{age_minutes // 1440}d ago"
            )

        source = article.get(
            "source",
            ""
        )

        if source:

            source_text = (
                f" • {source}"
            )

        else:

            source_text = ""

        st.markdown(
            f"**[{article['title']}]"
            f"({article['url']})**  \n"
            f"🕒 {age_text} — "
            f"{eastern_time.strftime('%b %d, %Y %I:%M %p ET')}"
            f"{source_text}"
        )

        st.divider()

else:

    st.info(
        "No recent headlines found."
    )


# ============================================================
# DATA SOURCES
# ============================================================

with st.expander(
    "Data sources"
):

    st.write(
        f"🥇 Gold: Yahoo Finance — "
        f"{GOLD_TICKER}"
    )

    st.write(
        "💵 DXY: Yahoo Finance — DX-Y.NYB"
    )

    st.write(
        "🇺🇸 10Y Treasury: Yahoo Finance — ^TNX"
    )

    st.write(
        "📰 News: NewsAPI / Google News RSS"
    )

    st.write(
        f"💾 History: GitHub — "
        f"{GITHUB_HISTORY_FILE}"
    )


# ============================================================
# REFRESH
# ============================================================

now_et = datetime.now(
    EASTERN
)

st.caption(
    "Last refresh: "
    + now_et.strftime(
        "%Y-%m-%d %I:%M:%S %p ET"
    )
)

st.caption(
    f"Automatic refresh every "
    f"{refresh} seconds."
)

time.sleep(
    refresh
)

st.rerun()
