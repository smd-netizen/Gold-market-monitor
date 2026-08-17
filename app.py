import os
import time
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
# CONSTANTS
# ============================================================

# EXACT CONTRACT WE ARE MONITORING
GOLD_TICKER = "1OZV26.CMX"
GOLD_CONTRACT_NAME = "1-Ounce Gold — October 2026"

DXY_TICKER = "DX-Y.NYB"
TREASURY_TICKER = "^TNX"

NEWS_MAX_AGE_HOURS = 48

EASTERN = ZoneInfo("America/New_York")

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


# ============================================================
# GENERIC YAHOO QUOTE
# ============================================================

def yf_quote(ticker, multiplier=1.0):
    """
    Get the latest Yahoo Finance price and compare it
    with the previous trading day's close.
    """

    try:

        stock = yf.Ticker(ticker)

        # ----------------------------------------------------
        # Intraday
        # ----------------------------------------------------

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

            # ------------------------------------------------
            # Fallback to daily data
            # ------------------------------------------------

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
                    "error": "No Yahoo Finance data returned."
                }

            daily_closes = pd.to_numeric(
                daily["Close"],
                errors="coerce"
            ).dropna()

            if daily_closes.empty:

                return {
                    "error": "No valid price data returned."
                }

            raw_price = float(
                daily_closes.iloc[-1]
            )

        # ----------------------------------------------------
        # Previous close
        # ----------------------------------------------------

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

        price = raw_price * multiplier

        previous_close = (
            previous_raw * multiplier
        )

        change = (
            price - previous_close
        )

        if previous_close != 0:

            pct = (
                (price / previous_close) - 1
            ) * 100

        else:

            pct = 0.0

        return {
            "price": price,
            "previous_close": previous_close,
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
                else "10Y data unavailable."
            )
        }

    return result


# ============================================================
# GOLD TECHNICAL DATA
# ============================================================

def get_gold_technical_data():
    """
    Technical analysis using the EXACT October 2026
    1-ounce Gold futures contract.

    Yahoo ticker:
        1OZV26.CMX

    Calculates:

        Current price
        Today's high
        Today's low
        Previous day's high
        Previous day's low
        20-period moving average
        50-period moving average
        Nearby support
        Nearby resistance
    """

    try:

        ticker = yf.Ticker(
            GOLD_TICKER
        )

        # ----------------------------------------------------
        # 15-minute data
        # ----------------------------------------------------

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
                "error": (
                    "Gold technical data unavailable."
                )
            }

        intraday = intraday.copy()

        # ----------------------------------------------------
        # Clean numbers
        # ----------------------------------------------------

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
                "error": (
                    "No valid Gold technical data."
                )
            }

        # ----------------------------------------------------
        # Current price
        # ----------------------------------------------------

        current_price = float(
            intraday["Close"].iloc[-1]
        )

        # ----------------------------------------------------
        # Moving averages
        # ----------------------------------------------------

        ma20 = float(
            intraday["Close"]
            .rolling(20)
            .mean()
            .iloc[-1]
        )

        ma50 = float(
            intraday["Close"]
            .rolling(50)
            .mean()
            .iloc[-1]
        )

        # ----------------------------------------------------
        # Convert timestamps to Eastern
        # ----------------------------------------------------

        if intraday.index.tz is not None:

            eastern_index = (
                intraday.index
                .tz_convert(EASTERN)
            )

        else:

            eastern_index = (
                intraday.index
                .tz_localize("UTC")
                .tz_convert(EASTERN)
            )

        dates = eastern_index.date

        today = datetime.now(
            EASTERN
        ).date()

        # ----------------------------------------------------
        # Today's data
        # ----------------------------------------------------

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
            today_data["High"].max()
        )

        today_low = float(
            today_data["Low"].min()
        )

        # ----------------------------------------------------
        # Previous trading day
        # ----------------------------------------------------

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
            previous_day_data["High"].max()
        )

        previous_day_low = float(
            previous_day_data["Low"].min()
        )

        # ----------------------------------------------------
        # Recent swing levels
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Swing highs
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Swing lows
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Resistance candidates
        # ----------------------------------------------------

        resistance_candidates = [
            value
            for value in (
                swing_highs
                + [previous_day_high]
            )
            if value > current_price
        ]

        # ----------------------------------------------------
        # Support candidates
        # ----------------------------------------------------

        support_candidates = [
            value
            for value in (
                swing_lows
                + [previous_day_low]
            )
            if value < current_price
        ]

        # ----------------------------------------------------
        # Nearest resistance
        # ----------------------------------------------------

        if resistance_candidates:

            resistance = min(
                resistance_candidates
            )

        else:

            resistance = today_high

        # ----------------------------------------------------
        # Nearest support
        # ----------------------------------------------------

        if support_candidates:

            support = max(
                support_candidates
            )

        else:

            support = today_low

        return {
            "price": current_price,
            "today_high": today_high,
            "today_low": today_low,
            "previous_day_high": previous_day_high,
            "previous_day_low": previous_day_low,
            "ma20": ma20,
            "ma50": ma50,
            "support": support,
            "resistance": resistance
        }

    except Exception as e:

        return {
            "error": str(e)
        }


