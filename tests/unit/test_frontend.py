"""The web UI is served by the same app without shadowing the API. No DB needed."""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import STATIC_DIR, app

client = TestClient(app)


def test_root_serves_the_ui() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<script type="module" src="/js/main.js">' in response.text


@pytest.mark.parametrize("path", ["/css/app.css", "/js/main.js", "/js/views/ticket.js"])
def test_assets_are_served(path: str) -> None:
    assert client.get(path).status_code == 200


def test_api_and_docs_still_win_over_the_static_mount() -> None:
    assert client.get("/openapi.json").json()["info"]["title"] == "TriageDesk"
    assert client.get("/docs").status_code == 200
    assert client.get("/api/v1/does-not-exist").status_code == 404


def test_every_js_import_resolves() -> None:
    """Catch typos in relative ES-module imports (they would only fail in a browser)."""
    for js in STATIC_DIR.rglob("*.js"):
        for target in re.findall(r'from "(\.{1,2}/[^"]+)"', js.read_text(encoding="utf-8")):
            assert (js.parent / target).resolve().is_file(), f"{js.name} imports missing {target}"


def test_ui_never_uses_inner_html() -> None:
    """Ticket text is customer input: rendering must go through text nodes (XSS)."""
    html_sinks = re.compile(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write")
    for js in STATIC_DIR.rglob("*.js"):
        assert not html_sinks.search(js.read_text(encoding="utf-8")), js.name
