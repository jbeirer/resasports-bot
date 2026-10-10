import io
import json
import logging
import sys
from datetime import date
from urllib.parse import parse_qs

import pytest
import responses

import pysportbot
from pysportbot import SportBot
from pysportbot.cli import main, parse_day
from pysportbot.endpoints import Endpoints
from pysportbot.service.__main__ import main as service_main
from pysportbot.service.config import ENV_VARS

FRIDAY = date(2030, 1, 4)  # The day of the fixture's slots


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def cli_env(monkeypatch):
    """
    Run each test without credentials in the env, without a terminal on stdin, and with a fresh "pysportbot" log
    handler, which `main()` then binds to the stderr that `capsys` captures.
    """
    for name in ENV_VARS.values():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    logger = logging.getLogger("pysportbot")
    monkeypatch.setattr(logger, "handlers", [h for h in logger.handlers if not hasattr(h, "_pysportbot_handler")])
    monkeypatch.setattr(logger, "level", logger.level)
    monkeypatch.setattr(logger, "propagate", logger.propagate)


@pytest.fixture
def today(monkeypatch):
    """Make the CLI's today Thursday 2030-01-03, the day before the fixture's slots."""
    monkeypatch.setattr("pysportbot.cli._today", lambda time_zone: date(2030, 1, 3))


def _calls(mocked_api, endpoint):
    return [c for c in mocked_api.calls if c.request.url == str(endpoint)]


def _slots_request_day(mocked_api) -> str:
    body = _calls(mocked_api, Endpoints.SLOTS)[-1].request.body
    return parse_qs(body)["start_timestamp"][0]


def test_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out == f"pysportbot {pysportbot.__version__}\n"


@pytest.mark.parametrize("argv", [["--help"], ["centres", "--help"], ["run", "--help"]])
def test_help(argv, capsys):
    assert main(argv) == 0
    assert "usage: pysportbot" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="no-command"),
        pytest.param(["bookings"], id="unknown-command"),
        pytest.param(["book", "Yoga", "next friday"], id="invalid-start"),
        pytest.param(["--log-level", "LOUD", "centres"], id="invalid-log-level"),
    ],
)
def test_usage_error_exits_2(argv, mocked_api, capsys):
    assert main(argv) == 2
    assert "usage: pysportbot" in capsys.readouterr().err
    assert len(mocked_api.calls) == 0


def test_centres_table_needs_no_login(mocked_api, capsys):
    assert main(["centres"]) == 0

    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert lines[0].split() == ["SLUG", "NAME", "TOWN", "COUNTRY"]
    assert lines[1].split() == ["test-centre", "Test", "Centre", "Testville", "Spain"]
    assert len(lines) == 4
    # Columns are aligned
    assert len({line.index(town) for line, town in zip(lines, ["TOWN", "Testville", "Otherville"], strict=False)}) == 1
    # The default log level is WARNING, so nothing but the table is printed
    assert err == ""
    assert _calls(mocked_api, Endpoints.USER_LOGIN) == []


def test_centres_json(mocked_api, capsys):
    assert main(["centres", "--json"]) == 0

    centres = json.loads(capsys.readouterr().out)
    assert len(centres) == 3
    assert centres[0] == {
        "slug": "test-centre",
        "name": "Test Centre",
        "town": "Testville",
        "country": "Spain",
        "address": "Calle Falsa 123",
    }


def test_centres_search(mocked_api, capsys):
    assert main(["centres", "--search", "OTHER", "--json"]) == 0
    assert [c["slug"] for c in json.loads(capsys.readouterr().out)] == ["other-centre"]

    assert main(["centres", "--search", "nowhere"]) == 0
    assert capsys.readouterr().out == "No centres match 'nowhere'.\n"


