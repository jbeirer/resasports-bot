<img src=https://github.com/jbeirer/resasports-bot/raw/main/docs/logo.svg alt="Logo" width="250">


[![Release](https://img.shields.io/github/v/release/jbeirer/resasports-bot)](https://img.shields.io/github/v/release/jbeirer/resasports-bot)
[![Build status](https://img.shields.io/github/actions/workflow/status/jbeirer/resasports-bot/main.yml?branch=main)](https://github.com/jbeirer/resasports-bot/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/jbeirer/resasports-bot/graph/badge.svg?token=ZCJV384TXF)](https://codecov.io/gh/jbeirer/resasports-bot)
[![Commit activity](https://img.shields.io/github/commit-activity/m/jbeirer/resasports-bot)](https://img.shields.io/github/commit-activity/m/jbeirer/resasports-bot)
[![License](https://img.shields.io/github/license/jbeirer/resasports-bot)](https://img.shields.io/github/license/jbeirer/resasports-bot)


Welcome to pysportbot!

## Download pysportbot
```python
pip install pysportbot
```

## Quick Start

```python
from pysportbot import SportBot

# Create bot instance
bot = SportBot()

# Connect to service with email and password
bot.login('email', 'password')

# List available activites
bot.activities(limit = 10)

# List bookable slots for an activity on a specific day
bot.daily_slots(activity='YourFavouriteGymClass', day = '2025-01-03', limit = 10)

# Book an activity slot on a specific day and time
bot.book(activity='YourFavouriteGymClass', start_time = '2024-12-30 07:00:00')

# Cancel an activity slot ona specific day and time
bot.cancel(activity='YourFavouriteGymClass', start_time = '2024-12-30 07:00:00')
```

## LICENSE

pysportbot is free of use and open-source. All versions are
published under the [MIT License](https://github.com/jbeirer/pysportbot/blob/main/LICENSE).
