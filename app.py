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
# MARKET DATA
# ============================================================

def yf_quote(ticker, multiplier=1.0):
    """
    Get the latest Yahoo Finance price.

    multiplier is used for instruments such as ^TNX,
    which Yahoo quotes approximately 10x the actual
    Treasury yield.

    Returns:
        price
        previous_close
        change
        pct
    """

    try:

        stock = yf.Ticker(ticker)

        # ----------------------------------------------------
        # Intraday data
        # ----------------------------------------------------

        intraday = stock.history(
            period="1d",
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

        # ----------------------------------------------------
        # Latest price
        # ----------------------------------------------------

        if not closes.empty:

            raw_price = float(
                closes.iloc[-1]
            )

        else:

            # Fall back to daily data.
            daily = stock.history(
                period="5d",
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
        # Previous trading day close
        # ----------------------------------------------------

        daily = stock.history(
            period="5d",
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

        # ----------------------------------------------------
        # Apply multiplier
        # ----------------------------------------------------

        price = raw_price * multiplier
        previous_close = previous_raw * multiplier

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
    """
    Get the 10-Year Treasury yield from Yahoo Finance.

    Yahoo's ^TNX quote is approximately 10x the actual
    percentage yield.

    Example:
        Yahoo ^TNX = 46.8
        Actual 10Y yield = 4.68%
    """

    result = yf_quote(
        "^TNX",
        multiplier=0.1
    )

    if not result or "price" not in result:

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
# NEWS DATE PARSING
# ============================================================

def parse_news_date(value):
    """
    Convert a news timestamp into a timezone-aware UTC datetime.
    """

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
    """
    Convert a UTC datetime to Eastern Time.
    """

    if dt is None:

        return None

    return dt.astimezone(
        EASTERN
    )


def article_age_text(dt):
    """
    Return a human-readable article age.
    """

    now = datetime.now(
        timezone.utc
    )

    seconds = int(
        (now - dt).total_seconds()
    )

    if seconds < 0:

        seconds = 0

    minutes = seconds // 60

    if minutes < 1:

        return "just now"

    if minutes < 60:

        return f"{minutes}m ago"

    hours = minutes // 60
    remaining_minutes = minutes % 60

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
# NEWS TITLE CLEANUP
# ============================================================

def clean_title(title):

    if not title:

        return ""

    title = str(
        title
    ).strip()

    # Google News frequently appends:
    #
    # " - Reuters"
    #
    # Remove that suffix.

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


# ============================================================
# ADD NEWS ARTICLE
# ============================================================

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
    # Reject genuine future timestamps.
    #
    # Allow a tiny 5-minute tolerance because publishers can
    # have slightly incorrect clocks.
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

    # ========================================================
    # NEWSAPI
    # ========================================================

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
    # GOOGLE NEWS RSS
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
# MARKET SCORING
# ============================================================

def score(
    gold,
    dxy,
    treasury
):
    """
    Transparent gold-market scoring.

    Maximum bullish score:
        Gold      +3
        DXY       +3
        10Y       +2

    Maximum bearish score:
        Gold      -3
        DXY       -3
        10Y       -2

    The 10Y has less weight because it is a slower-moving
    macro indicator compared with gold and DXY.
    """

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
                "The 10Y Treasury yield is slightly lower, "
                "which is mildly supportive of gold."
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
                "The 10Y Treasury yield is slightly higher, "
                "which is a mild headwind for gold."
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
    # FINAL BIAS
    # ========================================================

    if score_value >= 6:

        bias = "BULLISH"

    elif score_value >= 3:

        bias = "BULLISH"

    elif score_value <= -6:

        bias = "BEARISH"

    elif score_value <= -3:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL / WAIT"

    # --------------------------------------------------------
    # Confidence
    #
    # Convert the total possible score of +/-8 into a
    # confidence value from roughly 1-10.
    # --------------------------------------------------------

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
    "The entire dashboard refreshes at the "
    "selected interval."
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


# ============================================================
# GET DATA
# ============================================================

gold = yf_quote(
    "GC=F"
)

dxy = yf_quote(
    "DX-Y.NYB"
)

treasury = get_10y_treasury()

articles = news()

bias, confidence, reasons, component_scores, total_score = score(
    gold,
    dxy,
    treasury
)


# ============================================================
# TOP METRICS
# ============================================================

column1, column2, column3, column4 = st.columns(4)


# ============================================================
# GOLD
# ============================================================

if gold and "price" in gold:

    column1.metric(
        "🥇 Gold Futures",
        f"${gold['price']:,.2f}",
        f"{gold['pct']:+.2f}%"
    )

else:

    column1.metric(
        "🥇 Gold Futures",
        "Unavailable"
    )


# ============================================================
# DXY
# ============================================================

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


# ============================================================
# 10Y
# ============================================================

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


# ============================================================
# BIAS
# ============================================================

column4.metric(
    "📊 Monitor Bias",
    bias,
    f"Confidence {confidence}/10"
)


# ============================================================
# SCORE BREAKDOWN
# ============================================================

st.subheader(
    "📊 Market Signal Breakdown"
)

score_col1, score_col2, score_col3, score_col4 = st.columns(4)

score_col1.metric(
    "Gold",
    f"{component_scores['gold']:+d}"
)

score_col2.metric(
    "DXY",
    f"{component_scores['dxy']:+d}"
)

score_col3.metric(
    "10Y",
    f"{component_scores['treasury']:+d}"
)

score_col4.metric(
    "Total",
    f"{total_score:+d}"
)


# ============================================================
# ANALYSIS
# ============================================================

st.subheader(
    "🔎 What the monitor sees"
)

for reason in reasons:

    st.write(
        "• " + reason
    )


# ============================================================
# SIMPLE INTERPRETATION
# ============================================================

if bias == "BULLISH":

    st.success(
        f"🟢 The indicators are currently leaning "
        f"BULLISH for gold. Confidence: "
        f"{confidence}/10."
    )

elif bias == "BEARISH":

    st.error(
        f"🔴 The indicators are currently leaning "
        f"BEARISH for gold. Confidence: "
        f"{confidence}/10."
    )

else:

    st.warning(
        f"🟡 The indicators are mixed. "
        f"Current reading: NEUTRAL / WAIT. "
        f"Confidence: {confidence}/10."
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

        if source:

            source_text = (
                f" • {source}"
            )

        else:

            source_text = ""

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
        "🥇 Gold: Yahoo Finance — GC=F"
    )

    st.write(
        "💵 DXY: Yahoo Finance — DX-Y.NYB"
    )

    st.write(
        "🇺🇸 10Y Treasury: Yahoo Finance — ^TNX"
    )

    st.write(
        "📰 News: NewsAPI when configured, "
        "otherwise Google News RSS."
    )

    st.write(
        "News timestamps are converted to "
        "America/New_York (Eastern Time)."
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
