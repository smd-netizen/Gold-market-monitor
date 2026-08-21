import base64
import io
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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
    "https://www.marketwatch.com/investing/index/dxy"
)

ET = ZoneInfo("America/New_York")

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
    return datetime.now(
        timezone.utc
    )


def iso_utc():
    return now_utc().isoformat()


# ============================================================
# SAFE NUMBER PARSER
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

    print(
        "Requesting Webull public Gold page..."
    )

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

    # --------------------------------------------------------
    # Gold price
    # --------------------------------------------------------

    price = None

    price_patterns = [

        r'"lastPrice"\s*:\s*"?(?:\$)?([0-9,]+\.[0-9]+)"?',

        r'"last"\s*:\s*"?(?:\$)?([0-9,]+\.[0-9]+)"?',

        r'"price"\s*:\s*"?(?:\$)?([0-9,]+\.[0-9]+)"?',

    ]

    for pattern in price_patterns:

        matches = re.findall(
            pattern,
            html,
            re.IGNORECASE,
        )

        for match in matches:

            candidate = parse_number(
                match
            )

            if candidate is not None and (
                3000 <= candidate <= 10000
            ):

                price = candidate
                break

        if price is not None:
            break

    if price is None:

        raise RuntimeError(
            "Webull returned a page, but "
            "the Gold price could not be "
            "identified."
        )

    # --------------------------------------------------------
    # Gold percentage change
    # --------------------------------------------------------

    gold_pct = None

    pct_patterns = [

        r'"changePercent"\s*:\s*"?(?:\+)?(-?[0-9]+(?:\.[0-9]+)?)%?"?',

        r'"changePct"\s*:\s*"?(?:\+)?(-?[0-9]+(?:\.[0-9]+)?)%?"?',

        r'"percentChange"\s*:\s*"?(?:\+)?(-?[0-9]+(?:\.[0-9]+)?)%?"?',

    ]

    for pattern in pct_patterns:

        matches = re.findall(
            pattern,
            html,
            re.IGNORECASE,
        )

        for match in matches:

            candidate = parse_number(
                match
            )

            if candidate is None:
                continue

            # Avoid accidentally accepting
            # an unrelated percentage.

            if abs(candidate) <= 20:

                gold_pct = candidate
                break

        if gold_pct is not None:
            break

    # --------------------------------------------------------
    # Fallback: locate percentage-looking
    # values near Gold quote information.
    # --------------------------------------------------------

    if gold_pct is None:

        gold_section = re.search(
            r"1OZV6.{0,30000}",
            html,
            re.IGNORECASE | re.DOTALL,
        )

        if gold_section:

            section = (
                gold_section.group(0)
            )

            candidates = re.findall(
                r"[-+]?[0-9]+(?:\.[0-9]+)?%",
                section,
            )

            for candidate in candidates:

                value = parse_number(
                    candidate
                )

                if (
                    value is not None
                    and abs(value) <= 20
                ):

                    gold_pct = value
                    break

    retrieved = iso_utc()

    print(
        f"Gold: ${price:,.2f}"
    )

    if gold_pct is None:

        print(
            "Gold % change: unavailable"
        )

    else:

        print(
            f"Gold % change: "
            f"{gold_pct:+.2f}%"
        )

    return {
        "gold_price": price,
        "gold_pct": gold_pct,
        "gold_retrieved_at_utc":
            retrieved,
        "gold_source":
            WEBULL_URL,
        "contract":
            "1OZV6.CMX",
        "contract_name":
            "1-Ounce Gold — October 2026",
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
        io.StringIO(
            response.text
        )
    )

    if not tables:

        raise RuntimeError(
            "Treasury page returned no tables."
        )

    valid_tables = []

    for table in tables:

        # Flatten MultiIndex columns.

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

            if (
                date_column is None
                and column.lower() == "date"
            ):

                date_column = column

            if (
                ten_year_column is None
                and "10 Yr" in column
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

    # Use the table containing the most
    # recent valid date, rather than simply
    # taking the last table returned.

    best = None

    for table, date_col, yield_col in valid_tables:

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

    _, table, date_col, yield_col = best

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

    # Only accept realistic 10Y yields.
    # This also protects against accidentally
    # reading another numeric column.

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
        "treasury_yield":
            yield_value,

        "treasury_date":
            treasury_date,

        "treasury_retrieved_at_utc":
            retrieved,
    }


