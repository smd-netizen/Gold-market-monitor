import os
import time
import base64
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
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
# CONTRACT SETTINGS
# ============================================================
# CURRENT CONTRACT:
#
# 1-Ounce Gold — October 2026
#
# When we eventually roll contracts, these are the ONLY
# values we should normally need to change.
#
# IMPORTANT:
# Historical predictions are tagged with the contract and
# will remain in the GitHub database.
# ============================================================

GOLD_TICKER = "1OZV26.CMX"
GOLD_CONTRACT_NAME = "1-Ounce Gold — October 2026"
GOLD_CME_SYMBOL = "1OZV6"


# ============================================================
# OTHER MARKET SYMBOLS
# ============================================================

DXY_TICKER = "DX-Y.NYB"
TREASURY_TICKER = "^TNX"


# ============================================================
# SETTINGS
# ============================================================

NEWS_MAX_AGE_HOURS = 48

PREDICTION_HORIZONS = {
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120
}

PREDICTION_THRESHOLD = 5.00

PREDICTION_INTERVAL_MINUTES = 15

EASTERN = ZoneInfo(
    "America/New_York"
)

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

GITHUB_TOKEN = os.getenv(
    "GITHUB_TOKEN",
    ""
)

GITHUB_REPO = os.getenv(
    "GITHUB_REPO",
    ""
)

GITHUB_BRANCH = os.getenv(
    "GITHUB_BRANCH",
    "main"
)

GITHUB_HISTORY_FILE = os.getenv(
    "GITHUB_HISTORY_FILE",
    "prediction_history.csv"
)


# ============================================================
# HISTORY COLUMNS
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
# GITHUB API
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
# LOAD HISTORY FROM GITHUB
# ============================================================

def load_history():

    # --------------------------------------------------------
    # If GitHub hasn't been configured correctly, fall back
    # to an empty database rather than crashing the dashboard.
    # --------------------------------------------------------

    if not GITHUB_TOKEN or not GITHUB_REPO:

        st.warning(
            "GitHub prediction storage is not configured. "
            "Check Streamlit Secrets."
        )

        return pd.DataFrame(
            columns=HISTORY_COLUMNS
        )

    try:

        response = requests.get(
            github_file_url(),
            headers=github_headers(),
            params={
                "ref": GITHUB_BRANCH
            },
            timeout=15
        )

        # ----------------------------------------------------
        # File does not exist yet.
        # That's OK. We'll create it when the first prediction
        # is generated.
        # ----------------------------------------------------

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

        from io import StringIO

        df = pd.read_csv(
            StringIO(decoded)
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
    commit_message="Update prediction history"
):

    if not GITHUB_TOKEN or not GITHUB_REPO:

        st.error(
            "GitHub storage is not configured."
        )

        return False

    try:

        csv_content = df.to_csv(
            index=False
        )

        encoded_content = base64.b64encode(
            csv_content.encode(
                "utf-8"
            )
        ).decode(
            "utf-8"
        )

        # ----------------------------------------------------
        # First find out whether the file already exists.
        # GitHub requires its SHA when updating an existing file.
        # ----------------------------------------------------

        get_response = requests.get(
            github_file_url(),
            headers=github_headers(),
            params={
                "ref": GITHUB_BRANCH
            },
            timeout=15
        )

        existing_sha = None

        if get_response.status_code == 200:

            existing_sha = (
                get_response.json()
                .get(
                    "sha"
                )
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

            payload[
                "sha"
            ] = existing_sha

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
# PREDICTION HISTORY HELPERS
# ============================================================

def generate_prediction_id():

    return (
        datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%d%H%M%S%f"
        )
    )


