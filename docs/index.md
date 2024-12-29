[![Release](https://img.shields.io/github/v/release/jbeirer/pysportbot)](https://img.shields.io/github/v/release/jbeirer/pysportbot)
[![Build status](https://img.shields.io/github/actions/workflow/status/jbeirer/pysportbot/main.yml?branch=main)](https://github.com/jbeirer/pysportbot/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/jbeirer/pysportbot/graph/badge.svg?token=ZCJV384TXF)](https://codecov.io/gh/jbeirer/pysportbot)
[![Commit activity](https://img.shields.io/github/commit-activity/m/jbeirer/pysportbot)](https://img.shields.io/github/commit-activity/m/jbeirer/pysportbot)
[![License](https://img.shields.io/github/license/jbeirer/pysportbot)](https://img.shields.io/github/license/jbeirer/pysportbot)


Welcome to pysportbot!

## Download pysportbot
```python
pip install pysportbot
```

## Quick Start

```python
import pysportbot as bot

# Set credentials
bot.set_email('mail@mail.com')
bot.set_password('mypassword')

# Connect to service
bot.connect()

# List available activites
bot.activities()

# List bookable slots for an activity on a specific day
bot.daily_slots(activity='YourFavouriteGymClass', day = '2025-01-03')

# Book an activity slot on a specific day and time
bot.book(activity='YourFavouriteGymClass', start_time = '2024-12-30 07:00:00')

# Cancel an activity slot ona specific day and time
bot.cancel(activity='YourFavouriteGymClass', start_time = '2024-12-30 07:00:00')
```

## LICENSE

pysportbot is free of use and open-source. All versions are
published under the [MIT License](https://github.com/jbeirer/pysportbot/blob/main/LICENSE).