def test_activities(mocked_api, credentials_env, capsys):
    assert main(["activities"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["NAME", "ID", "CATEGORY"]
    assert [line.split()[0] for line in lines[1:]] == ["Yoga", "Gimnasio", "Pilates"]


def test_activities_json(mocked_api, credentials_env, capsys):
    assert main(["activities", "--json"]) == 0

    activities = json.loads(capsys.readouterr().out)
    assert [a["name"] for a in activities] == ["Yoga", "Gimnasio", "Pilates"]
    assert set(activities[0]) == {"id", "name", "category_id"}


def test_slots_on_date(mocked_api, credentials_env, capsys):
    assert main(["slots", "Yoga", "2030-01-04"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["START", "END", "TAKEN", "WAITING", "TRAINER", "STATUS"]
    assert lines[1].split() == ["2030-01-04", "09:00", "10:00", "5/15", "0", "Trainer", "A"]
    assert len(lines) == 3
    assert _slots_request_day(mocked_api) == "2030-01-04"


def test_slots_json_has_iso_times(mocked_api, credentials_env, capsys):
    assert main(["slots", "Gimnasio", "2030-01-04", "--json"]) == 0

    slots = json.loads(capsys.readouterr().out)
    assert [s["start"] for s in slots] == ["2030-01-04T10:00:00+01:00", "2030-01-04T12:00:00+01:00"]
    assert slots[0]["inscribed"] == slots[0]["capacity"] == 30


def test_slots_marks_full_slots(mocked_api, credentials_env, capsys):
    assert main(["slots", "Gimnasio", "2030-01-04"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[1].endswith("full")
    assert not lines[2].endswith("full")


@pytest.mark.parametrize(("day", "expected"), [("tomorrow", "2030-01-04"), ("monday", "2030-01-07")])
def test_slots_day_keywords(day, expected, mocked_api, credentials_env, today):
    assert main(["slots", "Yoga", day]) == 0
    assert _slots_request_day(mocked_api) == expected


def test_slots_invalid_day_exits_2_before_login(mocked_api, credentials_env, capsys):
    assert main(["slots", "Yoga", "someday"]) == 2
    assert "invalid day 'someday'" in capsys.readouterr().err
    assert len(mocked_api.calls) == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("today", FRIDAY),
        ("Tomorrow", date(2030, 1, 5)),
        # A weekday name is its next occurrence, today included
        ("friday", FRIDAY),
        ("Mon", date(2030, 1, 7)),
        ("thursday", date(2030, 1, 10)),
        (" 2030-02-01 ", date(2030, 2, 1)),
    ],
)
def test_parse_day(value, expected):
    assert parse_day(value, today=FRIDAY) == expected


@pytest.mark.parametrize("value", ["someday", "2030-13-01", "04/01/2030", ""])
def test_parse_day_rejects_invalid_days(value):
    with pytest.raises(ValueError, match="invalid day"):
        parse_day(value, today=FRIDAY)


def test_book(mocked_api, credentials_env, capsys):
    assert main(["book", "Gimnasio", "2030-01-04 12:00"]) == 0

    assert capsys.readouterr().out == "Booked 'Gimnasio' on 2030-01-04 12:00\n"
    assert len(_calls(mocked_api, Endpoints.BOOKING)) == 1


def test_book_already_booked_exits_1(mocked_api, credentials_env, capsys):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": 5})

    assert main(["book", "Gimnasio", "2030-01-04 12:00:00"]) == 1

    out, err = capsys.readouterr()
    assert out == ""
    assert "pysportbot: error: Slot 5004 is already booked (error code 5)." in err
    assert "Traceback" not in err


def test_failure_shows_traceback_at_debug_level(mocked_api, credentials_env, capsys):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": 5})

    assert main(["--log-level", "DEBUG", "book", "Gimnasio", "2030-01-04 12:00"]) == 1

    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "SlotAlreadyBookedError" in err


def test_login_failure_exits_1_without_traceback(mocked_api, credentials_env, capsys):
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=401, json={})

    assert main(["activities"]) == 1

    err = capsys.readouterr().err
    assert "pysportbot: error: Login failed" in err
    # The library logs the failure too, but without the traceback
    assert "Traceback" not in err


def test_cancel(mocked_api, credentials_env, capsys):
    assert main(["cancel", "Yoga", "2030-01-04 18:00"]) == 0

    assert capsys.readouterr().out == "Cancelled 'Yoga' on 2030-01-04 18:00\n"
    assert len(_calls(mocked_api, Endpoints.CANCELLATION)) == 1


def test_missing_password_without_tty_exits_2(mocked_api, monkeypatch, capsys):
    monkeypatch.setenv("SPORTBOT_EMAIL", "user@example.com")
    monkeypatch.setenv("SPORTBOT_CENTRE", "test-centre")

    assert main(["activities"]) == 2

    err = capsys.readouterr().err
    assert "SPORTBOT_PASSWORD" in err
    assert "SPORTBOT_EMAIL" not in err
    assert len(mocked_api.calls) == 0


def test_missing_credentials_are_listed_together(mocked_api, capsys):
    assert main(["slots", "Yoga", "today"]) == 2

    err = capsys.readouterr().err
    for name in ("SPORTBOT_EMAIL", "SPORTBOT_CENTRE", "SPORTBOT_PASSWORD"):
        assert name in err
    assert len(mocked_api.calls) == 0


def test_flags_and_password_prompt_on_tty(mocked_api, monkeypatch, capsys):
    prompts = []
    monkeypatch.setattr(sys, "stdin", FakeTTY())
    monkeypatch.setattr("getpass.getpass", lambda prompt: prompts.append(prompt) or "password")

    assert main(["activities", "--email", "user@example.com", "--centre", "test-centre"]) == 0

    assert prompts == ["Password for user@example.com: "]
    assert json.loads(_calls(mocked_api, Endpoints.USER_LOGIN)[0].request.body)["username"] == "user@example.com"


def test_empty_password_prompt_exits_2(mocked_api, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", FakeTTY())
    monkeypatch.setattr("getpass.getpass", lambda prompt: "")

    assert main(["activities", "--email", "user@example.com", "--centre", "test-centre"]) == 2
    assert "no password entered" in capsys.readouterr().err
    assert len(mocked_api.calls) == 0


def test_keyboard_interrupt_exits_130(monkeypatch, capsys):
    def interrupt(self, search=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(SportBot, "centres", interrupt)

    assert main(["centres"]) == 130
    assert "Interrupted." in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--log-level", "debug", "centres"], id="before-command"),
        pytest.param(["centres", "--log-level", "debug"], id="after-command"),
    ],
)
def test_global_options_before_or_after_command(argv, mocked_api, capsys):
    assert main(argv) == 0
    assert "[DEBUG]" in capsys.readouterr().err


def test_run_dry_run_sends_no_booking(mocked_api, mock_time, frozen_now, config_path, credentials_env, capsys):
    assert main(["run", "--config", str(config_path), "--dry-run"]) == 0

    assert _calls(mocked_api, Endpoints.BOOKING) == []
    err = capsys.readouterr().err
    assert "DRY RUN: would book 'Gimnasio' on Friday 2030-01-04 at 12:00 (slot 5004, 10/30 places taken)." in err
    # run logs at INFO by default
    assert "[INFO]" in err


def _write_config(path, class_time):
    path.write_text(
        json.dumps({"classes": [{"activity": "Gimnasio", "class_day": "Friday", "class_time": class_time}]})
    )


def test_run_dry_run_reports_full_slot(mocked_api, mock_time, frozen_now, config_path, credentials_env, capsys):
    _write_config(config_path, "10:00")  # The fixture's full Gimnasio slot

    assert main(["run", "--config", str(config_path), "--dry-run", "--retry-attempts", "3"]) == 1

    err = capsys.readouterr().err
    assert "would book" not in err
    assert "after 1 attempt(s): Slot 5002 is full and cannot be booked." in err
    assert _calls(mocked_api, Endpoints.BOOKING) == []
    mock_time.sleep.assert_not_called()


def _write_classes(path, *classes):
    path.write_text(
        json.dumps(
            {"classes": [{"activity": activity, "class_day": "Friday", "class_time": t} for activity, t in classes]}
        )
    )


def test_run_exits_1_if_a_class_is_not_booked(mocked_api, mock_time, frozen_now, config_path, credentials_env, capsys):
    _write_classes(config_path, ("Gimnasio", "12:00"), ("Gimnasio", "10:00"))  # Open and full

    assert main(["run", "--config", str(config_path)]) == 1

    err = capsys.readouterr().err
    assert "Booking summary:" in err
    assert "Gimnasio  Friday 2030-01-04  12:00  booked  " in err
    assert "Gimnasio  Friday 2030-01-04  10:00  full    " in err
    assert "1 of 2 classes could not be booked." in err


def test_run_exits_0_if_all_classes_are_booked_or_already_booked(
    mocked_api, mock_time, frozen_now, config_path, credentials_env, capsys
):
    _write_classes(config_path, ("Gimnasio", "12:00"), ("Yoga", "18:00"))
    mocked_api.add(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": 5})

    assert main(["run", "--config", str(config_path)]) == 0

    err = capsys.readouterr().err
    assert " booked " in err
    assert " already booked " in err
    assert "All bookings completed." in err


def test_run_accepts_fractional_seconds(mocked_api, mock_time, frozen_now, config_path, credentials_env):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": 28})
    mocked_api.add(responses.POST, str(Endpoints.BOOKING), json={"success": True})
    argv = ["run", "--config", str(config_path), "--booking-delay", "0.25", "--poll-interval", "0.1"]

    assert main([*argv, "--poll-window", "5", "--retry-delay", "0.5"]) == 0

    assert [c.args for c in mock_time.sleep.call_args_list] == [(0.25,), (0.1,)]


def test_run_dry_run_reports_cancelled_slot(
    mocked_api, mock_time, frozen_now, config_path, credentials_env, payloads, capsys
):
    calendar = payloads["activities_calendar"]
    entry = next(e for e in calendar["data"]["activities_calendar"] if e["id_activity_calendar"] == 5004)
    entry["cancelled"] = 1
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json=calendar)

    assert main(["run", "--config", str(config_path), "--dry-run"]) == 1

    err = capsys.readouterr().err
    assert "would book" not in err
    assert "after 1 attempt(s): Slot 5004 is cancelled, so booking it would fail." in err
    assert "Gimnasio  Friday 2030-01-04  12:00  failed  1" in err
    assert _calls(mocked_api, Endpoints.BOOKING) == []


def test_main_removes_traceback_filter_when_done(mocked_api):
    assert main(["centres"]) == 0

    handler = next(h for h in logging.getLogger("pysportbot").handlers if hasattr(h, "_pysportbot_handler"))
    assert handler.filters == []


def test_service_alias_runs_run_command(mocked_api, mock_time, frozen_now, config_path, credentials_env):
    assert service_main(["--config", str(config_path), "--max-threads", "-1"]) == 0

    assert len(_calls(mocked_api, Endpoints.BOOKING)) == 1


def test_service_alias_exits_1_if_a_class_is_not_booked(
    mocked_api, mock_time, frozen_now, config_path, credentials_env
):
    _write_config(config_path, "10:00")  # The fixture's full Gimnasio slot

    assert service_main(["--config", str(config_path)]) == 1


def test_run_reports_config_error_without_traceback(mocked_api, tmp_path, capsys):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"booking_execution": "now", "classes": [], "center": "test-centre"}))

    assert main(["run", "--config", str(path)]) == 2

    err = capsys.readouterr().err
    assert "unknown key 'center', did you mean 'centre'?" in err
    assert "SPORTBOT_EMAIL" in err
    assert "Traceback" not in err
    assert len(mocked_api.calls) == 0


