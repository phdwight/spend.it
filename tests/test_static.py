"""Sanity checks that the PWA shell and its required assets are served."""
from __future__ import annotations

import json


def test_index_served_at_root(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>spend.it" in r.text
    assert "/static/manifest.webmanifest" in r.text
    assert "/static/app.js" in r.text


def test_app_js_registers_service_worker(client) -> None:
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "navigator.serviceWorker.register" in r.text
    assert "/sw.js" in r.text


def test_service_worker_served_at_root_scope(client) -> None:
    """The SW must be at /sw.js so its scope covers the whole origin."""
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    assert "self.addEventListener" in r.text


def test_manifest_is_valid_json_with_required_fields(client) -> None:
    r = client.get("/static/manifest.webmanifest")
    assert r.status_code == 200
    data = json.loads(r.text)
    for key in ("name", "short_name", "start_url", "display", "icons"):
        assert key in data, f"manifest missing '{key}'"
    assert data["start_url"] == "/"
    assert data["display"] == "standalone"
    assert len(data["icons"]) >= 1


def test_static_assets_are_served(client) -> None:
    for path in (
        "/static/app.js",
        "/static/styles.css",
        "/static/icons/icon.svg",
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.content, f"{path} returned empty body"


def test_unknown_route_returns_404(client) -> None:
    assert client.get("/does-not-exist").status_code == 404
