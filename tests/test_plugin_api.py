import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


API_PATH = Path(__file__).parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("pending_queue_monitor_api", API_PATH)
plugin_api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin_api
spec.loader.exec_module(plugin_api)


def _write(home: Path, subsystem: str, name: str, record: object) -> None:
    directory = home / "pending" / subsystem
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(record), encoding="utf-8")


def _client(monkeypatch, root: Path) -> TestClient:
    app = FastAPI()
    app.include_router(plugin_api.router, prefix="/api/plugins/pending-queue-monitor")
    monkeypatch.setattr(plugin_api, "_default_root", lambda: root)
    return TestClient(app)


def test_default_and_named_profiles_are_scanned_without_payload(monkeypatch, tmp_path):
    named = tmp_path / "profiles" / "investor"
    (named / "config.yaml").parent.mkdir(parents=True)
    (named / "config.yaml").write_text("profile: investor\n", encoding="utf-8")
    now = datetime.now(timezone.utc).timestamp()
    _write(tmp_path, "memory", "one.json", {"id": "m1", "action": "add", "origin": "foreground", "created_at": now - 120, "summary": "SECRET SUMMARY", "payload": {"content": "SECRET PAYLOAD"}})
    _write(named, "skills", "two.json", {"id": "s1", "action": "edit", "origin": "background_review", "created_at": now - 7200, "summary": "HIDDEN", "old_text": "HIDDEN"})
    response = _client(monkeypatch, tmp_path).get("/api/plugins/pending-queue-monitor/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["total"] == 2
    assert {row["profile"] for row in body["items"]} == {"default", "investor"}
    assert "SECRET" not in json.dumps(body)
    assert set(body["items"][0]) == plugin_api._ALLOWLIST
    assert body["totals"]["oldest_age_seconds"] >= 7100


def test_malformed_disappearing_and_symlink_files_are_skipped(monkeypatch, tmp_path):
    _write(tmp_path, "memory", "bad.json", {"id": "bad", "created_at": "not-a-time"})
    _write(tmp_path, "skills", "broken.json", "not an object")
    directory = tmp_path / "pending" / "memory"
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"id": "outside", "created_at": 1}), encoding="utf-8")
    (directory / "link.json").symlink_to(outside)
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/plugins/pending-queue-monitor/overview")
    assert response.status_code == 200
    assert response.json()["totals"]["total"] == 0
    assert response.json()["skipped"] == 3


def test_empty_queue_and_timestamp_formats(monkeypatch, tmp_path):
    empty = _client(monkeypatch, tmp_path).get("/api/plugins/pending-queue-monitor/overview").json()
    assert empty["items"] == []
    assert empty["totals"]["oldest_age_seconds"] is None
    now = datetime.now(timezone.utc).timestamp()
    _write(tmp_path, "memory", "iso.json", {"id": "iso", "created_at": datetime.fromtimestamp(now - 10, timezone.utc).isoformat()})
    body = _client(monkeypatch, tmp_path).get("/api/plugins/pending-queue-monitor/overview").json()
    assert body["items"][0]["created_at"].endswith("Z")
    assert 0 <= body["items"][0]["age_seconds"] <= 20


def test_scan_failure_is_http_500(monkeypatch, tmp_path):
    _client(monkeypatch, tmp_path)
    monkeypatch.setattr(plugin_api, "build_overview", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    app = FastAPI()
    app.include_router(plugin_api.router, prefix="/api/plugins/pending-queue-monitor")
    assert app.router.routes
    status_code = TestClient(app).get("/api/plugins/pending-queue-monitor/overview").status_code
    assert not 200 <= status_code < 300
    assert status_code == 500


def test_size_item_and_shape_limits_are_explicit(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).timestamp()
    _write(tmp_path, "memory", "bad-shape.json", {"id": "\n", "created_at": now})
    (tmp_path / "pending" / "memory" / "too-large.json").write_bytes(b"{}" + b" " * plugin_api._MAX_FILE_BYTES)
    body = _client(monkeypatch, tmp_path).get("/api/plugins/pending-queue-monitor/overview").json()
    assert body["totals"]["total"] == 0
    assert body["truncated"] is False


def test_item_limit_sets_truncated(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).timestamp()
    _write(tmp_path, "memory", "one.json", {"id": "one", "created_at": now})
    _write(tmp_path, "memory", "two.json", {"id": "two", "created_at": now})
    monkeypatch.setattr(plugin_api, "_MAX_ITEMS", 1)
    body = _client(monkeypatch, tmp_path).get("/api/plugins/pending-queue-monitor/overview").json()
    assert body["totals"]["total"] == 1
    assert body["truncated"] is True


def test_hardlink_is_skipped(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).timestamp()
    _write(tmp_path, "memory", "original.json", {"id": "one", "created_at": now})
    linked = tmp_path / "pending" / "memory" / "linked.json"
    linked.hardlink_to(tmp_path / "pending" / "memory" / "original.json")
    body = _client(monkeypatch, tmp_path).get("/api/plugins/pending-queue-monitor/overview").json()
    assert body["totals"]["total"] == 0
    assert body["skipped"] == 2


def test_missing_no_follow_flag_fails_closed(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).timestamp()
    _write(tmp_path, "memory", "one.json", {"id": "one", "created_at": now})
    client = _client(monkeypatch, tmp_path)
    monkeypatch.delattr(plugin_api.os, "O_NOFOLLOW", raising=False)
    body = client.get("/api/plugins/pending-queue-monitor/overview").json()
    assert body["totals"]["total"] == 0
    assert body["skipped"] == 1
