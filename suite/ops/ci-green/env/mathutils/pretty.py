"""Pretty JSON formatting helpers."""

import json


def dumps(data, indent=2):
    return json.dumps(data, indent=indent)
