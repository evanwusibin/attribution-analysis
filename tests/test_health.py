from fastapi.testclient import TestClient

from attribution_analysis.app import app


def test_health_contract_reports_service_readiness() -> None:
    """Contract: a local client can verify that the Slice 0 service is ready."""
    response = TestClient(app).get("/health")

    assert response.status_code == 200


def test_business_routes_reject_unsupported_methods() -> None:
    """Contract: the Case resource rejects methods it does not declare (GET collection is now a valid route)."""
    response = TestClient(app).put("/api/v1/cases")

    assert response.status_code == 405
