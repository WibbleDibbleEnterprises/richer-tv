"""
Richer Sounds OLED TV price watcher.

Checks the OLED TVs listing page, and emails an alert when:
  - a TV's price newly drops below PRICE_THRESHOLD, or
  - a TV that is already under PRICE_THRESHOLD drops even further.

Designed to run twice a day (9am / 3pm Europe/Dublin time) via GitHub Actions.
Because GitHub Actions cron only runs in UTC, this script is triggered more
often than needed and checks the *actual* Dublin local time itself before
doing any work — so it self-corrects for daylight saving automatically.
"""

import asyncio
import json
import os
import re
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

URL = (
    "https://euro.richersounds.ie/c-15-oledtvs.aspx?swapstore=1"
    "&pgnum=1&sort=&l=3&c3=1179&v3=48+to+50+Inch~55+to+58+Inch"
)
STATE_FILE = Path(__file__).parent / "state.json"
PRICE_THRESHOLD = 750.0
TARGET_HOURS = {9, 15}  # 9am and 3pm, Dublin local time
TIMEZONE = "Europe/Dublin"

PRICE_RE = re.compile(r"€\s?([\d,]+\.\d{2})")


def in_target_window() -> bool:
    """Only do real work when it's actually 9am or 3pm in Dublin."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    return now.hour in TARGET_HOURS


async def scrape_products():
    """Render the page in a real browser and pull out (name, price) pairs.

    NOTE: This site's exact HTML structure hasn't been directly inspected
    (it's JS-rendered and wasn't visible via a plain fetch). This function
    tries a few common product-tile selectors first, and falls back to a
    generic text-pattern scan if none of them match anything. The first
    real run's logs will show what was found — if it looks wrong or
    incomplete, share the log output and the selectors can be tightened.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)  # let client-side rendering settle

        products = []

        candidate_selectors = [
            ".product-item",
            ".productitem",
            ".product-tile",
            ".prod-item",
            "[class*='product']",
        ]
        for sel in candidate_selectors:
            tiles = await page.query_selector_all(sel)
            if tiles:
                for tile in tiles:
                    text = (await tile.inner_text()).strip()
                    match = PRICE_RE.search(text)
                    if match:
                        name = text.split("\n")[0][:120]
                        price = float(match.group(1).replace(",", ""))
                        products.append({"name": name, "price": price})
                if products:
                    break

        # Fallback: scan all page text for "<name line>" followed by a
        # line containing a euro price.
        if not products:
            body_text = await page.inner_text("body")
            lines = [ln.strip() for ln in body_text.split("\n") if ln.strip()]
            for i, line in enumerate(lines):
                match = PRICE_RE.search(line)
                if match:
                    price = float(match.group(1).replace(",", ""))
                    name = lines[i - 1] if i > 0 else f"Unnamed item (line {i})"
                    products.append({"name": name, "price": price})

        await browser.close()
        return products


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def send_email(alerts: list) -> None:
    user = os.environ["EMAIL_ADDRESS"]
    password = os.environ["EMAIL_APP_PASSWORD"]
    to = os.environ["ALERT_TO_EMAIL"]

    lines = ["TVs under €750 on Richer Sounds (OLED TVs page):\n"]
    for a in alerts:
        lines.append(f"- {a['name']}: €{a['price']:.2f}  ({a['reason']})")
    lines.append(f"\n{URL}")
    body = "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"TV price alert: {len(alerts)} deal(s) under €750"
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, password)
        server.sendmail(user, [to], msg.as_string())


def main() -> None:
    if not in_target_window():
        print("Not 9am or 3pm Dublin time right now — skipping this run.")
        return

    products = asyncio.run(scrape_products())
    if not products:
        print("WARNING: found 0 products. Selectors likely need adjusting "
              "— check the page structure and update candidate_selectors.")
        return

    print(f"Found {len(products)} product(s):")
    for p in products:
        print(f"  - {p['name']}: €{p['price']:.2f}")

    state = load_state()
    alerts = []

    for p in products:
        name, price = p["name"], p["price"]
        prev = state.get(name)

        if price < PRICE_THRESHOLD:
            if prev is None or not prev.get("under_threshold"):
                alerts.append({"name": name, "price": price,
                                "reason": "newly under €750"})
            elif prev.get("under_threshold") and price < prev.get("last_price", price):
                alerts.append({"name": name, "price": price,
                                "reason": "dropped even further"})
            state[name] = {"last_price": price, "under_threshold": True}
        else:
            state[name] = {"last_price": price, "under_threshold": False}

    save_state(state)

    if alerts:
        send_email(alerts)
        print(f"Alert email sent for {len(alerts)} TV(s).")
    else:
        print("No new alerts this run.")


if __name__ == "__main__":
    main()
