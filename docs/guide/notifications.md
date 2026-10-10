# Notifications

The booking service can send a summary of each run to your phone with [ntfy](https://ntfy.sh), a free push notification service that doesn't need an account.

## Setup

1. Install the ntfy app from the [App Store](https://apps.apple.com/app/ntfy/id1625396347), [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy) or [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/).
2. Pick a long, random topic name that nobody can guess, and subscribe to it in the app. For example, generate one with:
   ```bash
   python -c "import secrets; print('pysportbot-' + secrets.token_urlsafe(12))"
   ```
3. Set the topic URL:
   ```bash
   export SPORTBOT_NOTIFY_URL="https://ntfy.sh/<your-topic>"
   ```

After each `pysportbot run`, you then get a notification like this:

```text
pysportbot: 1/2 booked
✅ Yoga · Mon 2026-01-12 18:00 · booked (3 attempts)
❌ Spinning · Tue 2026-01-13 07:00 · full
```

!!! warning "Keep the topic URL secret"
    Anyone who knows the URL can read your notifications and send you fake ones, so treat it like a password.
    Set it with `SPORTBOT_NOTIFY_URL` rather than in a config file you commit. The service never logs it.

## Settings

| Config key | Env var | Option | Values |
|------------|---------|--------|--------|
| `notify_url` | `SPORTBOT_NOTIFY_URL` | | ntfy topic URL. Notifications are off without it. |
| `notify_on` | `SPORTBOT_NOTIFY_ON` | `--notify-on` | `always` (default) or `failure` |
| `notify_language` | `SPORTBOT_NOTIFY_LANGUAGE` | | `en` (default), `de`, `es`, `fr` or `it` |

The option takes precedence over the env var, and the env var over the config key.

### When

By default, you get a notification after every run. With `failure`, you only get one if a class wasn't booked or the run failed.

If a run fails before it gets to booking, e.g. because the login failed, the notification contains the error message.
If the config file itself can't be loaded, the service can only send that error if the notification settings are in the `SPORTBOT_NOTIFY_*` env vars.

### Language

Notifications are in English by default. Set `notify_language` to `de` (German), `es` (Spanish), `fr` (French) or `it` (Italian) to change that. For example, with `de`:

```text
pysportbot: 1/2 gebucht
✅ Yoga · Mo 12.01.2026 18:00 · gebucht (3 Versuche)
```

Error messages stay in English.

### Testing

`pysportbot run --config config.json --dry-run` sends a notification too, with `[dry run]` in front of the title.

## Self-hosted and protected topics

- **Self-hosted ntfy:** use the URL of the topic on your own server. It must use `https://`, except for `localhost`.
- **Protected topics:** put the credentials in the URL. For an access token, use `https://:<access-token>@ntfy.example.com/<topic>` (with an empty username, ntfy treats the password as a token). For a username and password, use `https://<username>:<password>@ntfy.example.com/<topic>`.

## Limits and failures

- A notification holds up to 4,096 bytes. If the summary is longer, e.g. because you book many classes, it lists the classes that weren't booked first and ends with how many it left out.
- If the notification can't be sent, the service logs a warning and carries on. The exit code doesn't change.
- The service also warns if the URL answers, but not like an ntfy server would, e.g. with a login page.
