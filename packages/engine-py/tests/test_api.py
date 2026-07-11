"""FastAPI route tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lexshield.server.app import create_app
from lexshield.shield import Shield

PACKS_DIR = Path(__file__).resolve().parents[3] / "packs" / "baseline-deny"

LEXSHIELD_YAML = """\
version: 1
shield:
  id: local
  name: local-shield
  policy: ./policy.yaml
  classifiers:
    - type: deterministic
      path: ./rules.yaml
  sinks:
    - type: file
      path: ./traces.ndjson
"""


@pytest.fixture
def shield_config_dir(tmp_path: Path) -> Path:
    shutil.copy(PACKS_DIR / "policy.yaml", tmp_path / "policy.yaml")
    shutil.copy(PACKS_DIR / "rules.yaml", tmp_path / "rules.yaml")
    (tmp_path / "lexshield.yaml").write_text(LEXSHIELD_YAML, encoding="utf-8")
    return tmp_path


@pytest.fixture
def shield(shield_config_dir: Path) -> Shield:
    return Shield.from_config(shield_config_dir / "lexshield.yaml")


@pytest.fixture
def client(shield: Shield) -> TestClient:
    return TestClient(create_app(shield))


def _evaluate_body(
    *,
    tool: str,
    arguments: dict | None = None,
) -> dict:
    return {
        "shieldId": "local",
        "caller": {"id": "agent-1", "type": "agent"},
        "tool": {"name": tool},
        "arguments": arguments or {},
        "context": {"environment": "production"},
    }


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_with_shield(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"ready": True}


def test_readyz_without_shield() -> None:
    client = TestClient(create_app(None))
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"ready": False}


def test_evaluate_allow_health(client: TestClient) -> None:
    response = client.post(
        "/v1/shields/local/evaluate",
        json=_evaluate_body(tool="health_check"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "ALLOW"
    assert body["matchedRuleId"] == "allow-health"


def test_evaluate_block_secret(client: TestClient) -> None:
    response = client.post(
        "/v1/shields/local/evaluate",
        json=_evaluate_body(
            tool="send_email",
            arguments={"body": "AKIAIOSFODNN7EXAMPLE"},
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "BLOCK"
    assert body["matchedRuleId"] == "block-secret-exposure"


def test_execute_blocked_returns_403(client: TestClient) -> None:
    response = client.post(
        "/v1/shields/local/execute",
        json=_evaluate_body(
            tool="send_email",
            arguments={"body": "AKIAIOSFODNN7EXAMPLE"},
        ),
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "lexshield_blocked"
    assert detail["verdict"] == "BLOCK"
    assert detail["matched_rule_id"] == "block-secret-exposure"
    assert detail["retryable"] is False


def test_auth_requires_bearer_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEXSHIELD_LOCAL_TOKEN", "test-secret-token")

    unauthenticated = client.post(
        "/v1/shields/local/evaluate",
        json=_evaluate_body(tool="health_check"),
    )
    assert unauthenticated.status_code == 401

    authenticated = client.post(
        "/v1/shields/local/evaluate",
        json=_evaluate_body(tool="health_check"),
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert authenticated.status_code == 200
    assert authenticated.json()["decision"] == "ALLOW"
