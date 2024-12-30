import json
from typing import Any, Dict, cast


def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path) as f:
        return cast(Dict[str, Any], json.load(f))
