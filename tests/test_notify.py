import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
import requests
import responses

from pysportbot.cli import main
from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import AuthenticationError, ConfigError
from pysportbot.service import notify
from pysportbot.service.config import ClassSpec, NotifySettings, ServiceConfig
from pysportbot.service.results import BookingResult, BookingStatus

# A secret topic: tests check that it never shows up in the logs or error messages
URL = "https://ntfy.example/s3cret-topic"
TZ = ZoneInfo("Europe/Madrid")

YOGA = BookingResult(
    ClassSpec("Yoga", 0, time(18)), datetime(2026, 1, 12, 18, tzinfo=TZ), BookingStatus.BOOKED, attempts=3
)
SPINNING = BookingResult(
    ClassSpec("Spinning", 1, time(7)),
    datetime(2026, 1, 13, 7, tzinfo=TZ),
    BookingStatus.FULL,
    attempts=1,
    error="Slot 5002 is full and cannot be booked.",
)
PILATES = BookingResult(
    ClassSpec("Pilates", 2, time(9, 30)),
    datetime(2026, 1, 14, 9, 30, tzinfo=TZ),
    BookingStatus.FAILED,
    attempts=3,
    error="Booking slot 5003 failed (error code 99).",
)
YOGA_DRY_RUN = BookingResult(
    ClassSpec("Yoga", 0, time(18)), datetime(2026, 1, 12, 18, tzinfo=TZ), BookingStatus.DRY_RUN, attempts=1
)
ALWAYS = NotifySettings(url=URL, on="always")
ON_FAILURE = NotifySettings(url=URL, on="failure")
CLASSES = [{"activity": "Yoga", "class_day": "Monday", "class_time": "18:00"}]
CREDENTIALS = {"email": "user@example.com", "password": "password", "centre": "test-centre"}


