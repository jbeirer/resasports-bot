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
python -m pysportbot.service --config config.json
```
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

- **Env vars** override the corresponding keys in the file. Empty env vars are ignored.
- **Weekdays** are English day names or their 3-letter abbreviations, case-insensitive, e.g. `Monday` or `mon`.
- **Times** use the 24-hour format `HH:MM` or `HH:MM:SS`, e.g. `18:00`.
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
python -m pysportbot.service --help
```
Currently supported options include:

1. `--booking-delay`: sets a global delay in seconds before booking execution, must not be negative [default: 0]
2. `--retry-attempts`: sets the number of booking attempts per class, must be at least 1 [default: 3]
3. `--retry-delay`: sets the delay in seconds between booking retries, must not be negative [default: 5]
4. `--time-zone`: sets the time zone for the service [default: Europe/Madrid]
5. `--log-level`: sets the log-level of the service [default: INFO]
6. `--max-threads`: caps the number of classes booked in parallel, must be a positive integer [default: no cap]

If the configuration is invalid, the service prints the problems and exits with code 2.

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
          # GitHub Actions renders colored logs, but its output is not a terminal
          FORCE_COLOR: "1"
        run: |
          uvx --from pysportbot python -m pysportbot.service --config config.json --log-level INFO --booking-delay 1 --retry-attempts 3 --retry-delay 5
```
**Note:** Make sure the workflow starts early enough — before your booking execution time (e.g., 07:30 Madrid time) — to allow for potential delays in job startup or execution.


## LICENSE

pysportbot is free of use and open-source. All versions are
published under the [MIT License](https://github.com/jbeirer/resasports-bot/blob/main/LICENSE).