def test_run_reports_unknown_activity_as_config_error(mocked_api, config_path, credentials_env, capsys):
    config_path.write_text(
        json.dumps({"classes": [{"activity": "Zumba", "class_day": "Friday", "class_time": "12:00"}]})
    )

    assert main(["run", "--config", str(config_path)]) == 2
    assert "No activity found with the name 'Zumba'" in capsys.readouterr().err
    assert _calls(mocked_api, Endpoints.BOOKING) == []


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--max-threads", "0"),
        ("--max-threads", "-2"),
        ("--max-threads", "two"),
        ("--retry-attempts", "0"),
        ("--retry-delay", "-1"),
        ("--booking-delay", "-1"),
        ("--booking-delay", "inf"),
        ("--retry-delay", "nan"),
        ("--retry-delay", "five"),
        ("--poll-interval", "0"),
        ("--poll-interval", "-0.5"),
        ("--poll-window", "-1"),
        ("--time-zone", "Mars/Base"),
        ("--time-zone", "../etc"),
        ("--log-level", "LOUD"),
    ],
)
def test_run_rejects_invalid_arguments(option, value, config_path, capsys):
    assert service_main(["--config", str(config_path), option, value]) == 2

    err = capsys.readouterr().err
    assert f"argument {option}:" in err
    assert "Traceback" not in err
