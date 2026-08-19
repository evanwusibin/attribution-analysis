from uuid import uuid4

from fastapi.testclient import TestClient

from attribution_analysis.app import app


client = TestClient(app)


def headers(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key, "X-Subject-Id": "follow-up-contract-user"}


_ACTIVE = {"created", "validating", "planning", "executing", "synthesizing", "cancelling"}


def wait_completion(case_id: str, *, timeout_ticks: int = 100) -> dict:
    """轮询 Case 直到进入终态（后台任务在 TestClient 下异步执行）。"""
    case = {}
    for _ in range(timeout_ticks):
        resp = client.get(f"/api/v1/cases/{case_id}", headers={"X-Subject-Id": "follow-up-contract-user"})
        assert resp.status_code == 200
        case = resp.json()["data"]
        if case["status"] not in _ACTIVE:
            return case
    case["timeout"] = True
    return case


def test_scenario_follow_up_refreshes_every_case_projection() -> None:
    """Contract: supported scenario cases accept a follow-up and expose a second complete projection."""
    scenarios = (
        ("E1", "客户商机丢单，报价竞争力与跟进节奏存在分歧。"),
        ("E2", "华东区本月业绩未达标，线索转化与回款周期是否为主要影响因素？"),
        ("S1", "电池包SOC异常，SOH只有70%，请给出诊断路径。"),
        ("S2", "CL-001 索赔单的工时费与保修资格是否合规？"),
    )

    for scenario, question in scenarios:
        created = client.post(
            "/api/v1/cases",
            json={"conversation_id": uuid4().hex, "scenario_hint": scenario, "question": question},
            headers=headers(uuid4().hex),
        )
        assert created.status_code == 202, created.text
        case_id = created.json()["data"]["case_id"]
        wait_completion(case_id)

        follow_up = client.post(
            f"/api/v1/cases/{case_id}/follow-ups",
            json={"question": f"针对{scenario}补充证据后，请重新评估归因分歧。"},
            headers=headers(uuid4().hex),
        )
        assert follow_up.status_code == 202, follow_up.text
        waited = wait_completion(case_id)
        assert waited["plan_version"] == 2
        assert waited["result_version"] == 2

        case = client.get(f"/api/v1/cases/{case_id}", headers={"X-Subject-Id": "follow-up-contract-user"})
        executions = client.get(f"/api/v1/cases/{case_id}/executions", headers={"X-Subject-Id": "follow-up-contract-user"})
        results = client.get(f"/api/v1/cases/{case_id}/results", headers={"X-Subject-Id": "follow-up-contract-user"})
        assert case.status_code == executions.status_code == results.status_code == 200
        assert case.json()["data"]["status"] == "completed"
        assert len(results.json()["data"]) == 2
        assert {item["plan_id"] for item in executions.json()["data"]}
