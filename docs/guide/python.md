# Python library

Everything the command line does is available from Python through the [`SportBot`](../reference/sportbot.md) class.

## Log in

```python
from pysportbot import SportBot

# Times without a time zone are taken to be in time_zone, the time zone of the centre
bot = SportBot(log_level="INFO", time_zone="Europe/Madrid")

# Find your centre (no login needed)
for centre in bot.centres(search="madrid"):
    print(centre.slug, centre.name)

# Log in with your email, password and the slug of your centre
bot.login("you@example.com", "your-password", "your-centre-slug")
```

Creating a `SportBot` sends no requests. `login()` checks the centre, logs in and fetches the activities of the centre.

## Browse activities and slots

```python
# List the activities of the centre
for activity in bot.activities():
    print(activity.name)

# List the slots of an activity on a day, given as a date or a "YYYY-MM-DD" string
for slot in bot.daily_slots("Yoga", "2026-01-12"):
    print(slot.start, f"{slot.inscribed}/{slot.capacity}", "full" if slot.is_full else f"{slot.available} left")
```

Centres, activities and slots are frozen dataclasses: [`Centre`](../reference/models.md#pysportbot.models.Centre), [`Activity`](../reference/models.md#pysportbot.models.Activity) and [`Slot`](../reference/models.md#pysportbot.models.Slot).
Slot times are time zone aware `datetime` objects in the bot's time zone.

!!! tip "Prefer pandas?"
    Convert a list of models into a DataFrame with `pd.DataFrame(map(dataclasses.asdict, slots))`.

## Book and cancel

```python
# Book the slot that starts at a given time
slot = bot.book("Yoga", "2026-01-12 18:00")

# Cancel it again
bot.cancel("Yoga", "2026-01-12 18:00")
```

The start time can be:

- a `"YYYY-MM-DD HH:MM"` or `"YYYY-MM-DD HH:MM:SS"` string, in the bot's time zone;
- a naive `datetime`, in the bot's time zone;
- a time zone aware `datetime`, in any time zone.

`book()` returns the booked slot as listed before the booking, so its `inscribed` count does not include your booking yet.
Both methods raise an exception if they fail, see [Error handling](#error-handling).

### Time-critical bookings

Popular classes fill up within seconds of the booking window opening. To book with a single request at that moment, find the slot ahead of time and book it later:

```python
slot = bot.find_slot("Yoga", "2026-01-12 18:00")

# ... wait until the booking window opens ...

bot.ensure_logged_in()  # log in again if the session has expired
bot.book_slot(slot)
```

`book_slot()` does not check whether the slot is full, because its counts may be stale by then: the API decides.
`ensure_logged_in()` costs one request while the session is still valid, and logs in again with the same credentials otherwise.

If you want to book your weekly classes this way, the [booking service](service.md) already does it for you, with polling and retries.

## Error handling

All pysportbot errors derive from [`SportBotError`](../reference/exceptions.md), so you can react to specific failures by type:

```python
import requests

from pysportbot import SlotAlreadyBookedError, SlotNotBookableYetError, SportBotError

try:
    bot.book("Yoga", "2026-01-12 18:00")
except SlotNotBookableYetError:
    ...  # the booking window has not opened yet, try again later
except SlotAlreadyBookedError:
    ...  # nothing to do
except SportBotError as e:
    ...  # any other pysportbot error
except requests.RequestException as e:
    ...  # network error, e.g. a timeout
```

All exception classes can be imported from `pysportbot`. See the [exceptions reference](../reference/exceptions.md) for the full hierarchy.

!!! warning "Network errors and retries"
    Network failures such as timeouts are not wrapped: they propagate as `requests.RequestException`.
    A request that fails to connect is retried up to twice, but a request that may have reached the server, such as a booking that timed out, is never sent again automatically.
    If you retry a timed-out booking yourself and the first request did succeed, the retry raises `SlotAlreadyBookedError`.

## Logging

`SportBot(log_level=...)` prints color-coded logs to stderr, with timestamps in the bot's time zone.
Change the level later with `bot.set_log_level("DEBUG")`.

pysportbot only configures its own `pysportbot` logger and never touches the root logger, so it does not change how your application logs.
Its messages are printed once by its own handler, even if your application also configures logging, e.g. with `logging.basicConfig()`.
Without a `SportBot` instance, pysportbot stays silent unless you configure logging yourself.

If your application manages logging itself, e.g. to send logs to a central handler, pass `SportBot(log_level=None)`.
pysportbot then installs no handler, and its records propagate to your root logger's handlers at the levels you configure, e.g. via `logging.getLogger("pysportbot")`.

Colors are used only when stderr is a terminal. Set `NO_COLOR=1` to always disable them, or `FORCE_COLOR=1` to enable them when the output is not a terminal, e.g. in CI logs.
