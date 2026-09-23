"""Formatting utilities — depends on the local mathutils package."""

import json

from mathutils import dumps as pretty_dumps


def export(data, path, pretty=False):
    with open(path, "w", encoding="utf-8") as fh:
        if pretty:
            fh.write(pretty_dumps(data))
        else:
            fh.write(json.dumps(data))
    return path
