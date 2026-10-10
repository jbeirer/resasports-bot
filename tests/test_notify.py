import json
from datetime import datetime, time
from email.header import decode_header, make_header
from zoneinfo import ZoneInfo

import pytest
import requests
import responses

from pysportbot.cli import main
from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import AuthenticationError, ConfigError
from pysportbot.service import notify
from pysportbot.service.config import (
    NOTIFY_LANGUAGES,
    ClassSpec,
    NotifySettings,
    ServiceConfig,
    notify_settings_from_env,
)
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


def _title(request) -> str:
    """The Title header, decoded from RFC 2047 if needed."""
    return str(make_header(decode_header(request.headers["Title"])))


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


@pytest.mark.parametrize(
    ("language", "title", "lines"),
    [
        (
            "de",
            "pysportbot: 1/3 gebucht",
            [
                "✅ Yoga · Mo 12.01.2026 18:00 · gebucht (3 Versuche)",
                "❌ Spinning · Di 13.01.2026 07:00 · ausgebucht",
                "❌ Pilates · Mi 14.01.2026 09:30 · fehlgeschlagen (3 Versuche): Booking slot 5003 failed (error code 99).",
            ],
        ),
        (
            "es",
            "pysportbot: 1/3 reservadas",
            [
                "✅ Yoga · lun 12/01/2026 18:00 · reservada (3 intentos)",
                "❌ Spinning · mar 13/01/2026 07:00 · completa",
                "❌ Pilates · mié 14/01/2026 09:30 · fallida (3 intentos): Booking slot 5003 failed (error code 99).",
            ],
        ),
        (
            "fr",
            "pysportbot: 1/3 réservés",
            [
                "✅ Yoga · lun. 12/01/2026 18:00 · réservé (3 tentatives)",
                "❌ Spinning · mar. 13/01/2026 07:00 · complet",
                "❌ Pilates · mer. 14/01/2026 09:30 · échec (3 tentatives): Booking slot 5003 failed (error code 99).",
            ],
        ),
        (
            "it",
            "pysportbot: 1/3 prenotate",
            [
                "✅ Yoga · lun 12/01/2026 18:00 · prenotata (3 tentativi)",
                "❌ Spinning · mar 13/01/2026 07:00 · al completo",
                "❌ Pilates · mer 14/01/2026 09:30 · non riuscita (3 tentativi): Booking slot 5003 failed (error code 99).",
            ],
        ),
    ],
)
def test_format_summary_languages(language, title, lines):
    assert notify.format_summary([YOGA, SPINNING, PILATES], language=language) == (title, "\n".join(lines))


@pytest.mark.parametrize(
    ("language", "title"),
    [
        ("de", "[Testlauf] pysportbot: 1/1 buchbar"),
        ("es", "[simulación] pysportbot: 1/1 reservables"),
        ("fr", "[simulation] pysportbot: 1/1 réservables"),
        ("it", "[simulazione] pysportbot: 1/1 prenotabili"),
    ],
)
def test_format_summary_dry_run_languages(language, title):
    assert notify.format_summary([YOGA_DRY_RUN], dry_run=True, language=language)[0] == title


def _result(activity, status=BookingStatus.BOOKED, error=None):
    return BookingResult(
        ClassSpec(activity, 0, time(18)), datetime(2026, 1, 12, 18, tzinfo=TZ), status, attempts=1, error=error
    )


def test_long_summary_fits_one_message_with_failures_first():
    results = [_result(f"Class {i:03} " + "x" * 40) for i in range(100)]
    results[70] = _result("Late failure", BookingStatus.FULL)

    title, body = notify.format_summary(results)

    lines = body.splitlines()
    assert len(body.encode("utf-8")) <= notify.MAX_MESSAGE_BYTES
    assert title == "pysportbot: 99/100 booked"
    assert lines[0] == "❌ Late failure · Mon 2026-01-12 18:00 · full"
    assert lines[1].startswith("✅ Class 000 ")
    kept = len(lines) - 1
    assert lines[-1] == f"… and {100 - kept} more"


def test_long_summary_more_line_in_language():
    results = [_result(f"Class {i:03} " + "x" * 40) for i in range(100)]

    _, body = notify.format_summary(results, language="it")

    assert body.splitlines()[-1].startswith("… e altre ")


def test_long_error_is_truncated():
    _, body = notify.format_summary([_result("Yoga", BookingStatus.FAILED, error="é" * 5000)])

    assert len(body.encode("utf-8")) <= notify.MAX_LINE_BYTES
    assert body.startswith("❌ Yoga · Mon 2026-01-12 18:00 · failed: éé")
    assert body.endswith("é…")


def test_send_truncates_long_fatal_error(ntfy):
    notify.send(ALWAYS, error=ConfigError("x" * 10_000))

    [request] = _notifications(ntfy)
    assert len(request.body) == notify.MAX_MESSAGE_BYTES
    assert _body(request).endswith("x…")


@pytest.mark.parametrize("language", NOTIFY_LANGUAGES)
def test_every_language_is_complete(language):
    texts = notify.TEXTS[language]

    assert set(texts.statuses) == set(BookingStatus)
    assert len(texts.weekdays) == 7


def test_languages_match_config():
    assert tuple(notify.TEXTS) == NOTIFY_LANGUAGES


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


def test_send_encodes_non_ascii_title(ntfy):
    notify.send(NotifySettings(url=URL, language="fr"), [YOGA])

    [request] = _notifications(ntfy)
    assert request.headers["Title"].isascii()
    assert request.headers["Title"].startswith("=?UTF-8?B?")
    assert _title(request) == "pysportbot: 1/1 réservés"
    assert _body(request) == "✅ Yoga · lun. 12/01/2026 18:00 · réservé (3 tentatives)"


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


