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
    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# WEBULL GOLD
# ============================================================

def get_webull_gold():

    print("Requesting Webull Gold page...")

    response = requests.get(
        WEBULL_URL,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    html = response.text

    print(
        f"Webull page received: "
        f"{len(html):,} characters"
    )

    price = None

    # Look for several common Webull
    # representations of the last price.

    patterns = [
        r'"lastPrice"\s*:\s*"?([0-9,]+\.[0-9]+)"?',
        r'"last"\s*:\s*"?([0-9,]+\.[0-9]+)"?',
        r'"price"\s*:\s*"?([0-9,]+\.[0-9]+)"?',
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            html,
            re.IGNORECASE,
        )

        if not match:
            continue

        try:

            candidate = float(
                match.group(1).replace(
                    ",",
                    "",
                )
            )

            # Sanity check for Gold.

            if 3000 <= candidate <= 10000:

                price = candidate
                break

        except Exception:
            continue

    if price is None:

        raise RuntimeError(
            "Webull responded successfully, "
            "but the Gold price could not be "
            "identified on the public page."
        )

    # Try to find Webull's displayed
    # percentage change.

    change_pct = None

    pct_patterns = [
        r'"changePercent"\s*:\s*"?([^"}]+)"?',
        r'"changePct"\s*:\s*"?([^"}]+)"?',
    ]

    for pattern in pct_patterns:

        match = re.search(
            pattern,
            html,
            re.IGNORECASE,
        )

        if not match:
            continue

        try:

            text = (
                match.group(1)
                .replace("%", "")
                .replace(",", "")
                .strip()
            )

            value = float(text)

            # If Webull supplies a decimal
            # fraction, convert it to percent.

            if abs(value) < 1:

                value *= 100

            change_pct = value

            break

        except Exception:
            continue

    retrieved = now_utc()

    print(
        f"Gold price: ${price:,.2f}"
    )

    if change_pct is not None:

        print(
            f"Gold change: "
            f"{change_pct:+.2f}%"
        )

    else:

        print(
            "Gold change: unavailable"
        )

    return {
        "gold_price": price,
        "gold_pct": change_pct,
        "gold_retrieved_at_utc": retrieved,
        "gold_source": WEBULL_URL,
        "contract": "1OZV6.CMX",
        "contract_name":
            "1-Ounce Gold — October 2026",
    }


# ============================================================
# TREASURY 10-YEAR
# ============================================================

def get_treasury():

    print(
        "Requesting U.S. Treasury data..."
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
            "The Treasury page returned "
            "no tables."
        )

    table = None

    for candidate in tables:

        text = " ".join(
            str(column)
            for column in candidate.columns
        )

        if "10 Yr" in text:

            table = candidate
            break

    if table is None:

        raise RuntimeError(
            "Could not find the Treasury "
            "10-year column."
        )

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

    date_column = None
    yield_column = None

    for column in table.columns:

        name = str(column)

        if (
            date_column is None
            and "Date" in name
        ):

            date_column = column

        if (
            yield_column is None
            and "10 Yr" in name
        ):

            yield_column = column

    if (
        date_column is None
        or yield_column is None
    ):

        raise RuntimeError(
            "Treasury Date or 10 Yr "
            "column could not be identified."
        )

    table[yield_column] = pd.to_numeric(
        table[yield_column],
        errors="coerce",
    )

    table = table.dropna(
        subset=[yield_column]
    )

    if table.empty:

        raise RuntimeError(
            "No valid Treasury 10-year "
            "values were found."
        )

    latest = table.iloc[-1]

    yield_value = float(
        latest[yield_column]
    )

    treasury_date = str(
        latest[date_column]
    )

    retrieved = now_utc()

    print(
        f"10Y Treasury: "
        f"{yield_value:.2f}%"
    )

    print(
        f"Treasury date: "
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

    # 404 means this is a brand-new
    # history file.

    if response.status_code == 404:

        print(
            "prediction_history.csv "
            "does not exist yet."
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


# ============================================================
# SAVE HISTORY
# ============================================================

def github_save_history(
    dataframe,
    sha,
):

    print(
        "Saving prediction_history.csv "
        "to GitHub..."
    )

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

    # Only send SHA when updating an
    # existing file.

    if sha is not None:

        payload["sha"] = sha

    response = requests.put(
        url,
        headers=github_headers(),
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    result = response.json()

    print(
        "GitHub save successful."
    )

    print(
        "Commit:"
        f" {result.get('commit', {}).get('sha', 'unknown')}"
    )


# ============================================================
# MAIN COLLECTION
# ============================================================

def main():

    print(
        "======================================"
    )

    print(
        "Gold Market Monitor"
    )

    print(
        "Starting market collection..."
    )

    print(
        "======================================"
    )

    # --------------------------------------------------------
    # Collect Gold
    # --------------------------------------------------------

    gold = get_webull_gold()

    # --------------------------------------------------------
    # Collect Treasury
    # --------------------------------------------------------

    treasury = get_treasury()

    # --------------------------------------------------------
    # Load existing history if available
    # --------------------------------------------------------

    history, sha = (
        github_get_history()
    )

    # --------------------------------------------------------
    # Build new record
    # --------------------------------------------------------

    record = {

        "collected_at_utc":
            now_utc(),

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

    # --------------------------------------------------------
    # Create or extend history
    # --------------------------------------------------------

    if history.empty:

        history = new_row

    else:

        # Add any new columns to the
        # existing history.

        for column in new_row.columns:

            if column not in history.columns:

                history[column] = None

        # Add missing legacy columns
        # to the new record.

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
    # Save
    # --------------------------------------------------------

    github_save_history(
        history,
        sha,
    )

    print(
        "======================================"
    )

    print(
        "COLLECTION COMPLETE"
    )

    print(
        f"Gold: ${gold['gold_price']:,.2f}"
    )

    print(
        f"Gold %: "
        f"{gold['gold_pct']}"
    )

    print(
        f"10Y: "
        f"{treasury['treasury_yield']:.2f}%"
    )

    print(
        f"Rows in history: "
        f"{len(history)}"
    )

    print(
        "======================================"
    )


if __name__ == "__main__":
    main()
