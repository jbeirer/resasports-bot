# No queues. Just gains.

<img src=https://github.com/jbeirer/resasports-bot/raw/main/docs/logo.png alt="Logo" width="250">


[![Release](https://img.shields.io/github/v/release/jbeirer/resasports-bot)](https://github.com/jbeirer/resasports-bot/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/jbeirer/resasports-bot/main.yml?branch=main)](https://github.com/jbeirer/resasports-bot/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/jbeirer/resasports-bot/graph/badge.svg?token=ZCJV384TXF)](https://codecov.io/gh/jbeirer/resasports-bot)
[![Commit activity](https://img.shields.io/github/commit-activity/m/jbeirer/resasports-bot)](https://github.com/jbeirer/resasports-bot/commits/main/)
[![License](https://img.shields.io/github/license/jbeirer/resasports-bot)](https://github.com/jbeirer/resasports-bot/blob/main/LICENSE)
[![Documentation](https://img.shields.io/badge/api-docs-blue)](https://jbeirer.github.io/resasports-bot/)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](https://github.com/jbeirer/resasports-bot/blob/main/CODE_OF_CONDUCT.md)

PySportBot empowers you to programmatically book fitness classes at any sports center that uses the [Resasports](https://social.resasports.com/en/) booking management software.

## Install
```bash
pip install pysportbot
```

## Command line

Installing `pysportbot` also installs the `pysportbot` command, so you can explore your centre and book classes without writing Python:

```bash
# Find the slug of your centre (no login needed)
pysportbot centres --search madrid

# Commands that log in read your email and centre from these env vars, or from --email and --centre
export SPORTBOT_EMAIL="your-email"
export SPORTBOT_CENTRE="your-centre-slug"

# List the activities of your centre; you are prompted for your password unless SPORTBOT_PASSWORD is set
pysportbot activities

# List the slots of an activity on a day: YYYY-MM-DD, today, tomorrow or a weekday (its next occurrence, today counts)
pysportbot slots Yoga monday

# Book or cancel the slot that starts at a given time
pysportbot book Yoga "2026-01-12 18:00"
pysportbot cancel Yoga "2026-01-12 18:00"

# Print JSON instead of a table, for scripts
pysportbot slots Yoga 2026-01-12 --json
```

With [uv](https://docs.astral.sh/uv/), `uvx pysportbot centres` runs the command without installing anything.

- **Password:** there is no `--password` flag, because it would end up in your shell history and in the process list. The password comes from `SPORTBOT_PASSWORD`, or from a prompt when you run the command in a terminal.
- **Global options:** `--log-level` [default: `WARNING`, so you only see the result; `INFO` for `run`] and `--time-zone` of the centre [default: `Europe/Madrid`] go before or after the command.
- **Exit codes:** `0` on success, `1` if the operation fails (e.g. the slot is already booked), `2` for invalid arguments, configuration or missing credentials, and `130` if interrupted. Errors are printed without a traceback; `--log-level DEBUG` adds it. For `run`, `1` means that at least one class was not booked, see [How the service books](#how-the-service-books).

Run `pysportbot --help` or `pysportbot <command> --help` for all options.

## Quick Start

```python
from pysportbot import SportBot

# Create bot instance; times without a time zone are taken to be in time_zone
bot = SportBot(log_level="INFO", time_zone="Europe/Madrid")

# Find your centre (no login needed)
for c in bot.centres(search="madrid"):
    print(c.slug, c.name)

# Connect to service with email and password as well as the slug of the centre
bot.login("email", "password", "centre-slug")

# List available activities
for a in bot.activities()[:10]:
    print(a.name)

# List the slots of an activity on a specific day
for s in bot.daily_slots("Yoga", "2026-01-05"):
    print(s.start, f"{s.inscribed}/{s.capacity}")

# In long-running scripts, log in again with the same credentials if the session has expired
bot.ensure_logged_in()

# Book an activity slot on a specific day and time, given as a string or a datetime
# Returns the booked slot as listed before the booking, so `inscribed` does not count your booking yet
# Raises an exception if the booking fails (e.g. not bookable yet, already booked, full)
bot.book("Yoga", "2026-01-05 07:00")

# For time-critical bookings, find the slot ahead of time and book it later with a single request
# book_slot() leaves checking whether the slot is full to the API, because the slot's counts may be stale by then
slot = bot.find_slot("Yoga", "2026-01-05 07:00")
bot.book_slot(slot)

# Cancel an activity slot on a specific day and time
# Raises an exception if the cancellation fails
bot.cancel("Yoga", "2026-01-05 07:00")
```

Centres, activities and slots are frozen dataclasses (`Centre`, `Activity`, `Slot`).
If you prefer pandas, convert them with `pd.DataFrame(map(dataclasses.asdict, slots))`.

## Error handling

All `pysportbot` errors derive from `SportBotError`, so you can react to specific failures by type.
Network failures such as timeouts are not wrapped: they propagate as `requests.RequestException`.
At the HTTP level, a request that fails to connect is retried up to twice, but a request that may have reached the server, such as a booking that timed out, is never re-sent automatically.
If you retry a timed-out booking yourself and the first request did succeed, the retry raises `SlotAlreadyBookedError`.

```python
import requests

from pysportbot import SlotAlreadyBookedError, SlotNotBookableYetError, SportBotError

try:
    bot.book("Yoga", "2026-01-05 07:00")
except SlotNotBookableYetError:
    ...  # the booking window has not opened yet, try again later
except SlotAlreadyBookedError:
    ...  # nothing to do
except SportBotError as e:
    ...  # any other pysportbot error
except requests.RequestException as e:
    ...  # network error, e.g. a timeout
```

All exception classes can be imported from `pysportbot`; see `pysportbot/exceptions.py` for the full hierarchy.

## Logging

`SportBot(log_level=..., time_zone=...)` prints color-coded logs to stderr, with timestamps in the given time zone.
It only configures the `pysportbot` logger and never touches the root logger, so it does not change how your own application logs.
`pysportbot` messages are printed once by its own handler, even if your application also configures logging, e.g. with `logging.basicConfig()`.
Without a `SportBot` instance, `pysportbot` stays silent unless you configure logging yourself.

If your application manages logging itself, e.g. to send logs to a central handler, pass `SportBot(log_level=None)`.
`pysportbot` then installs no handler and its records propagate to your root logger handlers, at the levels you configure, e.g. via `logging.getLogger("pysportbot")`.

Colors are used only when stderr is a terminal. Set `NO_COLOR=1` to always disable them, or `FORCE_COLOR=1` to enable them when the output is not a terminal, e.g. in CI logs.

## Advanced usage as service

You can easily run `pysportbot` as a service to manage your bookings automatically with
```bash
pysportbot run --config config.json
```
The older `python -m pysportbot.service --config config.json` still works and takes the same options.

The service reads a JSON or TOML configuration file that specifies how you would like to book your classes. Your credentials don't need to be in the file: set them as environment variables instead.

```bash
export SPORTBOT_EMAIL="your-email"
export SPORTBOT_PASSWORD="your-password"
export SPORTBOT_CENTRE="your-gym-name"
```

The configuration supports these keys:

| Key | Type | Required | Env var |
|-----|------|----------|---------|
| `email` | string | yes, in the file or the env | `SPORTBOT_EMAIL` |
| `password` | string | yes, in the file or the env | `SPORTBOT_PASSWORD` |
| `centre` | string | yes, in the file or the env | `SPORTBOT_CENTRE` |
| `booking_execution` | `"now"` or `"<weekday> <time>"` | no, defaults to `"now"` | |
| `classes` | non-empty list of classes, each with `activity`, `class_day` (weekday) and `class_time` (time) | yes | |
| `notify_url` | ntfy topic URL, see [Notifications](#notifications) | no, notifications are off without it | `SPORTBOT_NOTIFY_URL` |
| `notify_on` | `"always"` or `"failure"` | no, defaults to `"always"` | `SPORTBOT_NOTIFY_ON` |

- **Env vars** override the corresponding keys in the file. Empty env vars are ignored.
- **Weekdays** are English day names or their 3-letter abbreviations, case-insensitive, e.g. `Monday` or `mon`.
- **Times** use the 24-hour format `HH:MM` or `HH:MM:SS`, e.g. `18:00`. In TOML, unquoted times such as `class_time = 18:00:00` work too.
- **Unknown keys** are errors, e.g. a misspelled `center`. The service reports all problems in the file at once.

Currently, two types of configuration are supported:

### 1. Book an upcoming class now

Let's say you would like to book Yoga next Monday at 18:00, then your `config.json` would look like:

```json
{
    "booking_execution": "now",

    "classes": [
        {
            "activity": "Yoga",
            "class_day": "Monday",
            "class_time": "18:00"
        }
    ]
}
```
### 2. Book an upcoming class on a specific day and time

Let's say you would like to book Yoga next Monday at 18:00, but the execution of the booking should only happen on Friday at 07:30, then your `config.json` would look like:

```json
{
    "booking_execution": "Friday 07:30",

    "classes": [
        {
            "activity": "Yoga",
            "class_day": "Monday",
            "class_time": "18:00"
        }
    ]
}
```

The same configuration as `config.toml`, with the centre in the file:

```toml
centre = "my-gym"
booking_execution = "Friday 07:30"

[[classes]]
activity = "Yoga"
class_day = "Monday"
class_time = "18:00"
```

**Note:**
1. Bookings are always scheduled for the following week. For example, if your booking execution is set for Friday at 07:30 and your class is on Friday at 18:00, the system will schedule the booking for **next Friday** at 18:00, not the same day.
2. All classes are booked in parallel; `--max-threads` caps concurrency. With a cap, the remaining classes are booked as soon as a thread is free, in the order of your configuration file.


The service also provides various other options that can be inspected with

```bash
pysportbot run --help
```
Currently supported options include:

1. `--booking-delay`: sets a global delay in seconds after the execution time before booking, must not be negative [default: 0]
2. `--poll-interval`: sets the delay in seconds between attempts while a slot is not bookable yet or not found, must be positive [default: 0.5]
3. `--poll-window`: sets how long to keep polling, in seconds after booking starts, must not be negative [default: 60]
4. `--retry-attempts`: sets the maximum number of attempts per class that fail with an error that may be temporary, such as a network error, must be at least 1 [default: 3]
5. `--retry-delay`: sets the delay in seconds after such an error, must not be negative [default: 5]
6. `--time-zone`: sets the time zone for the service [default: Europe/Madrid]
7. `--log-level`: sets the log-level of the service [default: INFO]
8. `--max-threads`: caps the number of classes booked in parallel, must be a positive integer [default: no cap]
9. `--notify-on`: `always` or `failure`, overrides `notify_on` and `SPORTBOT_NOTIFY_ON`, see [Notifications](#notifications)
10. `--dry-run`: does everything, including logging in, waiting until the execution time and checking that the slots exist and are neither full nor cancelled, but sends no booking requests. The real booking can still fail, e.g. if a slot fills up in the meantime. With `"booking_execution": "now"` it runs immediately, as a quick check of your configuration.

All delays accept fractions of a second, e.g. `--retry-delay 0.5`.

If the configuration or an option is invalid, the service prints the problems without a traceback and exits with code 2.

### How the service books

Popular classes fill up within seconds of the booking window opening, so the service prepares ahead and keeps trying fast at the opening moment:

```text
T-60 s     log in again if the session expired (retrying on failure), and look up each slot
T          book: one request per class, all classes at once
T…T+60 s   try again every 0.5 s while a slot is "not bookable yet"
```

Here `T` is the `booking_execution` time plus `--booking-delay`, and the polling stops `--poll-window` seconds after `T`.
Each class looks up its own slot, so a slow lookup does not delay the other classes. If a slot cannot be found at `T-60 s`, e.g. because the calendar is not published yet, it is looked up again when booking.
With `"booking_execution": "now"` the service books at once.

What the service does after a failed attempt depends on the error:

| Error | What happens | Result |
|-------|--------------|--------|
| Not bookable yet, not available, or slot not found | Try again every `--poll-interval` seconds for `--poll-window` seconds after booking starts. Polls do not count as retry attempts | `failed` or `not found` once the window ends |
| Network error, unexpected API response or unknown error code | Try again after `--retry-delay` seconds, up to `--retry-attempts` attempts | `failed` after the last attempt |
| Already booked | Stop. This includes a booking that timed out but went through: the next attempt finds it already booked | `already booked` |
| Full | Send one booking request, in case one of the places is already yours, then stop | `full`, or `already booked` |

At the end, the service logs a summary with the status and the number of attempts of each class.
It exits with code `0` if every class is `booked` or `already booked` (or would be booked in a `--dry-run`), and with code `1` otherwise, so that a failed booking is easy to spot, e.g. in a scheduled GitHub Actions run.

### Notifications

The service can push a summary of each run to your phone with [ntfy](https://ntfy.sh), a free push notification service that needs no account:

1. Install the ntfy app from the [App Store](https://apps.apple.com/app/ntfy/id1625396347), [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy) or [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/).
2. Pick a long, random topic name that nobody can guess, e.g. from `python -c "import secrets; print('pysportbot-' + secrets.token_urlsafe(12))"`, and subscribe to it in the app.
3. Set the topic URL:
   ```bash
   export SPORTBOT_NOTIFY_URL="https://ntfy.sh/<your-topic>"
   ```

After each `pysportbot run` you then get a notification such as:

```text
pysportbot: 1/2 booked
✅ Yoga · Mon 2026-01-12 18:00 · booked (3 attempts)
❌ Spinning · Tue 2026-01-13 07:00 · full
```

- **When:** after every run by default. With `notify_on` set to `"failure"`, or `--notify-on failure`, only if a class was not booked or the run failed. A run that fails before booking, e.g. because the login failed, sends the error message.
- **Testing:** `pysportbot run --config config.json --dry-run` sends the notification too, with the title prefixed by `[dry run]`.
- **Self-hosted ntfy:** set the URL of the topic on your server instead. It must use `https://`, except for `localhost`.
- **Failures:** if the notification cannot be sent, the service logs a warning and carries on. The exit code stays the same.

**Keep the topic URL secret.** Anyone who knows it can read your notifications and send you fake ones, so treat it like a password: set it via `SPORTBOT_NOTIFY_URL` rather than in a committed config file. The service never logs it.

## Automating Weekly Bookings with GitHub Actions

While you can use PySportBot as a continuously running service, doing so often becomes cumbersome because it requires a server (or similar machine) that is always online.

Using **[GitHub Actions](https://docs.github.com/en/actions)** is one of the most reliable ways to schedule **automated weekly bookings**. With a simple workflow file, you can ensure your bookings run at a specific time each week — no manual intervention required.

For example, if you have a **Yoga** class on **Monday at 18:00**, and you want the **booking** to be executed on **Friday at 07:30**, commit the `config.json` from [example 2](#2-book-an-upcoming-class-on-a-specific-day-and-time) to your repository. It contains no credentials. Then add `SPORTBOT_EMAIL`, `SPORTBOT_PASSWORD` and `SPORTBOT_CENTRE` under **Settings → Secrets and variables → Actions** in your repository.

Below is a sample **[GitHub Actions workflow](https://docs.github.com/en/actions/writing-workflows)** that triggers every **Friday at 07:00 Madrid time**, ensuring there is enough time before the actual booking execution at 07:30:

```yml
name: Weekly Booking

on:
  # Runs at 07:00 Madrid time on Fridays, all year round
  # The timezone key accepts any IANA time zone and handles daylight saving time automatically
  schedule:
    - cron: '0 7 * * 5'
      timezone: 'Europe/Madrid'

jobs:
  book:
    runs-on: ubuntu-latest

    steps:
      - name: Check out repository
        uses: actions/checkout@v7

      - name: Set up uv
        uses: astral-sh/setup-uv@v7

      - name: Run pysportbot
        env:
          SPORTBOT_EMAIL: ${{ secrets.SPORTBOT_EMAIL }}
          SPORTBOT_PASSWORD: ${{ secrets.SPORTBOT_PASSWORD }}
          SPORTBOT_CENTRE: ${{ secrets.SPORTBOT_CENTRE }}
          # Optional, see Notifications
          SPORTBOT_NOTIFY_URL: ${{ secrets.SPORTBOT_NOTIFY_URL }}
          # GitHub Actions renders colored logs, but its output is not a terminal
          FORCE_COLOR: "1"
        run: |
          uvx pysportbot run --config config.json --booking-delay 1 --poll-interval 0.5 --poll-window 60
```
**Notes:**
1. Start the workflow at least 10 minutes before your booking execution time (e.g., 07:30 Madrid time). Scheduled GitHub Actions runs often start several minutes late, and the service waits until the execution time anyway.
2. If a class could not be booked, `pysportbot run` exits with code 1 and GitHub marks the run as failed. GitHub can notify you of failed runs, e.g. by email, depending on your notification settings, so you know to book the class yourself.
3. To get a push notification on your phone instead, add your ntfy topic URL as the `SPORTBOT_NOTIFY_URL` secret, see [Notifications](#notifications). Without the secret, notifications are simply off.


## LICENSE

pysportbot is free of use and open-source. All versions are
published under the [MIT License](https://github.com/jbeirer/resasports-bot/blob/main/LICENSE).
