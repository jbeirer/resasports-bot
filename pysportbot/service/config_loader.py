import json
from typing import Any, cast


def load_config(config_path: str) -> dict[str, Any]:
    with open(config_path) as f:
        return cast(dict[str, Any], json.load(f))
