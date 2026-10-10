# No queues. Just gains.

<img src=https://github.com/jbeirer/resasports-bot/raw/main/docs/logo.png alt="Logo" width="250">


[![Release](https://img.shields.io/github/v/release/jbeirer/resasports-bot)](https://github.com/jbeirer/resasports-bot/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/jbeirer/resasports-bot/main.yml?branch=main)](https://github.com/jbeirer/resasports-bot/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/jbeirer/resasports-bot/graph/badge.svg?token=ZCJV384TXF)](https://codecov.io/gh/jbeirer/resasports-bot)
[![Activity](https://img.shields.io/github/commit-activity/m/jbeirer/resasports-bot?label=activity)](https://github.com/jbeirer/resasports-bot/commits/main/)
[![License](https://img.shields.io/github/license/jbeirer/resasports-bot)](https://github.com/jbeirer/resasports-bot/blob/main/LICENSE)
[![Documentation](https://img.shields.io/badge/api-docs-blue)](https://jbeirer.github.io/resasports-bot/)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg?label=Contributing)](https://github.com/jbeirer/resasports-bot/blob/main/CODE_OF_CONDUCT.md)
[![Downloads](https://static.pepy.tech/badge/pysportbot)](https://pepy.tech/projects/pysportbot)

pysportbot books fitness classes at sports centres that use the [Resasports](https://social.resasports.com/en/) booking software.
You can use it from the command line or from Python, or let it book your weekly classes as soon as bookings open, e.g. from a scheduled GitHub Actions workflow. It can also send you the result on your phone.

## Installation

```bash
pip install pysportbot
```

pysportbot needs Python 3.11 or newer. With [uv](https://docs.astral.sh/uv/), `uvx pysportbot` runs the command without installing anything.

## Quick start

### Command line

```bash
# Find the slug of your centre (no login needed)
pysportbot centres --search madrid

# Tell pysportbot who you are; you are prompted for your password unless SPORTBOT_PASSWORD is set
export SPORTBOT_EMAIL="you@example.com"
export SPORTBOT_CENTRE="your-centre-slug"

# See what's on, then book
pysportbot activities
pysportbot slots Yoga monday
pysportbot book Yoga "2026-01-12 18:00"
```

### Python

```python
from pysportbot import SportBot

bot = SportBot()
bot.login("you@example.com", "your-password", "your-centre-slug")

for slot in bot.daily_slots("Yoga", "2026-01-12"):
    print(slot.start, f"{slot.inscribed}/{slot.capacity}")

bot.book("Yoga", "2026-01-12 18:00")
```

### Book every week, automatically

Describe your classes in a `config.json`:

```json
{
    "booking_execution": "Friday 07:30",
    "classes": [
        {"activity": "Yoga", "class_day": "Monday", "class_time": "18:00"}
    ]
}
```

Then start the booking service, e.g. every Friday from [GitHub Actions](https://jbeirer.github.io/resasports-bot/guide/github-actions/):

```bash
pysportbot run --config config.json
```

It waits until Friday 07:30 and then books Yoga on the following Monday at 18:00. If the booking window has not opened yet, it keeps trying for up to a minute. It exits with code 1 if a class could not be booked.

## Documentation

The full documentation is at [jbeirer.github.io/resasports-bot](https://jbeirer.github.io/resasports-bot/):

- [Command line](https://jbeirer.github.io/resasports-bot/guide/cli/): all commands, exit codes and env vars
- [Python library](https://jbeirer.github.io/resasports-bot/guide/python/): booking from your own code, error handling and logging
- [Booking service](https://jbeirer.github.io/resasports-bot/guide/service/): the config file and how bookings are retried
- [Notifications](https://jbeirer.github.io/resasports-bot/guide/notifications/): booking results on your phone with ntfy
- [GitHub Actions](https://jbeirer.github.io/resasports-bot/guide/github-actions/): weekly bookings without a server
- [API reference](https://jbeirer.github.io/resasports-bot/reference/sportbot/)

## Contributing

Contributions are welcome. See [CONTRIBUTING.rst](https://github.com/jbeirer/resasports-bot/blob/main/CONTRIBUTING.rst) to set up a development environment.

## License

pysportbot is open source and published under the [MIT License](https://github.com/jbeirer/resasports-bot/blob/main/LICENSE).