# ============================================================
# DXY
# ============================================================

def get_dxy():

    print(
        "Requesting DXY data..."
    )

    response = requests.get(
        DXY_URL,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    html = response.text

    dxy = None
    dxy_pct = None

    # MarketWatch page patterns.

    price_patterns = [

        r'"value"\s*:\s*"?(9[0-9](?:\.[0-9]+)?)"?',

        r'"last"\s*:\s*"?(9[0-9](?:\.[0-9]+)?)"?',

        r'"price"\s*:\s*"?(9[0-9](?:\.[0-9]+)?)"?',

    ]

    for pattern in price_patterns:

        matches = re.findall(
            pattern,
            html,
            re.IGNORECASE,
        )

        for match in matches:

            candidate = parse_number(
                match
            )

            if (
                candidate is not None
                and 80 <= candidate <= 120
            ):

                dxy = candidate
                break

        if dxy is not None:
            break

    pct_patterns = [

        r'"changePercent"\s*:\s*"?(?:\+)?(-?[0-9]+(?:\.[0-9]+)?)%?"?',

        r'"percentChange"\s*:\s*"?(?:\+)?(-?[0-9]+(?:\.[0-9]+)?)%?"?',

    ]

    for pattern in pct_patterns:

        matches = re.findall(
            pattern,
            html,
            re.IGNORECASE,
        )

        for match in matches:

            candidate = parse_number(
                match
            )

            if (
                candidate is not None
                and abs(candidate) <= 10
            ):

                dxy_pct = candidate
                break

        if dxy_pct is not None:
            break

    if dxy is None:

        raise RuntimeError(
            "DXY page responded, but the "
            "DXY value could not be identified."
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

    else:

        print(
            "DXY change: unavailable"
        )

    return {
        "dxy_price":
            dxy,

        "dxy_pct":
            dxy_pct,

        "dxy_retrieved_at_utc":
            retrieved,

        "dxy_source":
            DXY_URL,
    }


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

        print(
            "No prediction history exists. "
            "Creating a new one."
        )

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

    gold = get_webull_gold()

    treasury = get_treasury()

    dxy = get_dxy()

    history, sha = (
        github_get_history()
    )

    record = {

        "collected_at_utc":
            iso_utc(),

        "gold_price":
            gold["gold_price"],

        "gold_pct":
            gold["gold_pct"],

        "gold_retrieved_at_utc":
            gold[
                "gold_retrieved_at_utc"
            ],

        "gold_source":
            gold["gold_source"],

        "contract":
            gold["contract"],

        "contract_name":
            gold["contract_name"],

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

        "treasury_yield":
            treasury[
                "treasury_yield"
            ],

        "treasury_date":
            treasury[
                "treasury_date"
            ],

        "treasury_retrieved_at_utc":
            treasury[
                "treasury_retrieved_at_utc"
            ],
    }

    new_row = pd.DataFrame(
        [record]
    )

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

    github_save_history(
        history,
        sha,
    )

    print(
        "=========================================="
    )

    print(
        "COLLECTION COMPLETE"
    )

    print(
        f"Gold: ${gold['gold_price']:,.2f}"
    )

    print(
        f"Gold %: {gold['gold_pct']}"
    )

    print(
        f"DXY: {dxy['dxy_price']:.3f}"
    )

    print(
        f"DXY %: {dxy['dxy_pct']}"
    )

    print(
        f"10Y: {treasury['treasury_yield']:.3f}%"
    )

    print(
        f"Rows: {len(history)}"
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()