def get_latest_prediction(
    history,
    contract
):

    if history.empty:

        return None

    current = history[
        history["contract"] == contract
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
# YAHOO QUOTE
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

        if not closes.empty:

            raw_price = float(
                closes.iloc[-1]
            )

        else:

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
                        "No Yahoo Finance data returned."
                }

            daily_closes = pd.to_numeric(
                daily["Close"],
                errors="coerce"
            ).dropna()

            if daily_closes.empty:

                return {
                    "error":
                        "No valid price data returned."
                }

            raw_price = float(
                daily_closes.iloc[-1]
            )

        daily = stock.history(
            period="10d",
            interval="1d",
            auto_adjust=False
        )

        if (
            daily.empty
            or "Close" not in daily.columns
        ):

            previous_raw = raw_price

        else:

            daily_closes = pd.to_numeric(
                daily["Close"],
                errors="coerce"
            ).dropna()

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
            "price": price,
            "previous_close":
                previous_close,
            "change": change,
            "pct": pct
        }

    except Exception as e:

        return {
            "error": str(e)
        }


# ============================================================
# 10-YEAR TREASURY
# ============================================================

def get_10y_treasury():

    result = yf_quote(
        TREASURY_TICKER,
        multiplier=0.1
    )

    if (
        not result
        or "price" not in result
    ):

        return {
            "error": (
                result.get(
                    "error",
                    "10Y data unavailable."
                )
                if result
                else
                "10Y data unavailable."
            )
        }

    return result


# ============================================================
# GOLD TECHNICAL DATA
# ============================================================