# ============================================================
# TECHNICAL SCORING
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

    # ========================================================
    # PRICE VS 20 MA
    # ========================================================

    if price > ma20:

        score += 1

        reasons.append(
            "Gold is above its 20-period moving average."
        )

    else:

        score -= 1

        reasons.append(
            "Gold is below its 20-period moving average."
        )

    # ========================================================
    # PRICE VS 50 MA
    # ========================================================

    if price > ma50:

        score += 1

        reasons.append(
            "Gold is above its 50-period moving average."
        )

    else:

        score -= 1

        reasons.append(
            "Gold is below its 50-period moving average."
        )

    # ========================================================
    # MA RELATIONSHIP
    # ========================================================

    if ma20 > ma50:

        score += 1

        reasons.append(
            "The 20-period average is above the "
            "50-period average."
        )

    elif ma20 < ma50:

        score -= 1

        reasons.append(
            "The 20-period average is below the "
            "50-period average."
        )

    else:

        reasons.append(
            "The moving averages are essentially flat."
        )

    # ========================================================
    # TECHNICAL BIAS
    # ========================================================

    if score >= 2:

        bias = "BULLISH"

    elif score <= -2:

        bias = "BEARISH"

    else:

        bias = "MIXED"

    # ========================================================
    # DISTANCE TO RESISTANCE
    # ========================================================

    if resistance > price:

        resistance_distance = (
            (
                resistance - price
            )
            / price
        ) * 100

    else:

        resistance_distance = 0

    # ========================================================
    # DISTANCE TO SUPPORT
    # ========================================================

    if support < price:

        support_distance = (
            (
                price - support
            )
            / price
        ) * 100

    else:

        support_distance = 0

    # ========================================================
    # RESISTANCE WARNINGS
    # ========================================================

    if 0 < resistance_distance <= 0.30:

        reasons.append(
            "⚠️ Gold is very close to nearby resistance."
        )

    elif 0 < resistance_distance <= 0.60:

        reasons.append(
            "Gold is approaching nearby resistance."
        )

    # ========================================================
    # SUPPORT WARNINGS
    # ========================================================

    if 0 < support_distance <= 0.30:

        reasons.append(
            "⚠️ Gold is very close to nearby support."
        )

    elif 0 < support_distance <= 0.60:

        reasons.append(
            "Gold is approaching nearby support."
        )

    return (
        bias,
        score,
        reasons
    )


