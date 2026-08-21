import base64
import io
import os
import re
from datetime import datetime, timezone

import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

REPO = os.getenv(
    "GITHUB_REPO",
    "smd-netizen/gold-market-monitor",
)

TOKEN = os.getenv("GITHUB_TOKEN")

HISTORY_FILE = "prediction_history.csv"

WEBULL_URL = (
    "https://www.webull.com/quote/COMEX-1OZV6"
)

TREASURY_URL = (
    "https://home.treasury.gov/"
    "resource-center/data-chart-center/"
    "interest-rates/TextView"
    "?type=daily_treasury_yield_curve"
    "&field_tdr_date_value=2026"
)

DXY_URL = (
    "https://finance.yahoo.com/quote/DX-Y.NYB/"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# TIME
# ============================================================

def now_utc():
    return datetime.now(timezone.utc)


def iso_utc():
    return now_utc().isoformat()


# ============================================================
# SAFE NUMBER
# ============================================================

def parse_number(value):

    if value is None:
        return None

    try:
        text = (
            str(value)
            .replace(",", "")
            .replace("%", "")
            .strip()
        )

        return float(text)

    except Exception:
        return None


# ============================================================
# WEBULL GOLD
# ============================================================

def get_webull_gold():

    print("Requesting Webull public Gold page...")

    response = requests.get(
        WEBULL_URL,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    html = response.text

    print(
        f"Webull response: "
        f"{len(html):,} characters"
    )

    price = None

    price_patterns = [
        (
            r'"lastPrice"\s*:\s*"?(?:\$)?'
            r'([0-9,]+\.[0-9]+)"?'
        ),
        (
            r'"last"\s*:\s*"?(?:\$)?'
            r'([0-9,]+\.[0-9]+)"?'
        ),
        (
            r'"price"\s*:\s*"?(?:\$)?'
            r'([0-9,]+\.[0-9]+)"?'
        ),
    ]

    for pattern in price_patterns:

        matches = re.findall(
            pattern,
            html,
            re.IGNORECASE,
        )

        for match in matches:

            candidate = parse_number(match)

            if (
                candidate is not None
                and 3000 <= candidate <= 10000
            ):
                price = candidate
                break

        if price is not None:
            break

    if price is None:

        raise RuntimeError(
            "Webull returned a page, but "
            "the Gold price could not be identified."
        )

    gold_pct = None

    pct_patterns = [
        (
            r'"changePercent"\s*:\s*"?(?:\+)?'
            r'(-?[0-9]+(?:\.[0-9]+)?)%?"?'
        ),
        (
            r'"changePct"\s*:\s*"?(?:\+)?'
            r'(-?[0-9]+(?:\.[0-9]+)?)%?"?'
        ),
        (
            r'"percentChange"\s*:\s*"?(?:\+)?'
            r'(-?[0-9]+(?:\.[0-9]+)?)%?"?'
        ),
    ]

    for pattern in pct_patterns:

        matches = re.findall(
            pattern,
            html,
            re.IGNORECASE,
        )

        for match in matches:

            candidate = parse_number(match)

            if (
                candidate is not None
                and abs(candidate) <= 20
            ):
                gold_pct = candidate
                break

        if gold_pct is not None:
            break

    if gold_pct is None:

        change_patterns = [
            (
                r'"change"\s*:\s*"?(?:\+)?'
                r'(-?[0-9]+(?:\.[0-9]+)?)"?'
            ),
            (
                r'"changeValue"\s*:\s*"?(?:\+)?'
                r'(-?[0-9]+(?:\.[0-9]+)?)"?'
            ),
        ]

        for pattern in change_patterns:

            matches = re.findall(
                pattern,
                html,
                re.IGNORECASE,
            )

            for match in matches:

                candidate = parse_number(match)

                if (
                    candidate is not None
                    and abs(candidate) <= 200
                ):

                    calculated_pct = (
                        candidate / price * 100
                    )

                    if abs(calculated_pct) <= 20:

                        gold_pct = calculated_pct
                        break

            if gold_pct is not None:
                break

    retrieved = iso_utc()

    print(
        f"Gold: ${price:,.2f}"
    )

    if gold_pct is not None:

        print(
            f"Gold % change: "
            f"{gold_pct:+.2f}%"
        )

    else:

        print(
            "Gold % change: unavailable"
        )

    return {
        "gold_price": price,
        "gold_pct": gold_pct,
        "gold_retrieved_at_utc": retrieved,
        "gold_source": WEBULL_URL,
        "contract": "1OZV6.CMX",
        "contract_name": (
            "1-Ounce Gold — October 2026"
        ),
    }


# ============================================================
# TREASURY 10-YEAR
# ============================================================

def get_treasury():

    print(
        "Requesting official Treasury data..."
    )

    response = requests.get(
        TREASURY_URL,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    tables = pd.read_html(
        io.StringIO(response.text)
    )

    if not tables:

        raise RuntimeError(
            "Treasury page returned no tables."
        )

    valid_tables = []

    for table in tables:

        if isinstance(
            table.columns,
            pd.MultiIndex,
        ):

            table.columns = [
                " ".join(
                    str(part)
                    for part in column
                    if str(part) != "nan"
                ).strip()
                for column in table.columns
            ]

        columns = [
            str(column)
            for column in table.columns
        ]

        date_column = None
        ten_year_column = None

        for column in columns:

            clean = column.lower()

            if (
                date_column is None
                and clean == "date"
            ):

                date_column = column

            if (
                ten_year_column is None
                and (
                    "10 yr" in clean
                    or "10-year" in clean
                    or "10 year" in clean
                )
            ):

                ten_year_column = column

        if (
            date_column is not None
            and ten_year_column is not None
        ):

            valid_tables.append(
                (
                    table,
                    date_column,
                    ten_year_column,
                )
            )

    if not valid_tables:

        raise RuntimeError(
            "Could not find a Treasury table "
            "containing Date and 10 Yr."
        )

    best = None

    for (
        table,
        date_col,
        yield_col,
    ) in valid_tables:

        dates = pd.to_datetime(
            table[date_col],
            errors="coerce",
        )

        if dates.notna().any():

            newest = dates.max()

            if (
                best is None
                or newest > best[0]
            ):

                best = (
                    newest,
                    table,
                    date_col,
                    yield_col,
                )

    if best is None:

        raise RuntimeError(
            "Treasury tables contained no "
            "usable dates."
        )

    (
        _,
        table,
        date_col,
        yield_col,
    ) = best

    table = table.copy()

    table["_date"] = pd.to_datetime(
        table[date_col],
        errors="coerce",
    )

    table["_yield"] = pd.to_numeric(
        table[yield_col],
        errors="coerce",
    )

    table = table.dropna(
        subset=[
            "_date",
            "_yield",
        ]
    )

    table = table[
        (table["_yield"] >= 0)
        & (table["_yield"] <= 15)
    ]

    if table.empty:

        raise RuntimeError(
            "No realistic Treasury 10-year "
            "yield was found."
        )

    latest = (
        table
        .sort_values("_date")
        .iloc[-1]
    )

    yield_value = float(
        latest["_yield"]
    )

    treasury_date = (
        latest["_date"]
        .strftime("%Y-%m-%d")
    )

    retrieved = iso_utc()

    print(
        f"10Y Treasury: "
        f"{yield_value:.3f}%"
    )

    print(
        f"Treasury observation date: "
        f"{treasury_date}"
    )

    return {
        "treasury_yield": yield_value,
        "treasury_date": treasury_date,
        "treasury_retrieved_at_utc": retrieved,
    }


# ============================================================
# DXY
# ============================================================

def get_dxy():

    print(
        "Requesting DXY data..."
    )

    quote_url = (
        "https://query1.finance.yahoo.com/"
        "v8/finance/chart/DX-Y.NYB"
        "?range=1d&interval=1m"
    )

    response = requests.get(
        quote_url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    chart = data.get(
        "chart",
        {},
    )

    results = chart.get(
        "result"
    )

    if not results:

        raise RuntimeError(
            "Yahoo Finance returned no DXY "
            "chart data."
        )

    result = results[0]

    meta = result.get(
        "meta",
        {},
    )

    dxy = parse_number(
        meta.get(
            "regularMarketPrice"
        )
    )

    previous_close = parse_number(
        meta.get(
            "previousClose"
        )
    )

    if dxy is None:

        raise RuntimeError(
            "Yahoo Finance returned DXY data "
            "but no current price."
        )

    dxy_pct = None

    if (
        previous_close is not None
        and previous_close != 0
    ):

        dxy_pct = (
            (dxy - previous_close)
            / previous_close
            * 100
        )

    if not (
        80 <= dxy <= 120
    ):

        raise RuntimeError(
            f"DXY value failed sanity check: "
            f"{dxy}"
        )

    retrieved = iso_utc()

    print(
        f"DXY: {dxy:.3f}"
    )

    if dxy_pct is not None:

        print(
            f"DXY change: "
            f"{dxy_pct:+.2f}%"
        )

    return {
        "dxy_price": dxy,
        "dxy_pct": dxy_pct,
        "dxy_retrieved_at_utc": retrieved,
        "dxy_source": quote_url,
    }


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

def calculate_technical_analysis(
    history,
    current_price,
):

    prices = pd.to_numeric(
        history.get(
            "gold_price",
            pd.Series(dtype=float),
        ),
        errors="coerce",
    ).dropna()

    prices = prices[
        (prices >= 3000)
        & (prices <= 10000)
    ]

    if len(prices) < 2:

        return {
            "technical_bias": "BUILDING DATA",
            "technical_score": 0,
            "support": current_price,
            "resistance": current_price,
            "ma20": current_price,
            "ma50": current_price,
        }

    # Use only the most recent collected
    # Webull observations.

    prices = prices.tail(50)

    ma20 = (
        prices.tail(20).mean()
        if len(prices) >= 20
        else prices.mean()
    )

    ma50 = prices.mean()

    recent = prices.tail(
        min(12, len(prices))
    )

    support = recent.min()
    resistance = recent.max()

    score = 0

    if current_price > ma20:
        score += 1
    else:
        score -= 1

    if current_price > ma50:
        score += 1
    else:
        score -= 1

    if len(prices) >= 4:

        short_change = (
            prices.iloc[-1]
            - prices.iloc[-4]
        )

        if short_change > 0:
            score += 1

        elif short_change < 0:
            score -= 1

    if score >= 2:

        bias = "BULLISH"

    elif score <= -2:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL / WAIT"

    return {
        "technical_bias": bias,
        "technical_score": float(score),
        "support": float(support),
        "resistance": float(resistance),
        "ma20": float(ma20),
        "ma50": float(ma50),
    }


# ============================================================
# MACRO ANALYSIS
# ============================================================

def calculate_macro(
    dxy,
    treasury,
):

    dxy_pct = dxy.get(
        "dxy_pct"
    )

    score = 0

    if (
        dxy_pct is not None
        and dxy_pct < 0
    ):

        score += 1

    elif (
        dxy_pct is not None
        and dxy_pct > 0
    ):

        score -= 1

    if score > 0:

        bias = "BULLISH"

    elif score < 0:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL / WAIT"

    confidence = 5

    if dxy_pct is not None:

        if abs(dxy_pct) >= 0.50:
            confidence = 9

        elif abs(dxy_pct) >= 0.25:
            confidence = 8

        elif abs(dxy_pct) >= 0.10:
            confidence = 7

        else:
            confidence = 5

    return {
        "macro_bias": bias,
        "macro_confidence": confidence,
    }


# ============================================================
# OVERALL SIGNAL
# ============================================================

def calculate_signal(
    technical,
    macro,
):

    technical_score = (
        technical["technical_score"]
    )

    macro_bias = macro["macro_bias"]

    score = technical_score

    if macro_bias == "BULLISH":
        score += 1

    elif macro_bias == "BEARISH":
        score -= 1

    if score >= 2:

        bias = "BULLISH"

    elif score <= -2:

        bias = "BEARISH"

    else:

        bias = "NEUTRAL / WAIT"

    confidence = min(
        10,
        max(
            3,
            int(
                5
                + abs(score)
            ),
        ),
    )

    return bias, confidence


# ============================================================
# PREDICTION TARGETS
# ============================================================

def calculate_targets(
    current_price,
    technical,
    overall_bias,
):

    resistance = technical["resistance"]
    support = technical["support"]

    if (
        overall_bias == "BULLISH"
    ):

        distance = max(
            0.25,
            (
                resistance
                - current_price
            ) * 0.15,
        )

        targets = {
            "target_15m":
                current_price + distance,

            "target_30m":
                current_price + distance * 1.5,

            "target_1h":
                current_price + distance * 2.0,

            "target_2h":
                current_price + distance * 2.75,
        }

    elif (
        overall_bias == "BEARISH"
    ):

        distance = max(
            0.25,
            (
                current_price
                - support
            ) * 0.15,
        )

        targets = {
            "target_15m":
                current_price - distance,

            "target_30m":
                current_price - distance * 1.5,

            "target_1h":
                current_price - distance * 2.0,

            "target_2h":
                current_price - distance * 2.75,
        }

    else:

        midpoint = (
            support
            + resistance
        ) / 2

        targets = {
            "target_15m":
                current_price,

            "target_30m":
                current_price,

            "target_1h":
                current_price,

            "target_2h":
                current_price,
        }

    return targets


# ============================================================
# GITHUB
# ============================================================

def github_headers():

    if not TOKEN:

        raise RuntimeError(
            "GITHUB_TOKEN is missing."
        )

    return {
        "Authorization":
            f"Bearer {TOKEN}",

        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            "2022-11-28",
    }


def github_get_history():

    url = (
        f"https://api.github.com/repos/"
        f"{REPO}/contents/"
        f"{HISTORY_FILE}?ref=main"
    )

    response = requests.get(
        url,
        headers=github_headers(),
        timeout=30,
    )

    if response.status_code == 404:

        return (
            pd.DataFrame(),
            None,
        )

    response.raise_for_status()

    data = response.json()

    content = base64.b64decode(
        data["content"]
    )

    history = pd.read_csv(
        io.BytesIO(content)
    )

    return (
        history,
        data["sha"],
    )


def github_save_history(
    dataframe,
    sha,
):

    csv_bytes = dataframe.to_csv(
        index=False
    ).encode("utf-8")

    encoded = base64.b64encode(
        csv_bytes
    ).decode("utf-8")

    url = (
        f"https://api.github.com/repos/"
        f"{REPO}/contents/"
        f"{HISTORY_FILE}"
    )

    payload = {
        "message":
            "Collect market data",

        "content":
            encoded,

        "branch":
            "main",
    }

    if sha is not None:
        payload["sha"] = sha

    response = requests.put(
        url,
        headers=github_headers(),
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    print(
        "GitHub prediction history updated."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=========================================="
    )

    print(
        "GOLD MARKET MONITOR - COLLECTION"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Collect live market data
    # --------------------------------------------------------

    gold = get_webull_gold()

    treasury = get_treasury()

    dxy = get_dxy()

    # --------------------------------------------------------
    # Load existing collected history
    # --------------------------------------------------------

    history, sha = github_get_history()

    # --------------------------------------------------------
    # Make sure gold history is usable
    # --------------------------------------------------------

    if not history.empty:

        if "gold_price" in history.columns:

            history["gold_price"] = pd.to_numeric(
                history["gold_price"],
                errors="coerce",
            )

    # --------------------------------------------------------
    # Technical analysis from Webull history
    # --------------------------------------------------------

    technical = calculate_technical_analysis(
        history,
        gold["gold_price"],
    )

    # --------------------------------------------------------
    # Macro analysis
    # --------------------------------------------------------

    macro = calculate_macro(
        dxy,
        treasury,
    )

    # --------------------------------------------------------
    # Overall signal
    # --------------------------------------------------------

    overall_bias, confidence = (
        calculate_signal(
            technical,
            macro,
        )
    )

    # --------------------------------------------------------
    # Targets
    # --------------------------------------------------------

    targets = calculate_targets(
        gold["gold_price"],
        technical,
        overall_bias,
    )

    # --------------------------------------------------------
    # New record
    # --------------------------------------------------------

    record = {

        "collected_at_utc":
            iso_utc(),

        "gold_price":
            gold["gold_price"],

        "gold_pct":
            gold["gold_pct"],

        "gold_retrieved_at_utc":
            gold["gold_retrieved_at_utc"],

        "gold_source":
            gold["gold_source"],

        "contract":
            gold["contract"],

        "contract_name":
            gold["contract_name"],

        "treasury_yield":
            treasury["treasury_yield"],

        "treasury_date":
            treasury["treasury_date"],

        "treasury_retrieved_at_utc":
            treasury[
                "treasury_retrieved_at_utc"
            ],

        "dxy_price":
            dxy["dxy_price"],

        "dxy_pct":
            dxy["dxy_pct"],

        "dxy_retrieved_at_utc":
            dxy[
                "dxy_retrieved_at_utc"
            ],

        "dxy_source":
            dxy["dxy_source"],

        "technical_bias":
            technical[
                "technical_bias"
            ],

        "technical_score":
            technical[
                "technical_score"
            ],

        "support":
            technical["support"],

        "resistance":
            technical["resistance"],

        "ma20":
            technical["ma20"],

        "ma50":
            technical["ma50"],

        "macro_bias":
            macro["macro_bias"],

        "macro_confidence":
            macro["macro_confidence"],

        "overall_bias":
            overall_bias,

        "confidence":
            confidence,

        "target_15m":
            targets["target_15m"],

        "target_30m":
            targets["target_30m"],

        "target_1h":
            targets["target_1h"],

        "target_2h":
            targets["target_2h"],

        "data_quality":
            "PASS",

    }

    new_row = pd.DataFrame(
        [record]
    )

    # --------------------------------------------------------
    # Append history
    # --------------------------------------------------------

    if history.empty:

        history = new_row

    else:

        for column in new_row.columns:

            if column not in history.columns:

                history[column] = None

        for column in history.columns:

            if column not in new_row.columns:

                new_row[column] = None

        new_row = new_row[
            history.columns
        ]

        history = pd.concat(
            [
                history,
                new_row,
            ],
            ignore_index=True,
        )

    # --------------------------------------------------------
    # Keep the history manageable
    # --------------------------------------------------------

    history = history.tail(
        2000
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    github_save_history(
        history,
        sha,
    )

    # --------------------------------------------------------
    # Final output
    # --------------------------------------------------------

    print(
        "=========================================="
    )

    print(
        "COLLECTION COMPLETE"
    )

    print(
        f"Gold: "
        f"${gold['gold_price']:,.2f}"
    )

    print(
        f"Gold %: "
        f"{gold['gold_pct']:+.2f}%"
        if gold["gold_pct"] is not None
        else "Gold %: unavailable"
    )

    print(
        f"Technical: "
        f"{technical['technical_bias']}"
    )

    print(
        f"Technical score: "
        f"{technical['technical_score']:.1f}"
    )

    print(
        f"Support: "
        f"${technical['support']:,.2f}"
    )

    print(
        f"Resistance: "
        f"${technical['resistance']:,.2f}"
    )

    print(
        f"MA20: "
        f"${technical['ma20']:,.2f}"
    )

    print(
        f"MA50: "
        f"${technical['ma50']:,.2f}"
    )

    print(
        f"Macro: "
        f"{macro['macro_bias']}"
    )

    print(
        f"Overall: "
        f"{overall_bias}"
    )

    print(
        f"Confidence: "
        f"{confidence}/10"
    )

    print(
        f"History rows: "
        f"{len(history)}"
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()