def get_gold_technical_data():

    try:

        ticker = yf.Ticker(
            GOLD_TICKER
        )

        intraday = ticker.history(
            period="5d",
            interval="15m",
            auto_adjust=False
        )

        if (
            intraday.empty
            or "High" not in intraday.columns
            or "Low" not in intraday.columns
            or "Close" not in intraday.columns
        ):

            return {
                "error":
                    "Gold technical data unavailable."
            }

        intraday = intraday.copy()

        for column in [
            "Close",
            "High",
            "Low"
        ]:

            intraday[column] = pd.to_numeric(
                intraday[column],
                errors="coerce"
            )

        intraday = intraday.dropna(
            subset=[
                "Close",
                "High",
                "Low"
            ]
        )

        if intraday.empty:

            return {
                "error":
                    "No valid Gold technical data."
            }

        current_price = float(
            intraday[
                "Close"
            ].iloc[-1]
        )

        ma20 = float(
            intraday[
                "Close"
            ]
            .rolling(20)
            .mean()
            .iloc[-1]
        )

        ma50 = float(
            intraday[
                "Close"
            ]
            .rolling(50)
            .mean()
            .iloc[-1]
        )

        if intraday.index.tz is not None:

            eastern_index = (
                intraday.index
                .tz_convert(
                    EASTERN
                )
            )

        else:

            eastern_index = (
                intraday.index
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

        today_data = intraday[
            dates == today
        ]

        if today_data.empty:

            today_data = intraday.tail(
                min(
                    26,
                    len(intraday)
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

        unique_dates = sorted(
            set(dates)
        )

        previous_day = None

        for date_value in reversed(
            unique_dates
        ):

            if date_value < today:

                previous_day = date_value

                break

        if previous_day is not None:

            previous_day_data = intraday[
                dates == previous_day
            ]

        else:

            previous_day_data = pd.DataFrame()

        if previous_day_data.empty:

            previous_day_data = intraday.tail(
                min(
                    26,
                    len(intraday)
                )
            )

        previous_day_high = float(
            previous_day_data[
                "High"
            ].max()
        )

        previous_day_low = float(
            previous_day_data[
                "Low"
            ].min()
        )

        recent = intraday.tail(
            min(
                100,
                len(intraday)
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
                highs[i] >= highs[i - 1]
                and highs[i] >= highs[i - 2]
                and highs[i] >= highs[i + 1]
                and highs[i] >= highs[i + 2]
            ):

                swing_highs.append(
                    highs[i]
                )

        for i in range(
            2,
            len(lows) - 2
        ):

            if (
                lows[i] <= lows[i - 1]
                and lows[i] <= lows[i - 2]
                and lows[i] <= lows[i + 1]
                and lows[i] <= lows[i + 2]
            ):

                swing_lows.append(
                    lows[i]
                )

        resistance_candidates = [
            value
            for value in (
                swing_highs
                + [previous_day_high]
            )
            if value > current_price
        ]

        support_candidates = [
            value
            for value in (
                swing_lows
                + [previous_day_low]
            )
            if value < current_price
        ]

        if resistance_candidates:

            resistance = min(
                resistance_candidates
            )

        else:

            resistance = today_high

        if support_candidates:

            support = max(
                support_candidates
            )

        else:

            support = today_low

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
            "error": str(e)
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

    price = technical[
        "price"
    ]

    ma20 = technical[
        "ma20"
    ]

    ma50 = technical[
        "ma50"
    ]

    support = technical[
        "support"
    ]

    resistance = technical[
        "resistance"
    ]

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
            "The moving averages are "
            "essentially flat."
        )

    if score >= 2:

        bias = "BULLISH"

    elif score <= -2:

        bias = "BEARISH"

    else:

        bias = "MIXED"

    resistance_distance = 0

    support_distance = 0

    if resistance > price:

        resistance_distance = (
            (
                resistance - price
            )
            / price
        ) * 100

    if support < price:

        support_distance = (
            (
                price - support
            )
            / price
        ) * 100

    if 0 < resistance_distance <= 0.30:

        reasons.append(
            "⚠️ Gold is very close "
            "to nearby resistance."
        )

    elif 0 < resistance_distance <= 0.60:

        reasons.append(
            "Gold is approaching "
            "nearby resistance."
        )

    if 0 < support_distance <= 0.30:

        reasons.append(
            "⚠️ Gold is very close "
            "to nearby support."
        )

    elif 0 < support_distance <= 0.60:

        reasons.append(
            "Gold is approaching "
            "nearby support."
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

    score_value = 0

    reasons = []

    component_scores = {
        "gold": 0,
        "dxy": 0,
        "treasury": 0
    }

    if gold and "pct" in gold:

        gold_pct = gold[
            "pct"
        ]

        if gold_pct > 0.50:

            component_scores[
                "gold"
            ] = 3

            score_value += 3

            reasons.append(
                "Gold is rising strongly."
            )

        elif gold_pct > 0.05:

            component_scores[
                "gold"
            ] = 2

            score_value += 2

            reasons.append(
                "Gold is rising."
            )

        elif gold_pct < -0.50:

            component_scores[
                "gold"
            ] = -3

            score_value -= 3

            reasons.append(
                "Gold is falling strongly."
            )

        elif gold_pct < -0.05:

            component_scores[
                "gold"
            ] = -2

            score_value -= 2

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

        dxy_pct = dxy[
            "pct"
        ]

        if dxy_pct < -0.20:

            component_scores[
                "dxy"
            ] = 3

            score_value += 3

            reasons.append(
                "DXY is falling strongly, "
                "which supports gold."
            )

        elif dxy_pct < -0.03:

            component_scores[
                "dxy"
            ] = 2

            score_value += 2

            reasons.append(
                "DXY is lower, "
                "which supports gold."
            )

        elif dxy_pct > 0.20:

            component_scores[
                "dxy"
            ] = -3

            score_value -= 3

            reasons.append(
                "DXY is rising strongly, "
                "which pressures gold."
            )

        elif dxy_pct > 0.03:

            component_scores[
                "dxy"
            ] = -2

            score_value -= 2

            reasons.append(
                "DXY is higher, "
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

        treasury_pct = treasury[
            "pct"
        ]

        if treasury_pct < -0.10:

            component_scores[
                "treasury"
            ] = 2

            score_value += 2

            reasons.append(
                "The 10Y Treasury yield is "
                "falling, which is generally "
                "supportive of gold."
            )

        elif treasury_pct < -0.02:

            component_scores[
                "treasury"
            ] = 1

            score_value += 1

            reasons.append(
                "The 10Y Treasury yield "
                "is slightly lower."
            )

        elif treasury_pct > 0.10:

            component_scores[
                "treasury"
            ] = -2

            score_value -= 2

            reasons.append(
                "The 10Y Treasury yield is "
                "rising, which can pressure gold."
            )

        elif treasury_pct > 0.02:

            component_scores[
                "treasury"
            ] = -1

            score_value -= 1

            reasons.append(
                "The 10Y Treasury yield "
                "is slightly higher."
            )

        else:

            reasons.append(
                "The 10Y Treasury yield "
                "is relatively flat."
            )

    else:

        reasons.append(
            "10Y Treasury data unavailable."
        )

    if score_value >= 3:

        bias = "BULLISH"

    elif score_value <= -3:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL / WAIT"

    confidence = round(
        5 + (
            abs(score_value)
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
        component_scores,
        score_value
    )


# ============================================================
# COMBINED BIAS
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
        and technical_bias != "MIXED"
        and macro_bias != technical_bias
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
    technical_total,
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
            generate_prediction_id(),

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
            (
                dxy.get(
                    "price",
                    ""
                )
                if dxy
                else ""
            ),

        "dxy_pct":
            (
                dxy.get(
                    "pct",
                    ""
                )
                if dxy
                else ""
            ),

        "treasury_yield":
            (
                treasury.get(
                    "price",
                    ""
                )
                if treasury
                else ""
            ),

        "treasury_pct":
            (
                treasury.get(
                    "pct",
                    ""
                )
                if treasury
                else ""
            ),

        "macro_bias":
            macro_bias,

        "macro_confidence":
            macro_confidence,

        "technical_bias":
            technical_bias,

        "technical_score":
            technical_total,

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
# CHECK PAST PREDICTIONS
# ============================================================

def check_predictions(
    history
):

    if history.empty:

        return history, False

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

            existing_result = history.at[
                index,
                result_column
            ]

            if (
                pd.notna(existing_result)
                and str(
                    existing_result
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
                    or "Close" not in data.columns
                ):

                    continue

                data = data.copy()

                data[
                    "Close"
                ] = pd.to_numeric(
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

                target_time = (
                    timestamp
                    + pd.Timedelta(
                        minutes=minutes
                    )
                )

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

                differences = abs(
                    data.index
                    - target_time
                )

                closest_position = (
                    differences.argmin()
                )

                closest_difference = (
                    differences[
                        closest_position
                    ].total_seconds()
                )

                if closest_difference > (
                    20 * 60
                ):

                    continue

                future_price = float(
                    data[
                        "Close"
                    ].iloc[
                        closest_position
                    ]
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

                    if abs(move) < PREDICTION_THRESHOLD:

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

    return history, changed


# ============================================================
# PERFORMANCE
# ============================================================

def performance_stats(
    history,
    contract=None
):

    if history.empty:

        return {
            "15m": None,
            "30m": None,
            "1h": None,
            "2h": None
        }

    df = history.copy()

    if contract is not None:

        df = df[
            df["contract"] == contract
        ]

    stats = {}

    for horizon in PREDICTION_HORIZONS:

        column = (
            f"result_{horizon}"
        )

        results = (
            df[column]
            .astype(str)
            .str.upper()
        )

        correct = (
            results == "CORRECT"
        ).sum()

        wrong = (
            results == "WRONG"
        ).sum()

        total = (
            correct
            + wrong
        )

        if total == 0:

            stats[horizon] = {
                "correct": 0,
                "wrong": 0,
                "total": 0,
                "accuracy": None
            }

        else:

            stats[horizon] = {
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
                    ) * 100
            }

    return stats


def confidence_stats(
    history,
    contract=None
):

    if history.empty:

        return pd.DataFrame()

    df = history.copy()

    if contract is not None:

        df = df[
            df["contract"] == contract
        ]

    rows = []

    for confidence in range(
        1,
        11
    ):

        subset = df[
            pd.to_numeric(
                df[
                    "confidence"
                ],
                errors="coerce"
            ) == confidence
        ]

        if subset.empty:

            continue

        results = (
            subset[
                "result_1h"
            ]
            .astype(str)
            .str.upper()
        )

        correct = (
            results == "CORRECT"
        ).sum()

        wrong = (
            results == "WRONG"
        ).sum()

        total = (
            correct
            + wrong
        )

        if total == 0:

            continue

        rows.append(
            {
                "Confidence":
                    confidence,

                "1H Correct":
                    int(correct),

                "1H Wrong":
                    int(wrong),

                "1H Predictions":
                    int(total),

                "1H Accuracy":
                    round(
                        (
                            correct
                            / total
                        ) * 100,
                        1
                    )
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# NEWS DATE PARSING
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


def article_age_text(
    dt
):

    now = datetime.now(
        timezone.utc
    )

    seconds = int(
        (
            now - dt
        ).total_seconds()
    )

    if seconds < 0:

        seconds = 0

    minutes = seconds // 60

    if minutes < 1:

        return "just now"

    if minutes < 60:

        return f"{minutes}m ago"

    hours = minutes // 60

    remaining = (
        minutes % 60
    )

    if hours < 24:

        if remaining == 0:

            return f"{hours}h ago"

        return (
            f"{hours}h "
            f"{remaining}m ago"
        )

    days = hours // 24

    return f"{days}d ago"


def clean_title(
    title
):

    if not title:

        return ""

    title = str(
        title
    ).strip()

    if " - " in title:

        parts = title.rsplit(
            " - ",
            1
        )

        if (
            len(parts) == 2
            and len(
                parts[1].strip()
            ) < 60
        ):

            title = (
                parts[0]
                .strip()
            )

    return title


def add_article(
    articles,
    published,
    title,
    link,
    source=""
):

    title = clean_title(
        title
    )

    if (
        not title
        or not link
    ):

        return

    published_dt = parse_news_date(
        published
    )

    if published_dt is None:

        return

    now = datetime.now(
        timezone.utc
    )

    cutoff = (
        now
        - timedelta(
            hours=NEWS_MAX_AGE_HOURS
        )
    )

    if published_dt < cutoff:

        return

    future_limit = (
        now
        + timedelta(
            minutes=5
        )
    )

    if published_dt > future_limit:

        return

    articles.append(
        {
            "published_dt":
                published_dt,

            "title":
                title,

            "link":
                link,

            "source":
                source
        }
    )


# ============================================================
# NEWS
# ============================================================

def news():

    articles = []

    newsapi_key = os.getenv(
        "NEWSAPI_KEY",
        ""
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

            response.raise_for_status()

            data = response.json()

            for article in data.get(
                "articles",
                []
            ):

                source_data = article.get(
                    "source",
                    {}
                )

                add_article(
                    articles,
                    article.get(
                        "publishedAt",
                        ""
                    ),
                    article.get(
                        "title",
                        ""
                    ),
                    article.get(
                        "url",
                        ""
                    ),
                    source_data.get(
                        "name",
                        ""
                    )
                )

        except Exception:

            pass

    searches = [
        "gold futures gold price",
        "gold Federal Reserve Fed",
        "gold Treasury yields",
        "gold US dollar DXY",
        "gold inflation CPI PCE PPI",
        "gold economic data"
    ]

    for search_term in searches:

        try:

            feed_url = (
                "https://news.google.com/rss/search?"
                f"q={quote(search_term)}"
                "&hl=en-US"
                "&gl=US"
                "&ceid=US:en"
            )

            feed = feedparser.parse(
                feed_url
            )

            for entry in feed.entries:

                published = (
                    entry.get(
                        "published",
                        ""
                    )
                    or entry.get(
                        "updated",
                        ""
                    )
                )

                title = entry.get(
                    "title",
                    ""
                )

                link = entry.get(
                    "link",
                    ""
                )

                source = ""

                if hasattr(
                    entry,
                    "source"
                ):

                    source = entry.source.get(
                        "title",
                        ""
                    )

                add_article(
                    articles,
                    published,
                    title,
                    link,
                    source
                )

        except Exception:

            continue

    unique = {}

    for article in articles:

        key = article[
            "title"
        ].lower().strip()

        if key not in unique:

            unique[key] = article

    articles = list(
        unique.values()
    )

    articles.sort(
        key=lambda x:
            x["published_dt"],
        reverse=True
    )

    return articles[:20]


# ============================================================
# LOAD DATA
# ============================================================

history = load_history()

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
# SCORE
# ============================================================

(
    macro_bias,
    macro_confidence,
    macro_reasons,
    component_scores,
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
# CREATE NEW PREDICTION WHEN DUE
# ============================================================

latest_prediction = get_latest_prediction(
    history,
    GOLD_TICKER
)

create_new_prediction = False

if latest_prediction is None:

    create_new_prediction = True

else:

    latest_time = pd.to_datetime(
        latest_prediction[
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

        if (
            age_minutes
            >= PREDICTION_INTERVAL_MINUTES
        ):

            create_new_prediction = True


if create_new_prediction:

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
# CHECK OLD PREDICTIONS
# ============================================================

history, prediction_results_changed = (
    check_predictions(
        history
    )
)

if prediction_results_changed:

    save_history(
        history,
        "Update Gold Market Monitor prediction results"
    )


# ============================================================
# PAGE
# ============================================================

st.title(
    "🥇 Gold Market Monitor — MVP"
)

st.caption(
    "Automated market-monitoring dashboard. "
    "It does NOT place trades."
)

st.info(
    f"Monitoring: **{GOLD_CONTRACT_NAME}** "
    f"(`{GOLD_TICKER}`)"
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "Settings"
)

refresh = st.sidebar.selectbox(
    "Refresh interval",
    options=[
        15,
        30,
        60,
        120,
        300,
        900
    ],
    format_func=lambda x: (
        f"{x} seconds"
        if x < 60
        else (
            "1 minute"
            if x == 60
            else f"{x // 60} minutes"
        )
    ),
    index=2
)

st.sidebar.info(
    "The dashboard refreshes at the selected "
    "interval. New prediction snapshots are "
    f"created approximately every "
    f"{PREDICTION_INTERVAL_MINUTES} minutes."
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

st.sidebar.markdown(
    f"""
### Prediction Testing

Threshold:

**${PREDICTION_THRESHOLD:.2f}**

Horizons:

- 15 minutes
- 30 minutes
- 1 hour
- 2 hours
"""
)

if GITHUB_TOKEN and GITHUB_REPO:

    st.sidebar.success(
        "💾 GitHub prediction storage: CONNECTED"
    )

else:

    st.sidebar.error(
        "💾 GitHub prediction storage: NOT CONNECTED"
    )

st.sidebar.warning(
    "Educational monitoring only. "
    "This app does not place trades."
)


# ============================================================
# TOP METRICS
# ============================================================

column1, column2, column3, column4 = st.columns(4)


if gold and "price" in gold:

    column1.metric(
        "🥇 Gold — Oct 2026",
        f"${gold['price']:,.2f}",
        f"{gold['pct']:+.2f}%"
    )

else:

    column1.metric(
        "🥇 Gold — Oct 2026",
        "Unavailable"
    )


if dxy and "price" in dxy:

    column2.metric(
        "💵 DXY",
        f"{dxy['price']:.3f}",
        f"{dxy['pct']:+.2f}%"
    )

else:

    column2.metric(
        "💵 DXY",
        "Unavailable"
    )


if treasury and "price" in treasury:

    column3.metric(
        "🇺🇸 10Y Treasury",
        f"{treasury['price']:.2f}%",
        f"{treasury['pct']:+.2f}%"
    )

else:

    column3.metric(
        "🇺🇸 10Y Treasury",
        "Unavailable"
    )


column4.metric(
    "📊 Overall Bias",
    overall_bias,
    f"Confidence {overall_confidence}/10"
)


# ============================================================
# PREDICTION TRACKER
# ============================================================

st.subheader(
    "🧪 Prediction Tracker"
)

st.write(
    "The monitor records its predictions and "
    "later checks what Gold actually did at "
    "15-minute, 30-minute, 1-hour and "
    "2-hour intervals."
)

current_history = history[
    history["contract"] == GOLD_TICKER
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

    display_df = current_history[
        display_columns
    ].head(15).copy()

    display_df = display_df.rename(
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
        display_df,
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

st.caption(
    "Accuracy is based only on completed "
    "directional predictions."
)

current_stats = performance_stats(
    history,
    GOLD_TICKER
)

all_stats = performance_stats(
    history,
    None
)

perf1, perf2, perf3, perf4 = st.columns(4)

for column, horizon in zip(
    [perf1, perf2, perf3, perf4],
    ["15m", "30m", "1h", "2h"]
):

    stats = current_stats[
        horizon
    ]

    label = {
        "15m":
            "15 Minute",

        "30m":
            "30 Minute",

        "1h":
            "1 Hour",

        "2h":
            "2 Hour"
    }[horizon]

    if (
        stats
        and stats["accuracy"] is not None
    ):

        column.metric(
            label,
            f"{stats['accuracy']:.1f}%",
            f"{stats['correct']} correct / "
            f"{stats['total']} tested"
        )

    else:

        column.metric(
            label,
            "Not enough data"
        )


# ============================================================
# ALL CONTRACTS
# ============================================================

st.subheader(
    "🌎 All-Contract Performance"
)

all_perf1, all_perf2, all_perf3, all_perf4 = (
    st.columns(4)
)

for column, horizon in zip(
    [
        all_perf1,
        all_perf2,
        all_perf3,
        all_perf4
    ],
    ["15m", "30m", "1h", "2h"]
):

    stats = all_stats[
        horizon
    ]

    label = {
        "15m":
            "15 Minute",

        "30m":
            "30 Minute",

        "1h":
            "1 Hour",

        "2h":
            "2 Hour"
    }[horizon]

    if (
        stats
        and stats["accuracy"] is not None
    ):

        column.metric(
            label,
            f"{stats['accuracy']:.1f}%",
            f"{stats['correct']} correct / "
            f"{stats['total']} tested"
        )

    else:

        column.metric(
            label,
            "Not enough data"
        )


# ============================================================
# CONFIDENCE TEST
# ============================================================

st.subheader(
    "🎯 Does Higher Confidence Actually Work?"
)

confidence_df = confidence_stats(
    history,
    GOLD_TICKER
)

if not confidence_df.empty:

    st.dataframe(
        confidence_df,
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "Not enough completed 1-hour predictions "
        "to evaluate confidence yet."
    )


# ============================================================
# CURRENT ASSESSMENT
# ============================================================

st.subheader(
    "🎯 Current Market Assessment"
)

assessment1, assessment2 = st.columns(2)

with assessment1:

    st.markdown(
        "### 🌎 Macro"
    )

    st.metric(
        "Macro Bias",
        macro_bias,
        f"Confidence {macro_confidence}/10"
    )

with assessment2:

    st.markdown(
        "### 📈 Technical"
    )

    st.metric(
        "Technical Bias",
        technical_bias
    )


# ============================================================
# TECHNICAL LEVELS
# ============================================================

st.subheader(
    "📐 Gold Technical Levels"
)

if technical and "price" in technical:

    level1, level2, level3, level4 = (
        st.columns(4)
    )

    level1.metric(
        "Support",
        f"${technical['support']:,.2f}"
    )

    level2.metric(
        "Resistance",
        f"${technical['resistance']:,.2f}"
    )

    level3.metric(
        "20 MA",
        f"${technical['ma20']:,.2f}"
    )

    level4.metric(
        "50 MA",
        f"${technical['ma50']:,.2f}"
    )

    range1, range2, range3, range4 = (
        st.columns(4)
    )

    range1.metric(
        "Today's High",
        f"${technical['today_high']:,.2f}"
    )

    range2.metric(
        "Today's Low",
        f"${technical['today_low']:,.2f}"
    )

    range3.metric(
        "Prev. Day High",
        f"${technical['previous_day_high']:,.2f}"
    )

    range4.metric(
        "Prev. Day Low",
        f"${technical['previous_day_low']:,.2f}"
    )

else:

    st.warning(
        "Technical Gold data is unavailable."
    )


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

st.subheader(
    "🔎 Technical Analysis"
)

for reason in technical_reasons:

    st.write(
        "• " + reason
    )


# ============================================================
# MACRO ANALYSIS
# ============================================================

st.subheader(
    "🌎 Macro Analysis"
)

for reason in macro_reasons:

    st.write(
        "• " + reason
    )


# ============================================================
# OVERALL
# ============================================================

st.subheader(
    "🧠 Overall Monitor Assessment"
)

if overall_bias == "BULLISH":

    st.success(
        f"🟢 Overall environment is bullish. "
        f"Current confidence: "
        f"{overall_confidence}/10."
    )

elif overall_bias == "BEARISH":

    st.error(
        f"🔴 Overall environment is bearish. "
        f"Current confidence: "
        f"{overall_confidence}/10."
    )

else:

    st.warning(
        f"🟡 Conditions are mixed. "
        f"Current environment is WAIT. "
        f"Confidence: {overall_confidence}/10."
    )


# ============================================================
# NEWS
# ============================================================

st.subheader(
    "📰 Recent Gold / Macro Headlines"
)

if articles:

    st.caption(
        f"Articles published within the last "
        f"{NEWS_MAX_AGE_HOURS} hours. "
        "Times are Eastern Time."
    )

    for article in articles[:10]:

        published_dt = article[
            "published_dt"
        ]

        formatted_time = published_dt.astimezone(
            EASTERN
        ).strftime(
            "%b %d, %Y at %I:%M %p ET"
        )

        age = article_age_text(
            published_dt
        )

        title = article[
            "title"
        ]

        link = article[
            "link"
        ]

        source = article.get(
            "source",
            ""
        )

        source_text = (
            f" • {source}"
            if source
            else ""
        )

        st.markdown(
            f"**[{title}]({link})**  \n"
            f"🕒 {age} — "
            f"{formatted_time}"
            f"{source_text}"
        )

        st.divider()

else:

    st.info(
        "No sufficiently recent headlines returned."
    )


# ============================================================
# DATABASE STATUS
# ============================================================

st.subheader(
    "💾 Prediction Database"
)

total_predictions = len(
    history
)

current_predictions = len(
    history[
        history["contract"]
        == GOLD_TICKER
    ]
)

contract_count = (
    history["contract"].nunique()
    if not history.empty
    else 0
)

db1, db2, db3 = st.columns(3)

db1.metric(
    "Total Predictions",
    total_predictions
)

db2.metric(
    "Current Contract",
    current_predictions
)

db3.metric(
    "Contracts Tracked",
    contract_count
)

if GITHUB_TOKEN and GITHUB_REPO:

    st.success(
        "💾 Prediction history is connected "
        "to GitHub persistent storage."
    )

else:

    st.error(
        "GitHub persistent storage is not configured."
    )


# ============================================================
# DATA SOURCES
# ============================================================

with st.expander(
    "Data source information"
):

    st.write(
        f"🥇 Gold: Yahoo Finance — "
        f"{GOLD_TICKER}"
    )

    st.write(
        f"📋 CME contract: "
        f"{GOLD_CME_SYMBOL}"
    )

    st.write(
        "💵 DXY: Yahoo Finance — "
        "DX-Y.NYB"
    )

    st.write(
        "🇺🇸 10Y Treasury: Yahoo Finance — "
        "^TNX"
    )

    st.write(
        "📰 News: NewsAPI when configured; "
        "Google News RSS otherwise."
    )

    st.write(
        "💾 Prediction database: "
        f"GitHub — {GITHUB_HISTORY_FILE}"
    )


# ============================================================
# LAST REFRESH
# ============================================================

now_eastern = datetime.now(
    EASTERN
)

st.caption(
    "Last dashboard refresh: "
    + now_eastern.strftime(
        "%Y-%m-%d %I:%M:%S %p ET"
    )
)

st.caption(
    f"Next refresh in approximately "
    f"{refresh} seconds."
)


# ============================================================
# AUTOMATIC REFRESH
# ============================================================

time.sleep(
    refresh
)

st.rerun()