# ============================================================
# MACRO SCORING
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

    # ========================================================
    # GOLD
    # ========================================================

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

    # ========================================================
    # DXY
    # ========================================================

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

    # ========================================================
    # 10Y TREASURY
    # ========================================================

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
                "The 10Y Treasury yield is falling, "
                "which is generally supportive of gold."
            )

        elif treasury_pct < -0.02:

            component_scores[
                "treasury"
            ] = 1

            score_value += 1

            reasons.append(
                "The 10Y Treasury yield is slightly lower."
            )

        elif treasury_pct > 0.10:

            component_scores[
                "treasury"
            ] = -2

            score_value -= 2

            reasons.append(
                "The 10Y Treasury yield is rising, "
                "which can pressure gold."
            )

        elif treasury_pct > 0.02:

            component_scores[
                "treasury"
            ] = -1

            score_value -= 1

            reasons.append(
                "The 10Y Treasury yield is slightly higher."
            )

        else:

            reasons.append(
                "The 10Y Treasury yield is relatively flat."
            )

    else:

        reasons.append(
            "10Y Treasury data unavailable."
        )

    # ========================================================
    # MACRO BIAS
    # ========================================================

    if score_value >= 3:

        bias = "BULLISH"

    elif score_value <= -3:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL / WAIT"

    confidence = round(
        5 + (
            abs(score_value) / 8
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

    # --------------------------------------------------------
    # Macro
    # --------------------------------------------------------

    if macro_bias == "BULLISH":

        score += 2

    elif macro_bias == "BEARISH":

        score -= 2

    # --------------------------------------------------------
    # Technical
    # --------------------------------------------------------

    if technical_bias == "BULLISH":

        score += 2

    elif technical_bias == "BEARISH":

        score -= 2

    # --------------------------------------------------------
    # Overall bias
    # --------------------------------------------------------

    if score >= 3:

        bias = "BULLISH"

    elif score <= -3:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL / WAIT"

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

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
# NEWS DATE PARSING
# ============================================================

def parse_news_date(value):

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


def eastern_datetime(dt):

    if dt is None:

        return None

    return dt.astimezone(
        EASTERN
    )


def article_age_text(dt):

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

    remaining_minutes = (
        minutes % 60
    )

    if hours < 24:

        if remaining_minutes == 0:

            return f"{hours}h ago"

        return (
            f"{hours}h "
            f"{remaining_minutes}m ago"
        )

    days = hours // 24

    return f"{days}d ago"


# ============================================================
# NEWS CLEANUP
# ============================================================

def clean_title(title):

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

        if len(parts) == 2:

            possible_source = (
                parts[1].strip()
            )

            if (
                len(possible_source) < 60
                and len(parts[0].strip()) > 10
            ):

                title = parts[0].strip()

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

    if not title or not link:

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

    # --------------------------------------------------------
    # Reject old articles
    # --------------------------------------------------------

    if published_dt < cutoff:

        return

    # --------------------------------------------------------
    # Reject impossible future timestamps
    # --------------------------------------------------------

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
            "published_dt": published_dt,
            "title": title,
            "link": link,
            "source": source
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

    # ========================================================
    # NEWS API
    # ========================================================

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
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 50,
                    "apiKey": newsapi_key
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

    # ========================================================
    # GOOGLE NEWS RSS FALLBACK
    # ========================================================

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

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

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

    # ========================================================
    # NEWEST FIRST
    # ========================================================

    articles.sort(
        key=lambda x: x[
            "published_dt"
        ],
        reverse=True
    )

    return articles[:20]


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
    "The entire dashboard refreshes at "
    "the selected interval."
)

st.sidebar.markdown(
    f"""
**Gold contract being monitored**

🥇 {GOLD_CONTRACT_NAME}

Yahoo symbol:

`{GOLD_TICKER}`

CME symbol:

`1OZV6`
"""
)

st.sidebar.warning(
    "This dashboard is for monitoring and education. "
    "It does not place trades."
)


# ============================================================
# TITLE
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
# GET DATA
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
# MACRO SCORE
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


# ============================================================
# TECHNICAL SCORE
# ============================================================

(
    technical_bias,
    technical_total,
    technical_reasons
) = technical_score(
    technical
)


# ============================================================
# COMBINED SCORE
# ============================================================

(
    combined,
    combined_confidence
) = combined_bias(
    macro_bias,
    macro_confidence,
    technical_bias
)


# ============================================================
# TOP METRICS
# ============================================================

column1, column2, column3, column4 = st.columns(4)


# ------------------------------------------------------------
# GOLD
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# DXY
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# 10Y
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# OVERALL BIAS
# ------------------------------------------------------------

column4.metric(
    "📊 Overall Bias",
    combined,
    f"Confidence {combined_confidence}/10"
)


# ============================================================
# MARKET ASSESSMENT
# ============================================================

st.subheader(
    "🎯 Market Assessment"
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

    level1, level2, level3, level4 = st.columns(4)

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

    # --------------------------------------------------------
    # Daily range
    # --------------------------------------------------------

    range1, range2, range3, range4 = st.columns(4)

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
        "Technical Gold data is currently unavailable."
    )


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

st.subheader(
    "🔎 Technical Analysis"
)

if technical_reasons:

    for reason in technical_reasons:

        st.write(
            "• " + reason
        )

else:

    st.write(
        "Technical analysis is unavailable."
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
# OVERALL INTERPRETATION
# ============================================================

st.subheader(
    "🧠 Overall Monitor Assessment"
)

if combined == "BULLISH":

    if (
        macro_bias == "BULLISH"
        and technical_bias == "BULLISH"
    ):

        st.success(
            f"🟢 Macro and technical conditions are "
            f"both bullish. Current confidence: "
            f"{combined_confidence}/10."
        )

    else:

        st.success(
            f"🟢 The overall environment is bullish, "
            f"but macro and technical conditions are "
            f"not perfectly aligned. Confidence: "
            f"{combined_confidence}/10."
        )

elif combined == "BEARISH":

    if (
        macro_bias == "BEARISH"
        and technical_bias == "BEARISH"
    ):

        st.error(
            f"🔴 Macro and technical conditions are "
            f"both bearish. Current confidence: "
            f"{combined_confidence}/10."
        )

    else:

        st.error(
            f"🔴 The overall environment is bearish, "
            f"but macro and technical conditions are "
            f"not perfectly aligned. Confidence: "
            f"{combined_confidence}/10."
        )

else:

    st.warning(
        f"🟡 Macro and technical conditions are mixed. "
        f"This is currently a WAIT environment. "
        f"Confidence: {combined_confidence}/10."
    )


# ============================================================
# NEWS
# ============================================================

st.subheader(
    "📰 Recent Gold / Macro Headlines"
)

if articles:

    st.caption(
        f"Showing articles published within the last "
        f"{NEWS_MAX_AGE_HOURS} hours. "
        "All times are Eastern Time."
    )

    for article in articles[:10]:

        published_dt = article[
            "published_dt"
        ]

        eastern = eastern_datetime(
            published_dt
        )

        formatted_time = eastern.strftime(
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
            f"🕒 {age} — {formatted_time}"
            f"{source_text}"
        )

        st.divider()

else:

    st.info(
        "No sufficiently recent gold/macro headlines "
        "were returned."
    )


# ============================================================
# DATA SOURCES
# ============================================================

with st.expander(
    "Data source information"
):

    st.write(
        f"🥇 Gold: Yahoo Finance — {GOLD_TICKER}"
    )

    st.write(
        "💵 DXY: Yahoo Finance — DX-Y.NYB"
    )

    st.write(
        "🇺🇸 10Y Treasury: Yahoo Finance — ^TNX"
    )

    st.write(
        f"📈 Technical data: Yahoo Finance — {GOLD_TICKER}"
    )

    st.write(
        "📰 News: NewsAPI when configured, "
        "otherwise Google News RSS."
    )

    st.write(
        "News timestamps are converted to "
        "America/New_York."
    )


# ============================================================
# REFRESH STATUS
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
    f"Next automatic refresh in approximately "
    f"{refresh} seconds."
)


# ============================================================
# AUTOMATIC REFRESH
# ============================================================

time.sleep(
    refresh
)

st.rerun()
