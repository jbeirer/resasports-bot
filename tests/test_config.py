import json
from datetime import time

import pytest

from pysportbot.exceptions import ConfigError
from pysportbot.service.config import ClassSpec, ServiceConfig, WeeklyTime, load_config

CREDENTIALS = {"email": "file@example.com", "password": "file-secret", "centre": "file-centre"}
CLASSES = [{"activity": "Yoga", "class_day": "Monday", "class_time": "18:00:00"}]
VALID = {**CREDENTIALS, "booking_execution": "Friday 07:30:00", "classes": CLASSES}

TOML = """
centre = "my-gym"
booking_execution = "Friday 07:30"

[[classes]]
activity = "Yoga"
class_day = "Monday"
class_time = "18:00"
"""
ENV = {"SPORTBOT_EMAIL": "env@example.com", "SPORTBOT_PASSWORD": "env-secret", "SPORTBOT_CENTRE": "env-centre"}


def parse(data, env=None):
    return ServiceConfig.from_mapping(data, env={} if env is None else env)


def config_error(data, env=None) -> str:
    with pytest.raises(ConfigError) as exc_info:
        parse(data, env)
    return str(exc_info.value)


def test_from_mapping_parses_valid_config():
    config = parse(VALID)

    assert config == ServiceConfig(
        email="file@example.com",
        password="file-secret",
        centre="file-centre",
        execution=WeeklyTime(weekday=4, time=time(7, 30)),
        classes=(ClassSpec(activity="Yoga", weekday=0, time=time(18, 0)),),
    )


def test_load_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(VALID))

    assert load_config(path, env={}) == parse(VALID)


