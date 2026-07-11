"""FastAPI route tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

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
  challenges:
    path: ./challenges
"""

LEXSHIELD_YAML_WITH_PROXY = LEXSHIELD_YAML + """\
  proxy:
    enabled: true
    upstreams:
      health_check:
        url: http://upstream.test/tools/health_check
        timeoutMs: 2000
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
def shield_with_proxy(tmp_path: Path) -> Shield:
    shutil.copy(PACKS_DIR / "policy.yaml", tmp_path / "policy.yaml")
    shutil.copy(PACKS_DIR / "rules.yaml", tmp_path / "rules.yaml")
    (tmp_path / "lexshield.yaml").write_text(LEXSHIELD_YAML_WITH_PROXY, encoding="utf-8")
    return Shield.from_config(tmp_path / "lexshield.yaml")


@pytest.fixture
def client(shield: Shield) -> TestClient:
    return TestClient(create_app(shield))


@pytest.fixture
def proxy_client(shield_with_proxy: Shield) -> TestClient:
    return TestClient(create_app(shield_with_proxy))


def _evaluate_body(
    *,
    tool: str,
    arguments: dict | None = None,
    environment: str = "production",
    request_id: str | None = None,
) -> dict:
    body = {
        "shieldId": "local",
        "caller": {"id": "agent-1", "type": "agent"},
        "tool": {"name": tool},
        "arguments": arguments or {},
        "context": {"environment": environment},
    }
    if request_id is not None:
        body["id"] = request_id
    return body


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


@respx.mock
def test_execute_allow_forwards_upstream_and_records_outcome(
    proxy_client: TestClient,
    shield_with_proxy: Shield,
) -> None:
    upstream_payload = {"status": "ok", "latencyMs": 12}
    route = respx.post("http://upstream.test/tools/health_check").mock(
        return_value=Response(200, json=upstream_payload)
    )

    response = proxy_client.post(
        "/v1/shields/local/execute",
        json=_evaluate_body(tool="health_check", environment="staging"),
        headers={"X-Request-Id": "req-exec-1"},
    )

    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == "req-exec-1"
    body = response.json()
    assert body["verdict"]["decision"] == "ALLOW"
    assert body["result"] == upstream_payload
    assert route.called
    assert route.calls[0].request.headers["X-LexShield-Verdict"] == "ALLOW"

    traces = shield_with_proxy.trace_sink.read_all()
    assert len(traces) == 1
    assert traces[0]["outcome"] == "EXECUTED"
    assert "outcomeAt" in traces[0]


def test_traces_list_after_evaluate(client: TestClient) -> None:
    evaluate_response = client.post(
        "/v1/shields/local/evaluate",
        json=_evaluate_body(tool="health_check", environment="staging"),
    )
    assert evaluate_response.status_code == 200
    request_id = evaluate_response.json()["requestId"]

    traces_response = client.get("/v1/traces", params={"tool": "health_check"})
    assert traces_response.status_code == 200
    payload = traces_response.json()
    assert payload["total"] == 1
    assert len(payload["traces"]) == 1
    assert payload["traces"][0]["id"] == request_id
    assert payload["traces"][0]["verdict"]["decision"] == "ALLOW"


def test_challenge_resolve_flow(client: TestClient) -> None:
    evaluate_response = client.post(
        "/v1/shields/local/evaluate",
        json=_evaluate_body(tool="delete_resource"),
    )
    assert evaluate_response.status_code == 200
    verdict = evaluate_response.json()
    assert verdict["decision"] == "CHALLENGE"
    challenge_id = verdict["challengeId"]
    assert challenge_id is not None

    list_response = client.get("/v1/challenges")
    assert list_response.status_code == 200
    open_challenges = list_response.json()["challenges"]
    assert len(open_challenges) == 1
    assert open_challenges[0]["id"] == challenge_id
    assert open_challenges[0]["status"] == "open"

    resolve_response = client.post(
        f"/v1/challenges/{challenge_id}/resolve",
        json={"decision": "approve", "actor": "reviewer-1"},
    )
    assert resolve_response.status_code == 200
    resolved = resolve_response.json()
    assert resolved["status"] == "approved"
    assert resolved["actor"] == "reviewer-1"

    list_after = client.get("/v1/challenges")
    assert list_after.json()["challenges"] == []


def test_policy_reload_failure_keeps_old_policy(
    client: TestClient,
    shield_config_dir: Path,
) -> None:
    policy_path = shield_config_dir / "policy.yaml"
    original_policy = policy_path.read_text(encoding="utf-8")

    policy_path.write_text("not: valid: yaml: [[", encoding="utf-8")
    reload_response = client.post("/v1/shields/local/policy/reload")
    assert reload_response.status_code == 200
    assert reload_response.json()["status"] == "failed"

    evaluate_response = client.post(
        "/v1/shields/local/evaluate",
        json=_evaluate_body(tool="health_check", environment="staging"),
    )
    assert evaluate_response.status_code == 200
    assert evaluate_response.json()["decision"] == "ALLOW"
    assert evaluate_response.json()["matchedRuleId"] == "allow-health"

    policy_path.write_text(original_policy, encoding="utf-8")


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
