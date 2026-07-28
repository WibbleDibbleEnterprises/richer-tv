# Richer Sounds OLED TV price watcher

Checks https://euro.richersounds.ie/c-15-oledtvs.aspx daily at 9am and 3pm
(Dublin time) and emails you when:

- a TV's price newly drops **below €750**, or
- a TV that's already under €750 **drops even further**.

It does **not** re-alert you every time it re-checks a TV that's already
under €750 at the same price — only on a new drop.

## How the pieces fit together

- `scrape_and_alert.py` — loads the page in a real (headless) browser,
  reads off each TV's name and price, compares against `state.json`
  (what it saw last time), and emails you if something qualifies.
- `state.json` — the bot's memory. Committed back to the repo after every
  run so the next run remembers what it already alerted you about.
- `.github/workflows/tv-price-check.yml` — the schedule. Runs on GitHub's
  own servers, so your computer doesn't need to be on.

## One-time setup

### 1. Create the repo
Create a **new GitHub repository** (can be private) and upload all these
files, keeping the folder structure as-is (the `.github/workflows/` folder
must stay exactly where it is).

### 2. Get a Gmail App Password
This lets the bot send email from a Gmail account without your real password.

1. On the Gmail account you want to send *from*, turn on 2-Step Verification
   (Google Account → Security).
2. Go to Google Account → Security → **App Passwords**.
3. Create one (name it anything, e.g. "TV bot"), and copy the 16-character
   password it gives you.

(Don't want to use Gmail? Any SMTP provider works — you'd just change the
`smtp.gmail.com` line in `scrape_and_alert.py`.)

### 3. Add repo secrets
In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add three:

| Secret name           | Value                                      |
|------------------------|---------------------------------------------|
| `EMAIL_ADDRESS`        | the Gmail address sending the alert         |
| `EMAIL_APP_PASSWORD`   | the 16-character app password from step 2   |
| `ALERT_TO_EMAIL`       | the email address you want alerts sent to   |

### 4. Enable Actions and test it
- Go to the **Actions** tab in your repo, enable workflows if prompted.
- Click into "TV Price Check" → **Run workflow** to trigger it manually
  right away, rather than waiting for the schedule.
- Check the run's logs — it will print every TV/price it found.

## Important caveat: selectors may need a tweak

I wasn't able to inspect the site's actual rendered HTML directly (it's
JavaScript-heavy, so a plain fetch just showed the page shell, not the
product listings). The script tries a few common product-tile patterns,
and falls back to a generic "name line, then price line" text scan if
none of those match.

**After your first test run**, check the Action's log output:
- If it lists sensible TV names and prices → great, you're done.
- If it lists 0 products, or garbled/wrong text → copy a snippet of the
  log output (or the page's HTML via right-click → Inspect on a TV's
  price) and send it over so the selectors can be corrected.

## On the schedule timing

GitHub Actions cron always runs in UTC. Ireland alternates between GMT and
IST (daylight saving), so the workflow file schedules **four** checks a day
covering both possible UTC offsets — but `scrape_and_alert.py` checks the
real Dublin clock first and only does real work if it's actually 9am or
3pm locally. So you'll only ever get alerts around 9am/3pm Irish time,
even though the workflow technically triggers four times.