def test_load_toml(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(TOML)

    config = load_config(path, env=ENV)

    assert config.centre == "env-centre"
    assert config.execution == WeeklyTime(weekday=4, time=time(7, 30))
    assert config.classes == (ClassSpec(activity="Yoga", weekday=0, time=time(18, 0)),)


@pytest.mark.parametrize(
    ("name", "content", "match"),
    [
        pytest.param("config.json", "{invalid", "Cannot parse config file", id="invalid-json"),
        pytest.param("config.toml", "centre =", "Cannot parse config file", id="invalid-toml"),
        pytest.param("config.json", "[]", "must contain an object", id="not-an-object"),
        pytest.param("config.yaml", "centre: x", "Unsupported config file type '.yaml'", id="unsupported-suffix"),
    ],
)
def test_load_config_rejects_bad_files(tmp_path, name, content, match):
    path = tmp_path / name
    path.write_text(content)

    with pytest.raises(ConfigError, match=match):
        load_config(path, env={})


def test_load_toml_native_time(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(TOML.replace('class_time = "18:00"', "class_time = 18:00:00"))

    assert load_config(path, env=ENV).classes[0].time == time(18, 0)


def test_load_config_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="Cannot read config file"):
        load_config(tmp_path / "missing.json", env={})


def test_env_overrides_file_credentials():
    config = parse(VALID, env=ENV)

    assert (config.email, config.password, config.centre) == ("env@example.com", "env-secret", "env-centre")


def test_env_only_credentials():
    config = parse({"classes": CLASSES}, env=ENV)

    assert (config.email, config.password, config.centre) == ("env@example.com", "env-secret", "env-centre")


def test_empty_env_var_falls_back_to_file():
    # GitHub Actions expands a secret that is not configured to an empty string
    config = parse(VALID, env={"SPORTBOT_PASSWORD": ""})

    assert config.password == "file-secret"


def test_missing_credential():
    message = config_error({"email": "a@b.c", "centre": "c", "classes": CLASSES})

    assert "password: missing. Set it in the config file or via the SPORTBOT_PASSWORD env var." in message


@pytest.mark.parametrize("value", ["", "  ", 42])
def test_invalid_credential(value):
    assert "email: must be a non-empty string." in config_error({**VALID, "email": value})


def test_unknown_key_suggests_close_match():
    message = config_error({**VALID, "center": "file-centre"})

    assert "unknown key 'center', did you mean 'centre'?" in message


def test_unknown_key_without_close_match_lists_valid_keys():
    message = config_error({**VALID, "xyz": 1})

    assert (
        "unknown key 'xyz'. Valid keys are: email, password, centre, booking_execution, classes, notify_url, notify_on."
        in message
    )


def test_unknown_class_key_suggests_close_match():
    message = config_error({**VALID, "classes": [{"activty": "Yoga", "class_day": "Monday", "class_time": "18:00"}]})

    assert "classes[0]: unknown key 'activty', did you mean 'activity'?" in message


@pytest.mark.parametrize(
    ("day", "weekday"),
    [("Monday", 0), ("FRIDAY", 4), (" sunday ", 6), ("mon", 0), ("Thu", 3), ("SAT", 5)],
)
def test_weekday_names_and_abbreviations(day, weekday):
    config = parse(
        {**VALID, "booking_execution": f"{day.strip()} 07:30", "classes": [{**CLASSES[0], "class_day": day}]}
    )

    assert config.execution.weekday == weekday
    assert config.classes[0].weekday == weekday


@pytest.mark.parametrize("day", ["Funday", "Lunes", "Mo", "", 1])
def test_bad_weekday(day):
    message = config_error({**VALID, "classes": [{**CLASSES[0], "class_day": day}]})

    assert f"classes[0].class_day: invalid day {day!r}." in message


@pytest.mark.parametrize(("value", "expected"), [("18:00", time(18, 0)), ("07:30:15", time(7, 30, 15))])
def test_time_formats(value, expected):
    config = parse({**VALID, "classes": [{**CLASSES[0], "class_time": value}]})

    assert config.classes[0].time == expected


@pytest.mark.parametrize("value", ["25:00", "18", "6pm", "", 1800])
def test_bad_time(value):
    message = config_error({**VALID, "classes": [{**CLASSES[0], "class_time": value}]})

    assert f"classes[0].class_time: invalid time {value!r}." in message


@pytest.mark.parametrize("value", ["now", "NOW", " now "])
def test_booking_execution_now(value):
    assert parse({**VALID, "booking_execution": value}).execution is None


def test_booking_execution_defaults_to_now():
    data = {key: value for key, value in VALID.items() if key != "booking_execution"}

    assert parse(data).execution is None


@pytest.mark.parametrize("value", ["Friday07:30:00", "Friday 07:30 extra", "", 730])
def test_bad_booking_execution(value):
    assert f"booking_execution: invalid value {value!r}." in config_error({**VALID, "booking_execution": value})


def test_bad_booking_execution_day():
    assert "booking_execution: invalid day 'Funday'." in config_error({**VALID, "booking_execution": "Funday 07:30"})


@pytest.mark.parametrize(
    ("classes", "match"),
    [
        pytest.param([], "classes: must be a non-empty list of classes.", id="empty"),
        pytest.param({"activity": "Yoga"}, "classes: must be a non-empty list of classes.", id="not-a-list"),
        pytest.param(None, "classes: missing.", id="missing"),
        pytest.param(["Yoga"], "classes[0]: must be an object", id="not-an-object"),
        pytest.param([{"class_day": "Monday"}], "classes[0]: missing activity, class_time.", id="missing-keys"),
        pytest.param(
            [{**CLASSES[0], "activity": ""}], "classes[0].activity: must be a non-empty string.", id="empty-activity"
        ),
    ],
)
def test_bad_classes(classes, match):
    data = {**VALID, "classes": classes}
    if classes is None:
        del data["classes"]

    assert match in config_error(data)


def test_multiple_errors_reported_together():
    data = {
        "center": "x",
        "booking_execution": "Funday 7pm",
        "classes": [
            {"activity": "Yoga", "class_day": "Monday", "class_time": "25:00"},
            {"activity": "Pilates", "class_day": "Someday", "class_time": "18:00"},
        ],
    }

    message = config_error(data)

    assert message.startswith("Invalid configuration:\n")
    expected = [
        "unknown key 'center', did you mean 'centre'?",
        "email: missing.",
        "password: missing.",
        "centre: missing.",
        "booking_execution: invalid day 'Funday'.",
        "booking_execution: invalid time '7pm'.",
        "classes[0].class_time: invalid time '25:00'.",
        "classes[1].class_day: invalid day 'Someday'.",
    ]
    bullets = message.splitlines()[1:]
    assert len(bullets) == len(expected)
    for bullet, start in zip(bullets, expected, strict=True):
        assert bullet.startswith(f"  - {start}")


def test_password_not_in_repr():
    config = parse(VALID)

    assert "file-secret" not in repr(config)
    assert "password" not in repr(config)
    assert "file@example.com" in repr(config)


def test_weekly_time_str():
    assert str(WeeklyTime(weekday=4, time=time(7, 30))) == "Friday 07:30:00"
