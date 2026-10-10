import logging
import re
import sys
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

import pytest

import pysportbot
from pysportbot.logging_utils import DATE_FORMAT, LOG_FORMAT, ColorFormatter, configure_logging, set_log_level

ANSI = re.compile(r"\033\[[0-9;]*m")
MADRID = ZoneInfo("Europe/Madrid")


class FakeTTY(StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def clean_logging(monkeypatch):
    """Give each test a "pysportbot" logger without our handler and no color env vars.

    configure_logging() then installs a fresh handler bound to the current sys.stderr, which `capsys` captures.
    """
    logger = logging.getLogger("pysportbot")
    root = logging.getLogger()
    saved = (logger.handlers[:], logger.level, logger.propagate, root.handlers[:], root.level)
    logger.handlers = [h for h in logger.handlers if not hasattr(h, "_pysportbot_handler")]
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    yield logger

    logger.handlers, _, logger.propagate, root.handlers, _ = saved
    logger.setLevel(saved[1])
    root.setLevel(saved[4])


def _our_handlers(logger):
    return [h for h in logger.handlers if hasattr(h, "_pysportbot_handler")]


def _record(msg="message", level=logging.INFO, thread_name="MainThread", created=None):
    record = logging.LogRecord("pysportbot.test", level, __file__, 1, msg, None, None)
    record.threadName = thread_name
    if created is not None:
        record.created = created
    return record


def _formatter(tz=MADRID, use_color=True):
    return ColorFormatter(LOG_FORMAT, DATE_FORMAT, tz=tz, include_threads=True, use_color=use_color)


def test_package_logger_has_null_handler():
    """Importing pysportbot alone must not print anything, even without logging configured."""
    handlers = logging.getLogger(pysportbot.__name__).handlers
    assert any(isinstance(h, logging.NullHandler) for h in handlers)


def test_configure_logging_does_not_touch_root_logger():
    root = logging.getLogger()
    handlers_before, level_before = root.handlers[:], root.level

    configure_logging(level="DEBUG")
    set_log_level("ERROR")

    assert root.handlers == handlers_before
    assert root.level == level_before


def test_configure_logging_is_idempotent(clean_logging, capsys):
    configure_logging(level="INFO")
    configure_logging(level="INFO")
    logging.getLogger("pysportbot.test").info("Only once.")

    assert len(_our_handlers(clean_logging)) == 1
    assert capsys.readouterr().err.count("Only once.") == 1


def test_configure_logging_again_updates_level(clean_logging, capsys):
    configure_logging(level="INFO")
    configure_logging(level="WARNING")
    logger = logging.getLogger("pysportbot.test")
    logger.info("This should not appear.")
    logger.warning("This is a warning.")

    output = capsys.readouterr().err
    assert "This is a warning." in output
    assert "This should not appear." not in output


def test_messages_are_not_duplicated_when_app_configures_root(clean_logging, capsys):
    """An app that calls logging.basicConfig() must not see pysportbot messages twice."""
    # What basicConfig() does, without closing pytest's own root handlers
    root_stream = StringIO()
    logging.getLogger().addHandler(logging.StreamHandler(root_stream))
    logging.getLogger().setLevel(logging.DEBUG)

    configure_logging(level="INFO")
    logging.getLogger("pysportbot.test").info("Hello.")

    assert capsys.readouterr().err.count("Hello.") == 1
    assert "Hello." not in root_stream.getvalue()
    assert clean_logging.propagate is False


def test_log_levels_are_filtered(capsys):
    configure_logging(level="WARNING")
    logger = logging.getLogger("pysportbot.test")
    logger.debug("This should not appear.")
    logger.info("This should not appear.")
    logger.warning("This is a warning.")
    logger.error("This is an error.")

    output = capsys.readouterr().err
    assert "This is a warning." in output
    assert "This is an error." in output
    assert "This should not appear." not in output


def test_level_names_are_case_insensitive(clean_logging):
    configure_logging(level="debug")
    assert clean_logging.level == logging.DEBUG


@pytest.mark.parametrize("setter", [configure_logging, set_log_level])
def test_invalid_level_raises(setter):
    with pytest.raises(ValueError, match=r"Invalid logging level: LOUD\. Valid levels are .*DEBUG"):
        setter("LOUD")


def test_set_log_level_changes_only_package_logger(clean_logging):
    root_level = logging.getLogger().level
    configure_logging(level="INFO")

    set_log_level("DEBUG")

    assert clean_logging.level == logging.DEBUG
    assert logging.getLogger().level == root_level


@pytest.mark.parametrize(
    ("stream", "env", "colored"),
    [
        pytest.param(FakeTTY, {}, True, id="tty"),
        pytest.param(FakeTTY, {"NO_COLOR": "1"}, False, id="tty+NO_COLOR"),
        pytest.param(FakeTTY, {"NO_COLOR": ""}, True, id="tty+empty-NO_COLOR"),
        pytest.param(StringIO, {}, False, id="pipe"),
        pytest.param(StringIO, {"FORCE_COLOR": "1"}, True, id="pipe+FORCE_COLOR"),
        pytest.param(FakeTTY, {"NO_COLOR": "1", "FORCE_COLOR": "1"}, False, id="NO_COLOR-wins"),
    ],
)
def test_color_follows_tty_and_env(monkeypatch, stream, env, colored):
    monkeypatch.setattr(sys, "stderr", stream())
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    configure_logging(level="INFO")
    logging.getLogger("pysportbot.test").info("Colorful?")

    output = sys.stderr.getvalue()
    assert "[INFO]    Colorful?" in ANSI.sub("", output)
    assert bool(ANSI.search(output)) is colored


def test_color_formatting():
    """Levels are padded to the width of "[WARNING]" and colored per level."""
    formatter = _formatter()

    assert "\033[92m[INFO]   \033[0m Info" in formatter.format(_record("Info", logging.INFO))
    assert "\033[93m[WARNING]\033[0m Warning" in formatter.format(_record("Warning", logging.WARNING))
    assert "\033[91m[ERROR]  \033[0m Error" in formatter.format(_record("Error", logging.ERROR))


def test_output_format_with_thread_info():
    """The full line: [timestamp] [LEVEL]   [Thread N] message."""
    created = datetime(2024, 12, 31, 14, 12, 23, tzinfo=MADRID).timestamp()
    record = _record("Booking...", thread_name="ThreadPoolExecutor-0_1", created=created)

    plain = _formatter(use_color=False).format(record)
    colored = _formatter().format(record)

    assert plain == "[2024-12-31 14:12:23] [INFO]    [Thread 1] Booking..."
    assert "[\033[95mThread 1\033[0m] Booking..." in colored
    assert ANSI.sub("", colored) == plain


def test_main_thread_has_no_thread_info():
    assert _formatter(use_color=False).format(_record("Hi")).endswith("[INFO]    Hi")


def test_timestamps_use_configured_time_zone():
    created = datetime(2024, 12, 31, 14, 12, 23, tzinfo=ZoneInfo("UTC")).timestamp()
    record = _record(created=created)

    assert _formatter(tz=ZoneInfo("America/New_York")).format(record).startswith("[2024-12-31 09:12:23]")
    assert _formatter(tz=MADRID).format(record).startswith("[2024-12-31 15:12:23]")


def test_default_time_zone_is_madrid(capsys):
    configure_logging(level="INFO")
    logging.getLogger("pysportbot.test").info("Now.")

    timestamp = capsys.readouterr().err.split("]")[0].strip("[")
    logged = datetime.strptime(timestamp, DATE_FORMAT).replace(tzinfo=MADRID)
    assert abs(logged.timestamp() - datetime.now(MADRID).timestamp()) < 2
