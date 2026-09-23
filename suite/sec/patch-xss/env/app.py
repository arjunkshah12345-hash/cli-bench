"""Comment board: adds comments and renders them into an HTML page.

(Vulnerable on purpose — see tests/test_exploit.py.)
"""

import html as _html_mod  # noqa: F401  (imported but unused by the vulnerable path)
import json
from pathlib import Path

STORE = Path(__file__).resolve().parent / "comments.json"


def load_comments():
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return []


def add_comment(author, body):
    comments = load_comments()
    comments.append({"author": author, "body": body})
    STORE.write_text(json.dumps(comments, indent=2), encoding="utf-8")
    return comments[-1]


def render_comment(comment):
    # UNSAFE: user content interpolated directly into HTML
    return f"<div class='comment'><b>{comment['author']}</b>: {comment['body']}</div>"


def render_page():
    parts = ["<html><body><h1>Comments</h1>"]
    for c in load_comments():
        parts.append(render_comment(c))
    parts.append("</body></html>")
    return "\n".join(parts)


if __name__ == "__main__":
    print(render_page())
