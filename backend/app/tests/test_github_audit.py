import base64
import json
from datetime import datetime
from types import SimpleNamespace

from app.github_audit import (
    get_audit_repository_url,
    normalize_repo_full_name,
    publish_audit_block_to_github,
)


def test_normalize_github_repo_formats(monkeypatch):
    assert normalize_repo_full_name("git@github.com:atcasanova/palpites-copa-2026-auditoria.git") == (
        "atcasanova/palpites-copa-2026-auditoria"
    )
    assert normalize_repo_full_name("https://github.com/atcasanova/palpites-copa-2026-auditoria.git") == (
        "atcasanova/palpites-copa-2026-auditoria"
    )
    assert normalize_repo_full_name("atcasanova/palpites-copa-2026-auditoria") == (
        "atcasanova/palpites-copa-2026-auditoria"
    )
    assert normalize_repo_full_name("https://example.com/invalid.git") == ""

    monkeypatch.setenv("GITHUB_REPO", "git@github.com:atcasanova/palpites-copa-2026-auditoria.git")
    assert get_audit_repository_url() == "https://github.com/atcasanova/palpites-copa-2026-auditoria"


def test_publish_audit_block_to_github_creates_json_file(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, status_code, data=None):
            self.status_code = status_code
            self._data = data or {}

        def json(self):
            return self._data

        def raise_for_status(self):
            assert self.status_code < 400

    def fake_get(url, headers, timeout):
        captured["get_url"] = url
        captured["headers"] = headers
        captured["get_timeout"] = timeout
        return FakeResponse(404)

    def fake_put(url, headers, json, timeout):
        captured["put_url"] = url
        captured["put_headers"] = headers
        captured["body"] = json
        captured["put_timeout"] = timeout
        return FakeResponse(
            201,
            {
                "content": {"html_url": "https://github.com/atcasanova/repo/blob/main/blocks/file.json"},
                "commit": {"html_url": "https://github.com/atcasanova/repo/commit/abc"},
            },
        )

    monkeypatch.setenv("GITHUB_AUDIT", "true")
    monkeypatch.setenv("GITHUB_REPO", "git@github.com:atcasanova/palpites-copa-2026-auditoria.git")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr("app.github_audit.requests.get", fake_get)
    monkeypatch.setattr("app.github_audit.requests.put", fake_put)

    block = SimpleNamespace(
        block_number=7,
        match_id=42,
        previous_hash="0" * 64,
        hash="a" * 64,
        created_at=datetime(2026, 6, 1, 12, 0, 0),
        payload=[{"username": "ana", "goals_team1": 2, "goals_team2": 1}],
        match=SimpleNamespace(
            id=42,
            round="Matchday 1",
            stage="Group Stage",
            group_name="A",
            kickoff_time=datetime(2026, 6, 12, 18, 0, 0),
            team1_name="Brasil",
            team2_name="Japao",
        ),
    )

    result = publish_audit_block_to_github(block)

    assert result["published"] is True
    assert result["already_exists"] is False
    assert captured["get_url"].endswith(
        "/repos/atcasanova/palpites-copa-2026-auditoria/contents/blocks/block_000007_match_42.json"
    )
    assert captured["put_url"] == captured["get_url"]
    assert captured["headers"]["Authorization"] == "Bearer test-token"

    decoded = base64.b64decode(captured["body"]["content"]).decode("utf-8")
    document = json.loads(decoded)
    assert document["schema"] == "bolao-copa-2026.audit-block.v1"
    assert document["payload"][0]["username"] == "ana"
    assert document["hash"] == "a" * 64