@pytest.fixture
def ntfy():
    """Mock the ntfy topic URL, and fail on any other request."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, URL, json={"id": "abc"})
        yield rsps


def _notifications(rsps):
    return [c.request for c in rsps.calls if c.request.url == URL]


def _body(request) -> str:
    return request.body.decode("utf-8")


# Message


def test_format_summary_all_ok():
    title, body = notify.format_summary([YOGA])

    assert title == "pysportbot: 1/1 booked"
    assert body == "✅ Yoga · Mon 2026-01-12 18:00 · booked (3 attempts)"


def test_format_summary_mixed():
    title, body = notify.format_summary([YOGA, SPINNING, PILATES])

    assert title == "pysportbot: 1/3 booked"
    assert body.splitlines() == [
        "✅ Yoga · Mon 2026-01-12 18:00 · booked (3 attempts)",
        "❌ Spinning · Tue 2026-01-13 07:00 · full",
        "❌ Pilates · Wed 2026-01-14 09:30 · failed (3 attempts): Booking slot 5003 failed (error code 99).",
    ]


def test_format_summary_dry_run():
    title, body = notify.format_summary([YOGA_DRY_RUN], dry_run=True)

    assert title == "[dry run] pysportbot: 1/1 bookable"
    assert body == "✅ Yoga · Mon 2026-01-12 18:00 · dry run"


# Sending


def test_send_all_ok(ntfy):
    notify.send(ALWAYS, [YOGA])

    [request] = _notifications(ntfy)
    assert request.headers["Title"] == "pysportbot: 1/1 booked"
    assert request.headers["Tags"] == "white_check_mark"
    assert request.headers["Priority"] == "default"
    assert request.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert _body(request) == "✅ Yoga · Mon 2026-01-12 18:00 · booked (3 attempts)"
    assert request.req_kwargs["timeout"] == 10


def test_send_mixed(ntfy):
    notify.send(ALWAYS, [YOGA, SPINNING])

    [request] = _notifications(ntfy)
    assert request.headers["Title"] == "pysportbot: 1/2 booked"
    assert request.headers["Tags"] == "warning"
    assert request.headers["Priority"] == "high"
    assert "❌ Spinning · Tue 2026-01-13 07:00 · full" in _body(request)


def test_send_dry_run_title(ntfy):
    notify.send(ALWAYS, [YOGA_DRY_RUN], dry_run=True)

    [request] = _notifications(ntfy)
    assert request.headers["Title"] == "[dry run] pysportbot: 1/1 bookable"


def test_notify_on_failure_skips_all_ok_run(ntfy):
    notify.send(ON_FAILURE, [YOGA])

    assert len(ntfy.calls) == 0


def test_notify_on_failure_sends_if_a_class_failed(ntfy):
    notify.send(ON_FAILURE, [YOGA, PILATES])

    [request] = _notifications(ntfy)
    assert request.headers["Priority"] == "high"


@pytest.mark.parametrize("settings", [ALWAYS, ON_FAILURE])
def test_send_error(settings, ntfy):
    notify.send(settings, error=AuthenticationError("Invalid credentials"))

    [request] = _notifications(ntfy)
    assert request.headers["Title"] == "pysportbot: run failed"
    assert request.headers["Tags"] == "warning"
    assert request.headers["Priority"] == "high"
    assert _body(request) == "Login failed: Invalid credentials. Please check your credentials and try again."


@pytest.mark.parametrize(
    ("response", "logged"),
    [
        pytest.param({"status": 500}, "HTTP 500", id="http-500"),
        pytest.param({"body": requests.ConnectionError(f"Cannot connect to {URL}")}, "ConnectionError", id="network"),
        pytest.param({"body": requests.Timeout(f"{URL} timed out")}, "Timeout", id="timeout"),
    ],
)
def test_send_failure_logs_warning_without_url(response, logged, pysportbot_caplog):
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, URL, **response)
        notify.send(ALWAYS, [YOGA])

    [record] = [r for r in pysportbot_caplog.records if r.name == "pysportbot.service.notify"]
    assert record.levelname == "WARNING"
    assert record.getMessage() == f"Could not send the notification: {logged}."
    assert "s3cret" not in pysportbot_caplog.text


# Config


def parse(data, env=None):
    return ServiceConfig.from_mapping({**CREDENTIALS, "classes": CLASSES, **data}, env={} if env is None else env)


def config_error(data, env=None) -> str:
    with pytest.raises(ConfigError) as exc_info:
        parse(data, env)
    return str(exc_info.value)


def test_notifications_off_by_default():
    assert parse({}).notify is None


def test_notify_settings_from_file():
    assert parse({"notify_url": URL}).notify == ALWAYS
    assert parse({"notify_url": f" {URL} ", "notify_on": "failure"}).notify == ON_FAILURE


def test_env_overrides_file_notify_settings():
    env = {"SPORTBOT_NOTIFY_URL": URL, "SPORTBOT_NOTIFY_ON": "failure"}

    config = parse({"notify_url": "https://ntfy.example/other", "notify_on": "always"}, env)

    assert config.notify == ON_FAILURE


def test_notify_settings_from_env_only():
    assert parse({}, {"SPORTBOT_NOTIFY_URL": URL}).notify == ALWAYS


def test_empty_notify_env_vars_fall_back_to_file():
    env = {"SPORTBOT_NOTIFY_URL": "", "SPORTBOT_NOTIFY_ON": ""}

    assert parse({"notify_url": URL, "notify_on": "failure"}, env).notify == ON_FAILURE


@pytest.mark.parametrize("url", ["http://localhost:8080/topic", "http://127.0.0.1/topic", "http://[::1]/topic"])
def test_http_allowed_for_localhost(url):
    config = parse({"notify_url": url})

    assert config.notify is not None
    assert config.notify.url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://ntfy.example/s3cret-topic",
        "ntfy.example/s3cret-topic",
        "ftp://ntfy.example/s3cret-topic",
        "https:///s3cret-topic",
        "https://[s3cret-topic",
        "",
        42,
    ],
)
def test_invalid_notify_url(url):
    message = config_error({"notify_url": url})

    assert "notify_url: must be an https:// URL" in message
    assert "s3cret" not in message


def test_invalid_notify_url_from_env():
    message = config_error({}, {"SPORTBOT_NOTIFY_URL": "http://ntfy.example/s3cret-topic"})

    assert "notify_url: must be an https:// URL" in message
    assert "s3cret" not in message


@pytest.mark.parametrize(("data", "env"), [({"notify_on": "never"}, {}), ({}, {"SPORTBOT_NOTIFY_ON": "never"})])
def test_invalid_notify_on(data, env):
    message = config_error({"notify_url": URL, **data}, env)

    assert "notify_on: invalid value 'never'. Use one of: always, failure." in message


def test_notify_url_not_in_repr():
    assert "s3cret" not in repr(parse({"notify_url": URL}))


# CLI


@pytest.fixture
def notify_url(monkeypatch, mocked_api):
    """Send notifications to the mocked topic URL."""
    monkeypatch.setenv("SPORTBOT_NOTIFY_URL", URL)
    mocked_api.add(responses.POST, URL, json={"id": "abc"})


def _run(config_path, *options):
    return main(["run", "--config", str(config_path), *options])


@pytest.mark.usefixtures("cli_env", "mock_time", "frozen_now", "credentials_env")
class TestRun:
    def test_no_notify_url_sends_nothing_extra(self, mocked_api, config_path):
        assert _run(config_path) == 0

        api_hosts = (Endpoints.BASE_SOCIAL, Endpoints.BASE_NUBAPP)
        assert mocked_api.calls
        assert all(c.request.url.startswith(api_hosts) for c in mocked_api.calls)

    def test_sends_summary(self, mocked_api, notify_url, config_path, capsys):
        assert _run(config_path) == 0

        [request] = _notifications(mocked_api)
        assert request.headers["Title"] == "pysportbot: 1/1 booked"
        assert _body(request) == "✅ Gimnasio · Fri 2030-01-04 12:00 · booked"
        err = capsys.readouterr().err
        assert "Notification sent." in err
        assert "s3cret" not in err

    def test_dry_run_title(self, mocked_api, notify_url, config_path):
        assert _run(config_path, "--dry-run") == 0

        [request] = _notifications(mocked_api)
        assert request.headers["Title"] == "[dry run] pysportbot: 1/1 bookable"

    def test_notify_on_flag_overrides_env(self, mocked_api, notify_url, monkeypatch, config_path):
        monkeypatch.setenv("SPORTBOT_NOTIFY_ON", "always")

        assert _run(config_path, "--notify-on", "failure") == 0

        assert _notifications(mocked_api) == []

    def test_notify_on_flag_without_url_warns(self, mocked_api, config_path, capsys):
        assert _run(config_path, "--notify-on", "failure") == 0

        assert "--notify-on has no effect: set SPORTBOT_NOTIFY_URL" in capsys.readouterr().err

    def test_notify_on_flag_rejects_invalid_value(self, config_path, capsys):
        assert _run(config_path, "--notify-on", "never") == 2

        assert "argument --notify-on: invalid choice: 'never'" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "response",
        [
            pytest.param({"status": 500}, id="http-500"),
            pytest.param({"body": requests.ConnectionError(f"Cannot connect to {URL}")}, id="network"),
        ],
    )
    @pytest.mark.parametrize(("class_time", "exit_code"), [("12:00", 0), ("10:00", 1)])
    def test_notification_failure_keeps_exit_code(
        self, response, class_time, exit_code, mocked_api, notify_url, full_slot_refused, config_path, capsys
    ):
        mocked_api.replace(responses.POST, URL, **response)
        config_path.write_text(
            json.dumps({"classes": [{"activity": "Gimnasio", "class_day": "Friday", "class_time": class_time}]})
        )

        assert _run(config_path) == exit_code

        assert len(_notifications(mocked_api)) == 1
        err = capsys.readouterr().err
        assert "[WARNING] Could not send the notification" in err
        assert "s3cret" not in err

    def test_fatal_error_sends_then_reraises(self, mocked_api, notify_url, config_path, capsys):
        mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=401, json={})

        assert _run(config_path, "--notify-on", "failure") == 1

        [request] = _notifications(mocked_api)
        assert request.headers["Title"] == "pysportbot: run failed"
        assert request.headers["Priority"] == "high"
        assert _body(request).startswith("Login failed:")
        assert "pysportbot: error: Login failed" in capsys.readouterr().err

    def test_config_error_after_loading_sends_then_exits_2(self, mocked_api, notify_url, config_path, capsys):
        config_path.write_text(
            json.dumps({"classes": [{"activity": "Zumba", "class_day": "Friday", "class_time": "12:00"}]})
        )

        assert _run(config_path) == 2

        [request] = _notifications(mocked_api)
        assert "No activity found with the name 'Zumba'" in _body(request)
        assert "No activity found with the name 'Zumba'" in capsys.readouterr().err

    def test_invalid_config_sends_nothing(self, mocked_api, notify_url, config_path):
        config_path.write_text(json.dumps({"classes": []}))

        assert _run(config_path) == 2

        assert len(mocked_api.calls) == 0
