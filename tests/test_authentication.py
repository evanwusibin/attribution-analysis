from uuid import uuid4

from fastapi.testclient import TestClient

from attribution_analysis.api import authentication
from attribution_analysis.api import cases
from attribution_analysis.app import app
from attribution_analysis.config.settings import Settings


client = TestClient(app)


def test_local_runtime_keeps_explicit_developer_subject_override() -> None:
    """Contract: automated test runs may use an explicit subject header (test env only)."""
    response = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析本地验证任务"},
        headers={"Idempotency-Key": uuid4().hex, "X-Subject-Id": "local-test-user"},
    )

    assert response.status_code == 202


def test_local_and_docker_runtimes_reject_forged_subject_header(monkeypatch) -> None:
    """Contract: X-Subject-Id never authenticates outside the test environment (P0-1)."""
    for env in ("local", "docker"):
        monkeypatch.setattr(authentication, "settings", Settings(environment=env))
        response = client.post(
            "/api/v1/cases",
            json={"conversation_id": uuid4().hex, "question": "伪造身份请求"},
            headers={"Idempotency-Key": uuid4().hex, "X-Subject-Id": "forged-user"},
        )
        assert response.status_code == 401, f"environment={env} must reject forged subject headers"
    monkeypatch.setattr(authentication, "settings", Settings(environment="test"))


def test_claim_compliance_endpoints_require_authentication() -> None:
    """Contract: claim-compliance routes reject anonymous access (P0-2)."""
    anonymous = TestClient(app)

    analyze = anonymous.post(
        "/api/claim-compliance/analyze",
        json={"question": "CL-001 索赔单是否应该赔付", "claim_id": "CL-001"},
    )
    claim = anonymous.get("/api/claim-compliance/claim/CL-001")

    assert analyze.status_code == 401
    assert claim.status_code == 401


def test_non_local_runtime_rejects_missing_bearer_token(monkeypatch) -> None:
    """Contract: deployment runtimes never default requests to a forgeable subject header."""
    monkeypatch.setattr(authentication, "settings", Settings(environment="staging"))

    response = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析验收环境任务"},
        headers={"Idempotency-Key": uuid4().hex, "X-Subject-Id": "forged-user"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token is required"


def test_non_local_runtime_never_treats_raw_token_as_identity(monkeypatch) -> None:
    """Contract: a token is denied until a configured verifier can validate its issuer and claims."""
    monkeypatch.setattr(authentication, "settings", Settings(environment="staging"))

    response = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析验收环境任务"},
        headers={"Authorization": "Bearer unverified-token", "Idempotency-Key": uuid4().hex},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Token verifier is not configured"


def test_local_demo_and_auth_storage_have_independent_database_boundaries() -> None:
    """Contract: demo business queries remain available when auth storage is initialized."""
    repository = authentication.auth_repository()
    business_connection = cases.service.evidence_toolset.nl2sql.connection

    assert repository.connection is not business_connection
    assert repository.connection.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0] >= 1
    assert business_connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] >= 1


def test_local_registration_and_password_reset_enable_subsequent_login() -> None:
    """Contract: a locally registered account can reset its password and authenticate with the new credential."""
    username = f"analyst-{uuid4().hex[:10]}"
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "display_name": "新分析员", "password": "initial-pass-123"},
    )
    assert response.status_code == 201

    reset = client.post(
        "/api/v1/auth/forgot-password",
        json={"username": username, "new_password": "updated-pass-456"},
    )
    assert reset.status_code == 200

    login = client.post("/api/v1/auth/login", json={"username": username, "password": "updated-pass-456"})
    assert login.status_code == 200
    assert login.json()["data"]["username"] == username


def test_login_session_protects_and_enables_both_demo_scenarios() -> None:
    """Contract: a valid login cookie can run the E2 and S1 scenario APIs without a forgeable header."""
    client = TestClient(app)

    login = client.post("/api/v1/auth/login", json={"username": "analyst", "password": "analyst123"})
    assert login.status_code == 200
    assert "attribution_session" in login.cookies

    presales = client.post(
        "/api/v1/presales/diagnostics",
        json={"question": "华东区本月业绩未达标为什么"},
    )
    after_sales = client.post(
        "/api/v1/after-sales/diagnostics",
        json={"question": "电池包SOC异常，SOH只有70%", "vin": "LSGAB52R7DF000005"},
    )

    assert presales.status_code == 200
    assert presales.json()["data"]["scenario"] == "E2"
    assert after_sales.status_code == 200
    assert after_sales.json()["data"]["domain"] == "battery_pack"


def test_scenario_apis_reject_requests_without_login_or_test_override() -> None:
    """Contract: scenario endpoints require a session when no explicit test subject is supplied."""
    client = TestClient(app)

    response = client.post("/api/v1/presales/diagnostics", json={"question": "华东区本月业绩未达标为什么"})

    assert response.status_code == 401



def test_session_creation_is_database_dialect_neutral() -> None:
    """Contract: session persistence passes an explicit expiry value instead of database-specific interval SQL."""
    class RecordingConnection:
        def __init__(self) -> None:
            self.statement = ""
            self.params = ()

        def execute(self, statement, params):
            self.statement = statement
            self.params = params

    repository = authentication.AuthRepository.__new__(authentication.AuthRepository)
    repository.connection = RecordingConnection()

    token = repository.create_session("subject-1")

    assert token
    assert "INTERVAL" not in repository.connection.statement
    assert repository.connection.statement.count("?") == 4
    assert repository.connection.params[2] == "subject-1"
    assert repository.connection.params[3] > repository.connection.params[3].replace(hour=0, minute=0, second=0, microsecond=0)


def test_logout_revokes_the_server_session() -> None:
    """Contract: logging out invalidates the session even if its token is replayed."""
    session_client = TestClient(app)
    login = session_client.post("/api/v1/auth/login", json={"username": "analyst", "password": "analyst123"})
    assert login.status_code == 200
    token = session_client.cookies.get("attribution_session")

    logout = session_client.post("/api/v1/auth/logout")
    replay = TestClient(app).get("/api/v1/auth/me", cookies={"attribution_session": token})

    assert logout.status_code == 200
    assert replay.status_code == 401
