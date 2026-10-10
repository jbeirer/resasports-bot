from pathlib import Path

import pysportbot


def test_version_is_installed_version():
    assert isinstance(pysportbot.__version__, str)
    assert pysportbot.__version__ != "0+unknown"


def test_all_names_are_exported():
    for name in pysportbot.__all__:
        assert hasattr(pysportbot, name), name


def test_package_is_typed():
    assert (Path(pysportbot.__file__).parent / "py.typed").is_file()
