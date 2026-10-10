# Command line

Installing `pysportbot` also installs the `pysportbot` command, so you can explore your centre and book classes without writing any Python.
With [uv](https://docs.astral.sh/uv/), `uvx pysportbot <command>` runs it without installing anything.

| Command | What it does |
|---------|--------------|
| `pysportbot centres` | List the centres and their slugs. Needs no login. |
| `pysportbot activities` | List the activities of your centre. |
| `pysportbot slots ACTIVITY DAY` | List the slots of an activity on a day. |
| `pysportbot book ACTIVITY START` | Book the slot that starts at `START`. |
| `pysportbot cancel ACTIVITY START` | Cancel the booking of the slot that starts at `START`. |
| `pysportbot run --config FILE` | Run the [booking service](service.md). |

## Logging in

Every command except `centres` logs in. It reads your email and centre from `--email` and `--centre`, or from the `SPORTBOT_EMAIL` and `SPORTBOT_CENTRE` env vars:

```bash
export SPORTBOT_EMAIL="you@example.com"
export SPORTBOT_CENTRE="your-centre-slug"
```

The password comes from `SPORTBOT_PASSWORD`, or from a prompt when you run the command in a terminal.

!!! note "Why is there no `--password` flag?"
    A password passed as a flag ends up in your shell history and in the process list, where other users can see it.

## Examples

```bash
# Find the slug of your centre
pysportbot centres --search madrid

# List the activities of your centre
pysportbot activities

# List the slots of an activity on a day
pysportbot slots Yoga monday

# Book or cancel the slot that starts at a given time
pysportbot book Yoga "2026-01-12 18:00"
pysportbot cancel Yoga "2026-01-12 18:00"

# Print JSON instead of a table, for scripts
pysportbot slots Yoga 2026-01-12 --json
```

- **`DAY`** is a date `YYYY-MM-DD`, `today`, `tomorrow`, or a weekday name such as `monday` for its next occurrence. Today counts as the next occurrence.
- **`START`** is the start time of the slot, `YYYY-MM-DD HH:MM` or `YYYY-MM-DD HH:MM:SS`, in the time zone of the centre.
- **`--json`** prints a JSON array instead of a table. It works with `centres`, `activities` and `slots`.

## Global options

These options go before or after the command:

| Option | Default | Description |
|--------|---------|-------------|
| `--log-level LEVEL` | `WARNING`, or `INFO` for `run` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. The default only shows the result. |
| `--time-zone TZ` | `Europe/Madrid` | The time zone of the centre. |
| `--version` | | Print the version and exit. |

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `1` | The operation failed, e.g. the slot is already booked. For `run`: at least one class was not booked, see [How the service books](service.md#how-the-service-books). |
| `2` | Invalid arguments or configuration, or missing credentials. |
| `130` | Interrupted, e.g. with Ctrl+C. |

Errors are printed without a traceback. Add `--log-level DEBUG` to see it.

## Environment variables

| Variable | Used by | Description |
|----------|---------|-------------|
| `SPORTBOT_EMAIL` | all commands that log in | Account email. `--email` takes precedence. |
| `SPORTBOT_PASSWORD` | all commands that log in | Account password. Without it, you are prompted in a terminal. |
| `SPORTBOT_CENTRE` | all commands that log in | Centre slug. `--centre` takes precedence. |
| `SPORTBOT_NOTIFY_URL` | `run` | ntfy topic URL, see [Notifications](notifications.md). |
| `SPORTBOT_NOTIFY_ON` | `run` | `always` or `failure`. `--notify-on` takes precedence. |
| `SPORTBOT_NOTIFY_LANGUAGE` | `run` | `en`, `de`, `es`, `fr` or `it`. |
| `NO_COLOR` | all commands | Set to any non-empty value to disable colored logs. |
| `FORCE_COLOR` | all commands | Set to any non-empty value to color logs even when stderr is not a terminal, e.g. in CI. |

For `run`, the `SPORTBOT_*` env vars override the corresponding keys in the [config file](service.md#configuration). Empty env vars are ignored.

## Help output

Run `pysportbot --help` or `pysportbot <command> --help` to see all options in your terminal.

??? example "`pysportbot --help`"
    ```text
    usage: pysportbot [-h] [--version] [--log-level LEVEL] [--time-zone TZ] <command> ...

    Book classes at sports centres that use Resasports.

    positional arguments:
      <command>
        centres          List the centres and their slugs; needs no login.
        activities       List the activities of the centre.
        slots            List the slots of an activity.
        book             Book a slot.
        cancel           Cancel a booking.
        run              Run the booking service with a config file.

    options:
      -h, --help         show this help message and exit
      --version          show program's version number and exit
      --log-level LEVEL  Log level: DEBUG, INFO, WARNING, ERROR or CRITICAL [default: INFO for run,
                         otherwise WARNING].
      --time-zone TZ     Time zone of the centre [default: Europe/Madrid].

    Commands that log in read the credentials from --email and --centre, or the SPORTBOT_EMAIL and
    SPORTBOT_CENTRE env vars. The password comes from SPORTBOT_PASSWORD, or a prompt in a terminal.
    ```

??? example "`pysportbot centres --help`"
    ```text
    usage: pysportbot centres [-h] [--log-level LEVEL] [--time-zone TZ] [--json] [--search TEXT]

    options:
      -h, --help         show this help message and exit
      --log-level LEVEL  Log level: DEBUG, INFO, WARNING, ERROR or CRITICAL [default: INFO for run,
                         otherwise WARNING].
      --time-zone TZ     Time zone of the centre [default: Europe/Madrid].
      --json             Print a JSON array instead of a table.
      --search TEXT      Only list centres whose slug, name or town contains TEXT.
    ```

??? example "`pysportbot activities --help`"
    ```text
    usage: pysportbot activities [-h] [--log-level LEVEL] [--time-zone TZ] [--email EMAIL]
                                 [--centre CENTRE] [--json]

    options:
      -h, --help         show this help message and exit
      --log-level LEVEL  Log level: DEBUG, INFO, WARNING, ERROR or CRITICAL [default: INFO for run,
                         otherwise WARNING].
      --time-zone TZ     Time zone of the centre [default: Europe/Madrid].
      --email EMAIL      Account email [default: $SPORTBOT_EMAIL].
      --centre CENTRE    Centre slug, see 'pysportbot centres' [default: $SPORTBOT_CENTRE].
      --json             Print a JSON array instead of a table.
    ```

??? example "`pysportbot slots --help`"
    ```text
    usage: pysportbot slots [-h] [--log-level LEVEL] [--time-zone TZ] [--email EMAIL]
                            [--centre CENTRE] [--json]
                            ACTIVITY DAY

    positional arguments:
      ACTIVITY           Activity name, see 'pysportbot activities'.
      DAY                YYYY-MM-DD, today, tomorrow, or a weekday name such as monday for its next
                         occurrence (today counts).

    options:
      -h, --help         show this help message and exit
      --log-level LEVEL  Log level: DEBUG, INFO, WARNING, ERROR or CRITICAL [default: INFO for run,
                         otherwise WARNING].
      --time-zone TZ     Time zone of the centre [default: Europe/Madrid].
      --email EMAIL      Account email [default: $SPORTBOT_EMAIL].
      --centre CENTRE    Centre slug, see 'pysportbot centres' [default: $SPORTBOT_CENTRE].
      --json             Print a JSON array instead of a table.
    ```

??? example "`pysportbot book --help`"
    ```text
    usage: pysportbot book [-h] [--log-level LEVEL] [--time-zone TZ] [--email EMAIL] [--centre CENTRE]
                           ACTIVITY START

    positional arguments:
      ACTIVITY           Activity name, see 'pysportbot activities'.
      START              Start time of the slot, 'YYYY-MM-DD HH:MM[:SS]'.

    options:
      -h, --help         show this help message and exit
      --log-level LEVEL  Log level: DEBUG, INFO, WARNING, ERROR or CRITICAL [default: INFO for run,
                         otherwise WARNING].
      --time-zone TZ     Time zone of the centre [default: Europe/Madrid].
      --email EMAIL      Account email [default: $SPORTBOT_EMAIL].
      --centre CENTRE    Centre slug, see 'pysportbot centres' [default: $SPORTBOT_CENTRE].
    ```

??? example "`pysportbot cancel --help`"
    ```text
    usage: pysportbot cancel [-h] [--log-level LEVEL] [--time-zone TZ] [--email EMAIL]
                             [--centre CENTRE]
                             ACTIVITY START

    positional arguments:
      ACTIVITY           Activity name, see 'pysportbot activities'.
      START              Start time of the slot, 'YYYY-MM-DD HH:MM[:SS]'.

    options:
      -h, --help         show this help message and exit
      --log-level LEVEL  Log level: DEBUG, INFO, WARNING, ERROR or CRITICAL [default: INFO for run,
                         otherwise WARNING].
      --time-zone TZ     Time zone of the centre [default: Europe/Madrid].
      --email EMAIL      Account email [default: $SPORTBOT_EMAIL].
      --centre CENTRE    Centre slug, see 'pysportbot centres' [default: $SPORTBOT_CENTRE].
    ```

??? example "`pysportbot run --help`"
    ```text
    usage: pysportbot run [-h] [--log-level LEVEL] [--time-zone TZ] --config CONFIG
                          [--booking-delay SECONDS] [--retry-attempts N] [--retry-delay SECONDS]
                          [--poll-interval SECONDS] [--poll-window SECONDS]
                          [--max-threads MAX_THREADS] [--dry-run] [--notify-on {always,failure}]

    Run the booking service with a JSON or TOML config file.

    options:
      -h, --help            show this help message and exit
      --log-level LEVEL     Log level: DEBUG, INFO, WARNING, ERROR or CRITICAL [default: INFO for run,
                            otherwise WARNING].
      --time-zone TZ        Time zone of the centre [default: Europe/Madrid].
      --config CONFIG       Path to the JSON or TOML configuration file.
      --booking-delay SECONDS
                            Global delay in seconds after the execution time before booking [default:
                            0].
      --retry-attempts N    Maximum number of attempts per class that fail with an error that may be
                            temporary, such as a network error [default: 3].
      --retry-delay SECONDS
                            Delay in seconds after such an error [default: 5].
      --poll-interval SECONDS
                            Delay in seconds between attempts while a slot is not bookable yet or not
                            found [default: 0.5].
      --poll-window SECONDS
                            How long to keep polling, in seconds after booking starts [default: 60].
      --max-threads MAX_THREADS
                            Maximum number of classes booked in parallel [default: all classes in
                            parallel].
      --dry-run             Do everything, including waiting and checking that the slots exist and are
                            open, but send no booking request. The real booking can still fail, e.g.
                            if the slot fills up first.
      --notify-on {always,failure}
                            When to send a notification to the ntfy topic URL in SPORTBOT_NOTIFY_URL
                            or notify_url: after every run, or only if a class was not booked or the
                            run failed [default: $SPORTBOT_NOTIFY_ON, notify_on, or always].

    The SPORTBOT_EMAIL, SPORTBOT_PASSWORD, SPORTBOT_CENTRE, SPORTBOT_NOTIFY_URL, SPORTBOT_NOTIFY_ON
    and SPORTBOT_NOTIFY_LANGUAGE env vars override the config file.
    ```
