import base64
import io
import os
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import feedparser
import pandas as pd
import requests
import yfinance as yf

from bs4 import BeautifulSoup


ET = ZoneInfo("America/New_York")

WEBULL_URL = (
    "https://www.webull.com/quote/COMEX-1OZV6"
)

REPO = os.getenv(
    "GITHUB_REPO",
    "smd-netizen/gold-market-monitor"
)

HISTORY_PATH = "prediction_history.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}


def now_utc():

    return datetime.now(
        timezone.utc
    )


# =========================================================
# GOLD
# =========================================================

def get_gold():

    retrieved = now_utc()

    response = requests.get(
        WEBULL_URL,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    text = soup.get_text(
        " ",
        strip=True,
    )

    # Make absolutely sure we are looking at
    # the intended contract.

    required = [
        "1OZV6",
        "1-Ounce Gold OCT 26",
        "COMEX",
    ]

    for item in required:

        if item not in text:

            raise RuntimeError(
                f"Expected contract information "
                f"not found: {item}"
            )


    # Current public-page quote format.

    pattern = (
        r"1-Ounce Gold OCT 26\s+"
        r"COMEX\s+"
        r"([\d,]+\.\d{2})\s+"
        r"([+-]?[\d,]+\.\d{2})\s+"
        r"([+-]?[\d,]+\.\d{2})%"
    )

    match = re.search(
        pattern,
        text,
    )

    if not match:

        raise RuntimeError(
            "Could not parse the Webull "
            "1OZV6 quote."
        )


    price = float(
        match.group(1).replace(",", "")
    )

    change = float(
        match.group(2).replace(",", "")
    )

    pct = float(
        match.group(3)
    )


    def extract_number(label):

        result = re.search(
            label
            + r"\s+([\d,]+\.\d{2})",
            text,
        )

        if not result:

            return None

        return float(
            result.group(1)
            .replace(",", "")
        )


    high = extract_number(
        "HIGH"
    )

    low = extract_number(
        "LOW"
    )

    previous_settlement = extract_number(
        "PREV SETTLE"
    )


    return {

        "price": price,

        "change": change,

        "pct": pct,

        "high": high,

        "low": low,

        "previous_settlement":
            previous_settlement,

        "retrieved_at_utc":
            retrieved.isoformat(),

    }


# =========================================================
# DXY
# =========================================================

def get_dxy():

    retrieved = now_utc()

    ticker = yf.Ticker(
        "DX-Y.NYB"
    )

    data = ticker.history(
        period="2d",
        interval="5m",
        auto_adjust=False,
        prepost=True,
    )

    if data.empty:

        raise RuntimeError(
            "No DXY data returned."
        )


    close = (
        pd.to_numeric(
            data["Close"],
            errors="coerce",
        )
        .dropna()
    )

    if close.empty:

        raise RuntimeError(
            "No valid DXY values."
        )


    price = float(
        close.iloc[-1]
    )


    local_index = (
        pd.to_datetime(
            close.index,
            utc=True,
        )
        .tz_convert(ET)
    )


    today = close[
        local_index.date
        == retrieved
        .astimezone(ET)
        .date()
    ]


    if len(today) > 0:

        opening_value = float(
            today.iloc[0]
        )

    else:

        opening_value = price


    if opening_value != 0:

        percentage = (
            (price / opening_value)
            - 1
        ) * 100

    else:

        percentage = 0


    return {

        "price": price,

        "pct": percentage,

        "retrieved_at_utc":
            retrieved.isoformat(),

    }


# =========================================================
# 10-YEAR TREASURY
# =========================================================

def get_ten_year():

    retrieved = now_utc()

    url = (
        "https://fred.stlouisfed.org/"
        "graph/fredgraph.csv?id=DGS10"
    )

    data = pd.read_csv(
        url
    )

    data["DGS10"] = pd.to_numeric(
        data["DGS10"],
        errors="coerce",
    )

    data = data.dropna(
        subset=["DGS10"]
    )

    if data.empty:

        raise RuntimeError(
            "No 10Y Treasury data."
        )


    latest = data.iloc[-1]


    return {

        "value":
            float(latest["DGS10"]),

        "date":
            str(latest["DATE"]),

        "retrieved_at_utc":
            retrieved.isoformat(),

    }


# =========================================================
# NEWS
# =========================================================

def get_news():

    url = (
        "https://news.google.com/rss/search?"
        "q=("
        "gold OR "
        "gold futures OR "
        "Federal Reserve OR "
        "DXY OR "
        "Treasury yields"
        ")"
        "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )

    feed = feedparser.parse(
        url
    )

    current_time = now_utc()

    articles = []


    for entry in feed.entries:

        if not entry.get(
            "published_parsed"
        ):

            continue


        published = datetime(
            *entry.published_parsed[:6],
            tzinfo=timezone.utc,
        )


        age = (
            current_time
            - published
        )


        # Reject future-dated articles.

        if age < timedelta(
            minutes=-5
        ):

            continue


        # Only keep last 48 hours.

        if age > timedelta(
            hours=48
        ):

            continue


        articles.append({

            "published_et":
                published
                .astimezone(ET)
                .isoformat(),

            "title":
                entry.get(
                    "title",
                    "",
                ),

            "link":
                entry.get(
                    "link",
                    "",
                ),

        })


    articles.sort(
        key=lambda x:
        x["published_et"],
        reverse=True,
    )


    return articles[:10]


# =========================================================
# PREDICTION ENGINE
# =========================================================

def analyze(
    gold,
    dxy,
    treasury,
):

    score = 0

    reasons = []


    # GOLD MOMENTUM

    if gold["pct"] > 0.30:

        score += 2

        reasons.append(
            "Gold is rising strongly."
        )

    elif gold["pct"] > 0.05:

        score += 1

        reasons.append(
            "Gold is rising."
        )

    elif gold["pct"] < -0.30:

        score -= 2

        reasons.append(
            "Gold is falling strongly."
        )

    elif gold["pct"] < -0.05:

        score -= 1

        reasons.append(
            "Gold is falling."
        )


    # DXY

    if dxy["pct"] < -0.15:

        score += 2

        reasons.append(
            "DXY is falling."
        )

    elif dxy["pct"] < -0.03:

        score += 1

        reasons.append(
            "DXY is slightly lower."
        )

    elif dxy["pct"] > 0.15:

        score -= 2

        reasons.append(
            "DXY is rising."
        )

    elif dxy["pct"] > 0.03:

        score -= 1

        reasons.append(
            "DXY is slightly higher."
        )


    # Current model remains conservative.

    if score >= 3:

        bias = "BULLISH"

        confidence = min(
            10,
            6 + score - 3,
        )

    elif score <= -3:

        bias = "BEARISH"

        confidence = min(
            10,
            6 + abs(score) - 3,
        )

    else:

        bias = "NEUTRAL / WAIT"

        confidence = 5


    macro_bias = (
        "BULLISH"
        if dxy["pct"] < 0
        else "MIXED"
    )


    technical_bias = (
        "BULLISH"
        if gold["pct"] > 0
        else "BEARISH"
    )


    # VERY IMPORTANT:
    # A bullish prediction is NOT an automatic entry.

    setup = (
        "WAIT FOR CONFIRMATION"
    )


    resistance = gold["high"]

    support = gold["low"]


    breakout = (
        resistance + 2
        if resistance is not None
        else None
    )


    return {

        "bias":
            bias,

        "confidence":
            confidence,

        "macro_bias":
            macro_bias,

        "technical_bias":
            technical_bias,

        "setup":
            setup,

        "resistance":
            resistance,

        "support":
            support,

        "breakout":
            breakout,

        "reasons":
            " | ".join(
                reasons
            ),

    }


# =========================================================
# GITHUB
# =========================================================

def github_headers():

    token = os.getenv(
        "GITHUB_TOKEN",
        "",
    )

    if not token:

        raise RuntimeError(
            "GITHUB_TOKEN is not configured."
        )


    return {

        "Authorization":
            f"Bearer {token}",

        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            "2022-11-28",

    }


def read_history():

    headers = github_headers()

    url = (
        f"https://api.github.com/repos/"
        f"{REPO}/contents/"
        f"{HISTORY_PATH}?ref=main"
    )


    response = requests.get(
        url,
        headers=headers,
        timeout=20,
    )


    if response.status_code == 404:

        return pd.DataFrame()


    response.raise_for_status()


    content = base64.b64decode(
        response.json()["content"]
    )


    return pd.read_csv(
        io.BytesIO(content)
    )


def write_history(
    dataframe
):

    headers = github_headers()

    url = (
        f"https://api.github.com/repos/"
        f"{REPO}/contents/"
        f"{HISTORY_PATH}"
    )


    existing = requests.get(
        url,
        headers=headers,
        params={
            "ref": "main"
        },
        timeout=20,
    )


    payload = {

        "message":
            "Update prediction history",

        "content":
            base64.b64encode(
                dataframe
                .to_csv(
                    index=False
                )
                .encode("utf-8")
            ).decode("ascii"),

        "branch":
            "main",

    }


    if existing.status_code == 200:

        payload["sha"] = (
            existing.json()["sha"]
        )


    response = requests.put(
        url,
        headers=headers,
        json=payload,
        timeout=20,
    )


    response.raise_for_status()


# =========================================================
# MAIN
# =========================================================

def main():

    collected = now_utc()


    print(
        "Collecting gold..."
    )

    gold = get_gold()


    print(
        "Collecting DXY..."
    )

    dxy = get_dxy()


    print(
        "Collecting 10Y..."
    )

    treasury = get_ten_year()


    print(
        "Collecting news..."
    )

    news = get_news()


    analysis = analyze(
        gold,
        dxy,
        treasury,
    )


    # -----------------------------------------------------
    # DATA QUALITY
    # -----------------------------------------------------
    #
    # We deliberately mark gold as WARN because the public
    # page does not expose an independently verified exchange
    # timestamp.
    #
    # This prevents us from pretending the source is real-time.
    #

    data_quality = "WARN"


    row = {

        "collected_at_utc":
            collected.isoformat(),

        "legacy":
            False,


        # GOLD

        "gold_symbol":
            "1OZV6",

        "gold_price":
            gold["price"],

        "gold_pct":
            gold["pct"],

        "gold_change":
            gold["change"],

        "gold_high":
            gold["high"],

        "gold_low":
            gold["low"],

        "gold_prev_settle":
            gold[
                "previous_settlement"
            ],

        "gold_retrieved_at_utc":
            gold[
                "retrieved_at_utc"
            ],

        "gold_status":
            "PUBLIC_PAGE_RETRIEVAL_TIME_ONLY",


        # DXY

        "dxy":
            dxy["price"],

        "dxy_pct":
            dxy["pct"],

        "dxy_retrieved_at_utc":
            dxy[
                "retrieved_at_utc"
            ],


        # 10Y

        "teny":
            treasury["value"],

        "teny_date":
            treasury["date"],

        "teny_retrieved_at_utc":
            treasury[
                "retrieved_at_utc"
            ],


        # QUALITY

        "data_quality":
            data_quality,


        "news_count":
            len(news),

        **analysis,

    }


    history = read_history()


    history = pd.concat(
        [
            history,
            pd.DataFrame(
                [row]
            ),
        ],
        ignore_index=True,
    )


    write_history(
        history
    )


    print(
        "Prediction successfully recorded."
    )

    print(row)


if __name__ == "__main__":

    main()
