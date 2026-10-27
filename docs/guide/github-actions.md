# GitHub Actions

You can keep the booking service running on a server, but you don't need one: a scheduled [GitHub Actions](https://docs.github.com/en/actions) workflow can run it once a week for free.

Say you go to Yoga on Monday at 18:00, and bookings open on Friday at 07:30.

1. Commit this `config.json` to a repository. It contains no credentials:
   ```json
   {
       "booking_execution": "Friday 07:30",
       "classes": [
           {"activity": "Yoga", "class_day": "Monday", "class_time": "18:00"}
       ]
   }
   ```
2. In the repository, go to **Settings → Secrets and variables → Actions** and add the secrets `SPORTBOT_EMAIL`, `SPORTBOT_PASSWORD` and `SPORTBOT_CENTRE`.
3. Add the workflow below as `.github/workflows/booking.yml`. It starts every Friday at 07:00 Madrid time, so it's ready well before bookings open at 07:30.

```yaml
name: Weekly Booking

on:
  # Runs at 07:00 Madrid time on Fridays, all year round
  # The timezone key accepts any IANA time zone and handles daylight saving time
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
        uses: astral-sh/setup-uv@v10.3.2

      - name: Run pysportbot
        env:
          SPORTBOT_EMAIL: ${{ secrets.SPORTBOT_EMAIL }}
          SPORTBOT_PASSWORD: ${{ secrets.SPORTBOT_PASSWORD }}
          SPORTBOT_CENTRE: ${{ secrets.SPORTBOT_CENTRE }}
          # Optional, see Notifications
          SPORTBOT_NOTIFY_URL: ${{ secrets.SPORTBOT_NOTIFY_URL }}
          # GitHub Actions shows colored logs, but its output is not a terminal
          FORCE_COLOR: "1"
        run: |
          uvx pysportbot run --config config.json --booking-delay 1 --poll-interval 0.5 --poll-window 60
```

!!! tip "Start early"
    Scheduled runs often start several minutes late, so start the workflow at least 10 minutes before bookings open. The service waits until the execution time anyway.

## Finding out if a booking failed

If a class couldn't be booked, `pysportbot run` exits with code 1 and GitHub marks the run as failed. Depending on your GitHub notification settings, you then get an email, so you know to book the class yourself.

For a push notification on your phone instead, add your ntfy topic URL as the `SPORTBOT_NOTIFY_URL` secret, see [Notifications](notifications.md). If the secret isn't set, notifications are simply off.
