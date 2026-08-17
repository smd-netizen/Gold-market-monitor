import os
import time
from datetime import datetime, timedelta, timezone

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

FRED_DGS10_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
)

NEWS_MAX_AGE_HOURS = 48

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

def yf_quote(ticker):
    """
    Get the latest Yahoo Finance quote and calculate the
    change versus the previous trading day's close.
    """

    try:
        stock = yf.Ticker(ticker)

        # ----------------------------------------------------
        # Get recent daily data.
        # This lets us compare today's/latest price against
        # the previous trading day's close.
        # ----------------------------------------------------

        daily = stock.history(
            period="5d",
            interval="1d",
            auto_adjust=False
        )

        if daily.empty or "Close" not in daily.columns:
            return {
                "error": "No daily quote data returned."
            }

        closes = pd.to_numeric(
            daily["Close"],
            errors="coerce"
        ).dropna()

        if closes.empty:
            return {
                "error": "No valid closing prices returned."
            }

        latest_daily_close = float(closes.iloc[-1])

        # ----------------------------------------------------
        # Try to get an intraday price.
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

            intraday_closes = pd.to_numeric(
                intraday["Close"],
                errors="coerce"
            ).dropna()

        else:

            intraday_closes = pd.Series(dtype=float)

        # ----------------------------------------------------
        # Determine current price.
        # ----------------------------------------------------

        if not intraday_closes.empty:

            price = float(
                intraday_closes.iloc[-1]
            )

        else:

            price = latest_daily_close

        # ----------------------------------------------------
        # Determine previous trading day's close.
        #
        # If we have more than one daily close, the second-last
        # value is the previous trading day.
        # ----------------------------------------------------

        if len(closes) >= 2:

            previous_close = float(
                closes.iloc[-2]
            )

        else:

            previous_close = latest_daily_close

        # ----------------------------------------------------
        # Calculate change.
        # ----------------------------------------------------

        change = price - previous_close

        if previous_close != 0:

            pct = (
                (price / previous_close) - 1
            ) * 100

        else:

            pct = 0.0

        return {
            "price": price,
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

def fred_series(series_id):
    """
    Get the latest observation from a FRED daily series.

    DGS10 = 10-Year Treasury Constant Maturity Rate.
    """

    try:

        response = requests.get(
            FRED_DGS10_URL,
            headers=REQUEST_HEADERS,
            timeout=15
        )

        response.raise_for_status()

        from io import StringIO

        df = pd.read_csv(
            StringIO(response.text)
        )

        if series_id not in df.columns:

            return {
                "error": (
                    f"FRED series {series_id} "
                    "was not found."
                )
            }

        df[series_id] = pd.to_numeric(
            df[series_id],
            errors="coerce"
        )

        df = df.dropna(
            subset=[series_id]
        )

        if df.empty:

            return {
                "error": "No valid FRED observations returned."
            }

        latest = df.iloc[-1]

        return {
            "value": float(
                latest[series_id]
            ),
            "date": str(
                latest["DATE"]
            )
        }

    except Exception as e:

        return {
            "error": str(e)
        }


# ============================================================
# ECONOMIC CALENDAR
# ============================================================

def trading_economics_calendar():
    """
    Optional Trading Economics calendar.

    If TE_API_KEY is not configured, the calendar simply
    returns an empty dataframe.
    """

    key = os.getenv(
        "TE_API_KEY",
        ""
    )

    if not key:

        return pd.DataFrame()

    try:

        today = datetime.now().date()

        url = (
            "https://api.tradingeconomics.com/"
            "calendar/country/United%20States/"
            "importance/3"
        )

        response = requests.get(
            url,
            params={
                "c": key,
                "d1": today,
                "d2": today
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
# NEWS HELPERS
# ============================================================

def parse_news_date(value):
    """
    Convert a feed/API date into a timezone-aware datetime.
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


def clean_title(title):
    """
    Remove common Google News source suffixes.
    """

    if not title:
        return ""

    title = str(title).strip()

    # Google News often formats headlines like:
    #
    # "Gold rises today - Reuters"
    #
    # Remove the source suffix when possible.

    if " - " in title:

        parts = title.rsplit(
            " - ",
            1
        )

        if len(parts) == 2:

            possible_source = parts[1].strip()

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
    """
    Add an article only if it is recent and valid.
    """

    title = clean_title(title)

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

    if published_dt < cutoff:

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
    """
    Get recent gold/macro headlines.

    NewsAPI is used when NEWSAPI_KEY exists.

    Otherwise multiple Google News RSS searches are used.

    Only articles from the last NEWS_MAX_AGE_HOURS are accepted.
    """

    articles = []

    # ========================================================
    # NEWSAPI
    # ========================================================

    key = os.getenv(
        "NEWSAPI_KEY",
        ""
    )

    if key:

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
                    "apiKey": key
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
                    article.get(
                        "source",
                        {}
                    ).get(
                        "name",
                        ""
                    )
                )

        except Exception:
            pass

    # ========================================================
    # GOOGLE NEWS RSS FALLBACK
    # ========================================================

    # We deliberately use several focused searches rather
    # than one broad search.
    # ========================================================

    searches = [
        "gold futures gold price",
        "gold Federal Reserve Fed",
        "gold Treasury yields",
        "gold US dollar DXY",
        "gold inflation CPI PCE PPI"
    ]

    for search_term in searches:

        try:

            feed_url = (
                "https://news.google.com/rss/search?"
                f"q={requests.utils.quote(search_term)}"
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

        key = article["title"].lower().strip()

        if key not in unique:

            unique[key] = article

    articles = list(
        unique.values()
    )

    # ========================================================
    # SORT NEWEST FIRST
    # ========================================================

    articles.sort(
        key=lambda x: x["published_dt"],
        reverse=True
    )

    return articles[:20]


# ============================================================
# GOLD MARKET SCORING
# ============================================================

def score(
    gold,
    dxy,
    treasury
):
    """
    Transparent first-pass gold-market scoring system.

    This is NOT a predictive trading model.

    Gold:
        Rising = bullish
        Falling = bearish

    DXY:
        Falling = bullish gold
        Rising = bearish gold

    10Y Treasury:
        Falling = bullish gold
        Rising = bearish gold

    Treasury gets less weight than Gold/DXY because the
    Treasury data is daily rather than intraday.
    """

    score_value = 0

    reasons = []

    # ========================================================
    # GOLD
    # ========================================================

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

        dxy_pct = dxy["pct"]

        if dxy_pct < -0.15:

            score_value += 2

            reasons.append(
                "DXY is falling strongly, "
                "which generally supports gold."
            )

        elif dxy_pct < -0.03:

            score_value += 1

            reasons.append(
                "DXY is slightly lower, "
                "which is supportive of gold."
            )

        elif dxy_pct > 0.15:

            score_value -= 2

            reasons.append(
                "DXY is rising strongly, "
                "which generally pressures gold."
            )

        elif dxy_pct > 0.03:

            score_value -= 1

            reasons.append(
                "DXY is slightly higher, "
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
    # 10-Y TREASURY
    # ========================================================

    if not treasury or "value" not in treasury:

        reasons.append(
            "10-year Treasury data unavailable."
        )

    else:

        reasons.append(
            "10-year Treasury yield is available "
            "as macroeconomic context."
        )

        # We don't assign an intraday score here because
        # DGS10 is a daily FRED series.

    # ========================================================
    # FINAL BIAS
    # ========================================================

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

    return (
        bias,
        confidence,
        reasons
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
            f"{x // 60} minute"
            if x == 60
            else f"{x // 60} minutes"
        )
    ),
    index=2
)

st.sidebar.info(
    "The dashboard refreshes all available data "
    "at the selected interval."
)

st.sidebar.warning(
    "Gold futures and DXY can move quickly. "
    "This dashboard is for monitoring and education, "
    "not execution."
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

treasury = fred_series(
    "DGS10"
)

events = trading_economics_calendar()

articles = news()

bias, confidence, reasons = score(
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
# 10 YEAR
# ============================================================

if treasury and "value" in treasury:

    treasury_date = treasury.get(
        "date",
        ""
    )

    column3.metric(
        "🇺🇸 10Y Treasury",
        f"{treasury['value']:.2f}%",
        help=(
            "10-Year Treasury Constant Maturity Rate "
            f"from FRED. Latest observation: "
            f"{treasury_date}"
        )
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
# MARKET ANALYSIS
# ============================================================

st.subheader(
    "What the monitor sees"
)

for reason in reasons:

    st.write(
        "• " + reason
    )


st.warning(
    "This is an educational monitoring heuristic. "
    "It is not financial advice and is not a proven "
    "trading strategy."
)


# ============================================================
# 10Y DATA STATUS
# ============================================================

if treasury and "value" in treasury:

    st.caption(
        "10Y source: FRED — "
        f"latest observation {treasury.get('date', 'unknown')}. "
        "The 10Y FRED series is published daily, so it will "
        "not necessarily change every dashboard refresh."
    )

else:

    st.error(
        "The 10-Year Treasury data could not be retrieved "
        "from FRED during this refresh."
    )


# ============================================================
# ECONOMIC CALENDAR
# ============================================================

st.subheader(
    "📅 Today's high-importance economic events"
)

if events.empty:

    st.info(
        "No Trading Economics calendar data is configured. "
        "If you add a TE_API_KEY to Streamlit secrets, "
        "today's high-importance U.S. events can appear here."
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
    "📰 Recent Gold / Macro Headlines"
)

if articles:

    st.caption(
        f"Showing articles published within the last "
        f"{NEWS_MAX_AGE_HOURS} hours. "
        "Newest articles appear first."
    )

    for article in articles[:10]:

        published_dt = article[
            "published_dt"
        ]

        # Convert UTC to Eastern Time.
        eastern_time = (
            published_dt
            .astimezone()
        )

        formatted_time = (
            eastern_time.strftime(
                "%b %d, %Y at %I:%M %p"
            )
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
                f" — {source}"
            )

        else:

            source_text = ""

        st.markdown(
            f"**[{title}]({link})**  \n"
            f"🕒 {formatted_time}"
            f"{source_text}"
        )

        st.divider()

else:

    st.info(
        "No sufficiently recent gold/macro headlines "
        "were returned during this refresh."
    )


# ============================================================
# REFRESH STATUS
# ============================================================

current_time = datetime.now()

st.caption(
    "Last dashboard refresh: "
    + current_time.strftime(
        "%Y-%m-%d %I:%M:%S %p"
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

st.rerun()import os
import time
from datetime import datetime, timedelta, timezone

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

FRED_DGS10_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
)

NEWS_MAX_AGE_HOURS = 48

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

def yf_quote(ticker):
    """
    Get the latest Yahoo Finance quote and calculate the
    change versus the previous trading day's close.
    """

    try:
        stock = yf.Ticker(ticker)

        # ----------------------------------------------------
        # Get recent daily data.
        # This lets us compare today's/latest price against
        # the previous trading day's close.
        # ----------------------------------------------------

        daily = stock.history(
            period="5d",
            interval="1d",
            auto_adjust=False
        )

        if daily.empty or "Close" not in daily.columns:
            return {
                "error": "No daily quote data returned."
            }

        closes = pd.to_numeric(
            daily["Close"],
            errors="coerce"
        ).dropna()

        if closes.empty:
            return {
                "error": "No valid closing prices returned."
            }

        latest_daily_close = float(closes.iloc[-1])

        # ----------------------------------------------------
        # Try to get an intraday price.
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

            intraday_closes = pd.to_numeric(
                intraday["Close"],
                errors="coerce"
            ).dropna()

        else:

            intraday_closes = pd.Series(dtype=float)

        # ----------------------------------------------------
        # Determine current price.
        # ----------------------------------------------------

        if not intraday_closes.empty:

            price = float(
                intraday_closes.iloc[-1]
            )

        else:

            price = latest_daily_close

        # ----------------------------------------------------
        # Determine previous trading day's close.
        #
        # If we have more than one daily close, the second-last
        # value is the previous trading day.
        # ----------------------------------------------------

        if len(closes) >= 2:

            previous_close = float(
                closes.iloc[-2]
            )

        else:

            previous_close = latest_daily_close

        # ----------------------------------------------------
        # Calculate change.
        # ----------------------------------------------------

        change = price - previous_close

        if previous_close != 0:

            pct = (
                (price / previous_close) - 1
            ) * 100

        else:

            pct = 0.0

        return {
            "price": price,
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

def fred_series(series_id):
    """
    Get the latest observation from a FRED daily series.

    DGS10 = 10-Year Treasury Constant Maturity Rate.
    """

    try:

        response = requests.get(
            FRED_DGS10_URL,
            headers=REQUEST_HEADERS,
            timeout=15
        )

        response.raise_for_status()

        from io import StringIO

        df = pd.read_csv(
            StringIO(response.text)
        )

        if series_id not in df.columns:

            return {
                "error": (
                    f"FRED series {series_id} "
                    "was not found."
                )
            }

        df[series_id] = pd.to_numeric(
            df[series_id],
            errors="coerce"
        )

        df = df.dropna(
            subset=[series_id]
        )

        if df.empty:

            return {
                "error": "No valid FRED observations returned."
            }

        latest = df.iloc[-1]

        return {
            "value": float(
                latest[series_id]
            ),
            "date": str(
                latest["DATE"]
            )
        }

    except Exception as e:

        return {
            "error": str(e)
        }


# ============================================================
# ECONOMIC CALENDAR
# ============================================================

def trading_economics_calendar():
    """
    Optional Trading Economics calendar.

    If TE_API_KEY is not configured, the calendar simply
    returns an empty dataframe.
    """

    key = os.getenv(
        "TE_API_KEY",
        ""
    )

    if not key:

        return pd.DataFrame()

    try:

        today = datetime.now().date()

        url = (
            "https://api.tradingeconomics.com/"
            "calendar/country/United%20States/"
            "importance/3"
        )

        response = requests.get(
            url,
            params={
                "c": key,
                "d1": today,
                "d2": today
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
# NEWS HELPERS
# ============================================================

def parse_news_date(value):
    """
    Convert a feed/API date into a timezone-aware datetime.
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


def clean_title(title):
    """
    Remove common Google News source suffixes.
    """

    if not title:
        return ""

    title = str(title).strip()

    # Google News often formats headlines like:
    #
    # "Gold rises today - Reuters"
    #
    # Remove the source suffix when possible.

    if " - " in title:

        parts = title.rsplit(
            " - ",
            1
        )

        if len(parts) == 2:

            possible_source = parts[1].strip()

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
    """
    Add an article only if it is recent and valid.
    """

    title = clean_title(title)

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

    if published_dt < cutoff:

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
    """
    Get recent gold/macro headlines.

    NewsAPI is used when NEWSAPI_KEY exists.

    Otherwise multiple Google News RSS searches are used.

    Only articles from the last NEWS_MAX_AGE_HOURS are accepted.
    """

    articles = []

    # ========================================================
    # NEWSAPI
    # ========================================================

    key = os.getenv(
        "NEWSAPI_KEY",
        ""
    )

    if key:

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
                    "apiKey": key
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
                    article.get(
                        "source",
                        {}
                    ).get(
                        "name",
                        ""
                    )
                )

        except Exception:
            pass

    # ========================================================
    # GOOGLE NEWS RSS FALLBACK
    # ========================================================

    # We deliberately use several focused searches rather
    # than one broad search.
    # ========================================================

    searches = [
        "gold futures gold price",
        "gold Federal Reserve Fed",
        "gold Treasury yields",
        "gold US dollar DXY",
        "gold inflation CPI PCE PPI"
    ]

    for search_term in searches:

        try:

            feed_url = (
                "https://news.google.com/rss/search?"
                f"q={requests.utils.quote(search_term)}"
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

        key = article["title"].lower().strip()

        if key not in unique:

            unique[key] = article

    articles = list(
        unique.values()
    )

    # ========================================================
    # SORT NEWEST FIRST
    # ========================================================

    articles.sort(
        key=lambda x: x["published_dt"],
        reverse=True
    )

    return articles[:20]


# ============================================================
# GOLD MARKET SCORING
# ============================================================

def score(
    gold,
    dxy,
    treasury
):
    """
    Transparent first-pass gold-market scoring system.

    This is NOT a predictive trading model.

    Gold:
        Rising = bullish
        Falling = bearish

    DXY:
        Falling = bullish gold
        Rising = bearish gold

    10Y Treasury:
        Falling = bullish gold
        Rising = bearish gold

    Treasury gets less weight than Gold/DXY because the
    Treasury data is daily rather than intraday.
    """

    score_value = 0

    reasons = []

    # ========================================================
    # GOLD
    # ========================================================

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

        dxy_pct = dxy["pct"]

        if dxy_pct < -0.15:

            score_value += 2

            reasons.append(
                "DXY is falling strongly, "
                "which generally supports gold."
            )

        elif dxy_pct < -0.03:

            score_value += 1

            reasons.append(
                "DXY is slightly lower, "
                "which is supportive of gold."
            )

        elif dxy_pct > 0.15:

            score_value -= 2

            reasons.append(
                "DXY is rising strongly, "
                "which generally pressures gold."
            )

        elif dxy_pct > 0.03:

            score_value -= 1

            reasons.append(
                "DXY is slightly higher, "
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
    # 10-Y TREASURY
    # ========================================================

    if not treasury or "value" not in treasury:

        reasons.append(
            "10-year Treasury data unavailable."
        )

    else:

        reasons.append(
            "10-year Treasury yield is available "
            "as macroeconomic context."
        )

        # We don't assign an intraday score here because
        # DGS10 is a daily FRED series.

    # ========================================================
    # FINAL BIAS
    # ========================================================

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

    return (
        bias,
        confidence,
        reasons
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
            f"{x // 60} minute"
            if x == 60
            else f"{x // 60} minutes"
        )
    ),
    index=2
)

st.sidebar.info(
    "The dashboard refreshes all available data "
    "at the selected interval."
)

st.sidebar.warning(
    "Gold futures and DXY can move quickly. "
    "This dashboard is for monitoring and education, "
    "not execution."
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

treasury = fred_series(
    "DGS10"
)

events = trading_economics_calendar()

articles = news()

bias, confidence, reasons = score(
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
# 10 YEAR
# ============================================================

if treasury and "value" in treasury:

    treasury_date = treasury.get(
        "date",
        ""
    )

    column3.metric(
        "🇺🇸 10Y Treasury",
        f"{treasury['value']:.2f}%",
        help=(
            "10-Year Treasury Constant Maturity Rate "
            f"from FRED. Latest observation: "
            f"{treasury_date}"
        )
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
# MARKET ANALYSIS
# ============================================================

st.subheader(
    "What the monitor sees"
)

for reason in reasons:

    st.write(
        "• " + reason
    )


st.warning(
    "This is an educational monitoring heuristic. "
    "It is not financial advice and is not a proven "
    "trading strategy."
)


# ============================================================
# 10Y DATA STATUS
# ============================================================

if treasury and "value" in treasury:

    st.caption(
        "10Y source: FRED — "
        f"latest observation {treasury.get('date', 'unknown')}. "
        "The 10Y FRED series is published daily, so it will "
        "not necessarily change every dashboard refresh."
    )

else:

    st.error(
        "The 10-Year Treasury data could not be retrieved "
        "from FRED during this refresh."
    )


# ============================================================
# ECONOMIC CALENDAR
# ============================================================

st.subheader(
    "📅 Today's high-importance economic events"
)

if events.empty:

    st.info(
        "No Trading Economics calendar data is configured. "
        "If you add a TE_API_KEY to Streamlit secrets, "
        "today's high-importance U.S. events can appear here."
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
    "📰 Recent Gold / Macro Headlines"
)

if articles:

    st.caption(
        f"Showing articles published within the last "
        f"{NEWS_MAX_AGE_HOURS} hours. "
        "Newest articles appear first."
    )

    for article in articles[:10]:

        published_dt = article[
            "published_dt"
        ]

        # Convert UTC to Eastern Time.
        eastern_time = (
            published_dt
            .astimezone()
        )

        formatted_time = (
            eastern_time.strftime(
                "%b %d, %Y at %I:%M %p"
            )
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
                f" — {source}"
            )

        else:

            source_text = ""

        st.markdown(
            f"**[{title}]({link})**  \n"
            f"🕒 {formatted_time}"
            f"{source_text}"
        )

        st.divider()

else:

    st.info(
        "No sufficiently recent gold/macro headlines "
        "were returned during this refresh."
    )


# ============================================================
# REFRESH STATUS
# ============================================================

current_time = datetime.now()

st.caption(
    "Last dashboard refresh: "
    + current_time.strftime(
        "%Y-%m-%d %I:%M:%S %p"
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
