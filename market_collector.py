import base64
import io
import os
import re
from datetime import datetime, timezone

import pandas as pd
import requests


REPO = os.getenv(
    "GITHUB_REPO",
    "smd-netizen/gold-market-monitor"
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


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def now_utc():
    return datetime.now(
        timezone.utc
    ).isoformat()


def get_webull_gold():

    response = requests.get(
        WEBULL_URL,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    html = response.text

    # Webull's public page contains the quote
    # information in the rendered page data.
    #
    # We deliberately look for the 1OZV6 quote
    # rather than scraping an unrelated Gold price.

    patterns = [

        r'"lastPrice"\s*:\s*"?( [0-9,]+\.[0-9]+ )"?',

        r'"last"\s*:\s*"?( [0-9,]+\.[0-9]+ )"?',

        r'"price"\s*:\s*"?( [0-9,]+\.[0-9]+ )"?',
    ]

    price = None

    for pattern in patterns:

        match = re.search(
            pattern.replace(" ", ""),
            html,
            re.IGNORECASE,
        )

        if match:

            try:

                candidate = float(
                    match.group(1)
                    .replace(",", "")
                )

                if (
                    3000
                    <= candidate
                    <= 10000
                ):

                    price = candidate
                    break

            except Exception:

                pass

    # Public-page fallback:
    # look near the 1OZV6 quote text.

    if price is None:

        section_match = re.search(
            r"1OZV6.{0,15000}",
            html,
            re.IGNORECASE | re.DOTALL,
        )

        if section_match:

            section = (
                section_match.group(0)
            )

            numbers = re.findall(
                r"\b[3-9][0-9]{2,3}\.[0-9]{2}\b",
                section,
            )

            for value in numbers:

                candidate = float(
                    value
                )

                if (
                    3000
                    <= candidate
                    <= 10000
                ):

                    price = candidate
                    break

    if price is None:

        raise RuntimeError(
            "Could not extract the Gold price "
            "from the Webull public 1OZV6 page."
        )

    # Webull displays a daily percentage change.
    change_pct = None

    pct_patterns = [

        r'"changePercent"\s*:\s*"?(.*?)"?[,}]',

        r'"changePct"\s*:\s*"?(.*?)"?[,}]',

    ]

    for pattern in pct_patterns:

        match = re.search(
            pattern,
            html,
            re.IGNORECASE,
        )

        if match:

            try:

                text = (
                    match.group(1)
                    .replace("%", "")
                    .replace(",", "")
                    .strip()
                )

                value = float(text)

                if abs(value) < 1:

                    value *= 100

                change_pct = value

                break

            except Exception:

                pass

    return {
        "gold_price": price,
        "gold_pct": change_pct,
        "gold_retrieved_at_utc": now_utc(),
        "gold_source": WEBULL_URL,
    }


def get_treasury():

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

    table = None

    for candidate in tables:

        columns = [
            str(c)
            for c in candidate.columns
        ]

        if any(
            "10 Yr" in c
            for c in columns
        ):

            table = candidate
            break

    if table is None:

        raise RuntimeError(
            "Could not find the Treasury "
            "10-year yield table."
        )

    # Flatten MultiIndex columns.

    if isinstance(
        table.columns,
        pd.MultiIndex
    ):

        table.columns = [
            " ".join(
                str(x)
                for x in col
                if str(x) != "nan"
            ).strip()
            for col in table.columns
        ]

    date_col = None
    yield_col = None

    for col in table.columns:

        text = str(col)

        if (
            date_col is None
            and "Date" in text
        ):

            date_col = col

        if (
            yield_col is None
            and "10 Yr" in text
        ):

            yield_col = col

    if (
        date_col is None
        or yield_col is None
    ):

        raise RuntimeError(
            "Could not identify Treasury "
            "Date / 10 Yr columns."
        )

    table = table[
        [date_col, yield_col]
    ].copy()

    table[yield_col] = pd.to_numeric(
        table[yield_col],
        errors="coerce",
    )

    table = table.dropna(
        subset=[
            yield_col
        ]
    )

    if table.empty:

        raise RuntimeError(
            "Treasury 10-year data is empty."
        )

    latest = table.iloc[-1]

    return {
        "treasury_yield":
            float(
                latest[yield_col]
            ),

        "treasury_date":
            str(
                latest[date_col]
            ),

        "treasury_retrieved_at_utc":
            now_utc(),
    }


def github_get_history():

    if not TOKEN:

        raise RuntimeError(
            "GITHUB_TOKEN is not configured."
        )

    url = (
        f"https://api.github.com/repos/"
        f"{REPO}/contents/"
        f"{HISTORY_FILE}?ref=main"
    )

    headers = {
        "Authorization":
            f"Bearer {TOKEN}",

        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            "2022-11-28",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    content = base64.b64decode(
        data["content"]
    )

    return (
        pd.read_csv(
            io.BytesIO(content)
        ),
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

    headers = {
        "Authorization":
            f"Bearer {TOKEN}",

        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            "2022-11-28",
    }

    payload = {
        "message":
            "Update market data",

        "content":
            encoded,

        "sha":
            sha,

        "branch":
            "main",
    }

    response = requests.put(
        url,
        headers=headers,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()


def main():

    print(
        "Starting Gold Market Monitor collection..."
    )

    gold = get_webull_gold()

    print(
        f"Gold: "
        f"${gold['gold_price']:,.2f}"
    )

    if gold["gold_pct"] is not None:

        print(
            f"Gold change: "
            f"{gold['gold_pct']:+.2f}%"
        )

    else:

        print(
            "Gold change: unavailable"
        )

    treasury = get_treasury()

    print(
        f"10Y Treasury: "
        f"{treasury['treasury_yield']:.2f}%"
    )

    history, sha = (
        github_get_history()
    )

    row = {}

    row.update(gold)

    row.update(treasury)

    row[
        "collected_at_utc"
    ] = now_utc()

    # Preserve the existing history.

    new_row = pd.DataFrame(
        [row]
    )

    for column in history.columns:

        if column not in new_row.columns:

            new_row[column] = None

    for column in new_row.columns:

        if column not in history.columns:

            history[column] = None

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
        "Market data saved successfully."
    )


if __name__ == "__main__":

    main()
