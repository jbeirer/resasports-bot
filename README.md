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

# Create bot instance, will list available centres if requested
bot = SportBot(log_level='INFO', print_centres=False, time_zone = 'Europe/Madrid')

# Connect to service with email and password as well as the name of the centre
bot.login('email', 'password', 'centre')

# List available activites
bot.activities(limit = 10)

# List bookable slots for an activity on a specific day
bot.daily_slots(activity='YourFavouriteGymClass', day = '2025-01-03', limit = 10)

# Book an activity slot on a specific day and time
bot.book(activity='YourFavouriteGymClass', start_time = '2024-12-30 07:00:00')

# Cancel an activity slot on a specific day and time
bot.cancel(activity='YourFavouriteGymClass', start_time = '2024-12-30 07:00:00')
```

## Advanced usage as service

You can easily run `pysportbot` as a service to manage your bookings automatically with
```bash
python -m pysportbot.service --config config.json
```
The service requires a `json` configuration file that specifies your user data and how you would like to book your classes. Currently, two types of configuration are supported:

### 1. Book an upcoming class now

Let's say you would like to book Yoga next Monday at 18:00:00, then your `config.json` would look like:

```json
{
    "email": "your-email",
    "password": "your-password",
    "center": "your-gym-name",
    "booking_execution": "now",

    "classes": [
        {
            "activity": "Yoga",
            "class_day": "Monday",
            "class_time": "18:00:00",
        }
    ]
}
```
### 2. Book an upcoming class on a specific day and time

Let's say you would like to book Yoga next Monday at 18:00:00, but the execution of the booking should only happen on Friday at 07:30:00 then your `config.json` would look like:

```json
{
    "email": "your-email",
    "password": "your-password",
    "center": "your-gym-name",
    "booking_execution": "Friday 07:30:00",

    "classes": [
        {
            "activity": "Yoga",
            "class_day": "Monday",
            "class_time": "18:00:00",
        }
    ]
}
```

**Note:** By default, PySportBot will attempt to execute *N* bookings in parallel, where *N* is the number of available cores on your machine.

The service also provides various other options that can be inspected with

```bash
python -m pysportbot.service --help
```
Currently supported options include:

1. `--booking-delay`: sets a global delay in seconds before booking execution [default: 0]
2. `--retry-attempts`: sets the number of retries attempted in case a booking attempt fails [default: 3]
3. `--retry-delay`: sets the delay in seconds between booking retries [default: 5]
4. `--time-zone`: sets the time zone for the service [default: Europe/Madrid]
5. `--log-level`: sets the log-level of the service [default: INFO]
6. `--max-threads`: limits the number of used threads for parallel bookings [default: -1]

## LICENSE

pysportbot is free of use and open-source. All versions are
published under the [MIT License](https://github.com/jbeirer/resasports-bot/blob/main/LICENSE).
