# Booking service

The booking service books a list of weekly classes for you. You describe the classes in a config file, and the service logs in, waits until the booking window opens and books them all at once:

```bash
pysportbot run --config config.json
```

`python -m pysportbot.service --config config.json` still works too, and takes the same options.

## Credentials

Your credentials don't need to be in the config file. Set them as env vars instead:

```bash
export SPORTBOT_EMAIL="you@example.com"
export SPORTBOT_PASSWORD="your-password"
export SPORTBOT_CENTRE="your-centre-slug"
```

## Configuration

The config file is JSON or TOML, chosen by its suffix. There are two ways to run it.

### Book now

To book Yoga next Monday at 18:00 right away:

=== "JSON"

    ```json
    {
        "booking_execution": "now",
        "classes": [
            {"activity": "Yoga", "class_day": "Monday", "class_time": "18:00"}
        ]
    }
    ```

=== "TOML"

    ```toml
    booking_execution = "now"

    [[classes]]
    activity = "Yoga"
    class_day = "Monday"
    class_time = "18:00"
    ```

### Book at a set time

Most centres open bookings a few days before the class. To book Yoga on Monday at 18:00 and Spinning on Tuesday at 07:00 as soon as bookings open on Friday at 07:30:

=== "JSON"

    ```json
    {
        "booking_execution": "Friday 07:30",
        "classes": [
            {"activity": "Yoga", "class_day": "Monday", "class_time": "18:00"},
            {"activity": "Spinning", "class_day": "Tuesday", "class_time": "07:00"}
        ]
    }
    ```

=== "TOML"

    ```toml
    booking_execution = "Friday 07:30"

    [[classes]]
    activity = "Yoga"
    class_day = "Monday"
    class_time = "18:00"

    [[classes]]
    activity = "Spinning"
    class_day = "Tuesday"
    class_time = "07:00"
    ```

The service waits until the next Friday 07:30, then books each class on its next occurrence after that.

!!! note "Classes are always in the future"
    A class on the same weekday as the booking is booked for the following week. With `"booking_execution": "Friday 07:30"`, a class on Friday at 18:00 is booked for **next** Friday, not the same day.

### Keys

| Key | Type | Required | Env var |
|-----|------|----------|---------|
| `email` | string | yes, in the file or the env | `SPORTBOT_EMAIL` |
| `password` | string | yes, in the file or the env | `SPORTBOT_PASSWORD` |
| `centre` | string | yes, in the file or the env | `SPORTBOT_CENTRE` |
| `booking_execution` | `"now"` or `"<weekday> <time>"` | no, defaults to `"now"` | |
| `classes` | list of classes, each with `activity`, `class_day` (weekday) and `class_time` (time) | yes, at least one | |
| `notify_url` | ntfy topic URL, see [Notifications](notifications.md) | no, notifications are off without it | `SPORTBOT_NOTIFY_URL` |
| `notify_on` | `"always"` or `"failure"` | no, defaults to `"always"` | `SPORTBOT_NOTIFY_ON` |
| `notify_language` | `"en"`, `"de"`, `"es"`, `"fr"` or `"it"` | no, defaults to `"en"` | `SPORTBOT_NOTIFY_LANGUAGE` |

- **Env vars** override the matching keys in the file. Empty env vars are ignored.
- **Weekdays** are English day names or their 3-letter abbreviations, in any case, e.g. `Monday` or `mon`.
- **Times** use the 24-hour format `HH:MM` or `HH:MM:SS`, e.g. `18:00`. In TOML, unquoted times such as `class_time = 18:00:00` work too.
- **Unknown keys** are errors, so a typo such as `center` doesn't go unnoticed. The service reports all problems in the file at once and exits with code 2.

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--booking-delay SECONDS` | `0` | Wait this long after the execution time before booking. |
| `--poll-interval SECONDS` | `0.5` | Time between attempts while a slot is not bookable yet or not found. Must be positive. |
| `--poll-window SECONDS` | `60` | How long to keep polling after booking starts. |
| `--retry-attempts N` | `3` | Attempts per class for errors that may be temporary, such as network errors. Must be at least 1. |
| `--retry-delay SECONDS` | `5` | Time to wait after such an error. |
| `--max-threads N` | no limit | How many classes to book in parallel. |
| `--notify-on {always,failure}` | `always` | When to send a [notification](notifications.md). Overrides `notify_on` and `SPORTBOT_NOTIFY_ON`. |
| `--dry-run` | | Do everything except send booking requests, see [below](#dry-run). |
| `--time-zone TZ` | `Europe/Madrid` | The time zone of the centre. |
| `--log-level LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. |

Delays can be fractions of a second, e.g. `--retry-delay 0.5`, and must not be negative.

All classes are booked in parallel. With `--max-threads`, the remaining classes are booked as soon as a thread is free, in the order of the config file.

### Dry run

`--dry-run` logs in, waits until the execution time and checks that each slot exists and is neither full nor cancelled, but it doesn't send any booking requests.
With `"booking_execution": "now"` it runs straight away, which makes it a quick way to check a new config file:

```bash
pysportbot run --config config.json --dry-run
```

A successful dry run doesn't guarantee the real booking, though: a slot can still fill up in the meantime.

## How the service books

Popular classes fill up within seconds of the booking window opening, so the service gets ready a minute early and then tries quickly at the opening time:

```text
T-60 s     log in again if the session expired (retrying on failure), and look up each slot
T          book: one request per class, all classes at once
T…T+60 s   try again every 0.5 s while a slot is "not bookable yet"
```

Here `T` is the `booking_execution` time plus `--booking-delay`, and polling stops `--poll-window` seconds after `T`.
Each class looks up its own slot, so one slow lookup doesn't hold up the others. If a slot can't be found at `T-60 s`, e.g. because the calendar isn't published yet, it is looked up again when booking.
With `"booking_execution": "now"`, the service books straight away.

What happens after a failed attempt depends on the error:

| Error | What happens | Result |
|-------|--------------|--------|
| Not bookable yet, not available, or slot not found | Try again every `--poll-interval` seconds until `--poll-window` ends. Polls don't count as retry attempts. | `failed` or `not found` once the window ends |
| Network error, unexpected API response or unknown error code | Try again after `--retry-delay` seconds, up to `--retry-attempts` attempts. | `failed` after the last attempt |
| Already booked | Stop. This includes a booking that timed out but went through: the next attempt finds it already booked. | `already booked` |
| Full | Send one booking request anyway, in case one of the places is already yours, then stop. | `full`, or `already booked` |

At the end, the service logs a summary with the status and number of attempts for each class.
It exits with code `0` if every class is `booked` or `already booked` (or would be booked, in a dry run), and with code `1` otherwise. That way a failed booking is easy to spot, e.g. as a failed scheduled run in [GitHub Actions](github-actions.md).