def test_send_error_title_in_language(ntfy):
    notify.send(NotifySettings(url=URL, language="es"), error=AuthenticationError("Invalid credentials"))

    [request] = _notifications(ntfy)
    assert _title(request) == "pysportbot: ejecución fallida"


@pytest.mark.parametrize(
    "response",
    [
        pytest.param({"body": "<html>Log in</html>", "content_type": "text/html"}, id="html"),
        pytest.param({"json": {"ok": True}}, id="json-without-id"),
        pytest.param({"json": ["id"]}, id="json-list"),
    ],
)
def test_send_warns_if_response_is_not_from_ntfy(response, pysportbot_caplog):
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, URL, **response)
        notify.send(ALWAYS, [YOGA])

    [record] = [r for r in pysportbot_caplog.records if r.name == "pysportbot.service.notify"]
    assert record.levelname == "WARNING"
    assert record.getMessage().startswith("The notification URL answered HTTP 200, but not like an ntfy server.")
    assert "s3cret" not in pysportbot_caplog.text


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
        "https://ntfy.example",
        "https://ntfy.example/",
        "https://ntfy.example/s3cret-topic#fragment",
        "https://[s3cret-topic",
        "",
        42,
    ],
)
def test_invalid_notify_url(url):
    message = config_error({"notify_url": url})

    assert "notify_url: must be the https:// URL of an ntfy topic" in message
    assert "s3cret" not in message


def test_invalid_notify_url_from_env():
    message = config_error({}, {"SPORTBOT_NOTIFY_URL": "http://ntfy.example/s3cret-topic"})

    assert "notify_url: must be the https:// URL of an ntfy topic" in message
    assert "s3cret" not in message


@pytest.mark.parametrize(("data", "env"), [({"notify_on": "never"}, {}), ({}, {"SPORTBOT_NOTIFY_ON": "never"})])
def test_invalid_notify_on(data, env):
    message = config_error({"notify_url": URL, **data}, env)

    assert "notify_on: invalid value 'never'. Use one of: always, failure." in message


def test_notify_language_from_file_and_env():
    assert parse({"notify_url": URL, "notify_language": "it"}).notify == NotifySettings(url=URL, language="it")
    config = parse({"notify_url": URL, "notify_language": "it"}, {"SPORTBOT_NOTIFY_LANGUAGE": " DE "})
    assert config.notify == NotifySettings(url=URL, language="de")


@pytest.mark.parametrize("language", ["pt", "german", 1])
def test_invalid_notify_language(language):
    message = config_error({"notify_url": URL, "notify_language": language})

    assert f"notify_language: invalid value {language!r}. Use one of: en, de, es, fr, it." in message


def test_notify_url_with_credentials_and_query():
    url = "https://user:s3cret@ntfy.example/topic?auth=abc"

    assert parse({"notify_url": url}).notify == NotifySettings(url=url)


def test_notify_settings_from_env():
    env = {"SPORTBOT_NOTIFY_URL": URL, "SPORTBOT_NOTIFY_ON": "failure", "SPORTBOT_NOTIFY_LANGUAGE": "it"}

    assert notify_settings_from_env(env) == NotifySettings(url=URL, on="failure", language="it")
    assert notify_settings_from_env({}) is None
    assert notify_settings_from_env({"SPORTBOT_NOTIFY_URL": "https://ntfy.example"}) is None
    assert notify_settings_from_env({"SPORTBOT_NOTIFY_URL": URL, "SPORTBOT_NOTIFY_LANGUAGE": "pt"}) is None


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

    def test_language_from_env(self, mocked_api, notify_url, monkeypatch, config_path):
        monkeypatch.setenv("SPORTBOT_NOTIFY_LANGUAGE", "de")

        assert _run(config_path) == 0

        [request] = _notifications(mocked_api)
        assert request.headers["Title"] == "pysportbot: 1/1 gebucht"
        assert _body(request) == "✅ Gimnasio · Fr 04.01.2030 12:00 · gebucht"

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

    def test_invalid_config_sends_error_to_url_from_env(self, mocked_api, notify_url, config_path, capsys):
        config_path.write_text(json.dumps({"classes": []}))

        assert _run(config_path, "--notify-on", "failure") == 2

        [request] = _notifications(mocked_api)
        assert len(mocked_api.calls) == 1
        assert request.headers["Title"] == "pysportbot: run failed"
        assert "classes: must be a non-empty list of classes." in _body(request)
        assert "classes: must be a non-empty list of classes." in capsys.readouterr().err

    def test_missing_config_file_sends_error_to_url_from_env(self, mocked_api, notify_url, tmp_path):
        assert _run(tmp_path / "missing.json") == 2

        [request] = _notifications(mocked_api)
        assert "Cannot read config file" in _body(request)

    def test_invalid_config_with_url_only_in_file_sends_nothing(self, mocked_api, config_path):
        config_path.write_text(json.dumps({"classes": [], "notify_url": URL}))

        assert _run(config_path) == 2

        assert len(mocked_api.calls) == 0

    def test_invalid_notify_env_var_sends_nothing(self, mocked_api, notify_url, monkeypatch, config_path):
        monkeypatch.setenv("SPORTBOT_NOTIFY_ON", "never")

        assert _run(config_path) == 2

        assert len(mocked_api.calls) == 0
