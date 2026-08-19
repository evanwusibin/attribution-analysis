from uuid import uuid4

from fastapi.testclient import TestClient

from attribution_analysis.app import app


client = TestClient(app)


def headers(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key, "X-Subject-Id": "test-user"}


_ACTIVE = {"created", "validating", "planning", "executing", "synthesizing", "cancelling"}


def wait_completion(case_id: str, *, timeout_ticks: int = 100) -> dict:
    """轮询 Case 直到进入终态（后台任务在 TestClient 下异步执行）。

    返回终态 Case 摘要；超时则返回最后一次可见摘要并附加 timeout 标记。
    """
    case = {}
    for _ in range(timeout_ticks):
        resp = client.get(f"/api/v1/cases/{case_id}", headers={"X-Subject-Id": "test-user"})
        assert resp.status_code == 200
        case = resp.json()["data"]
        if case["status"] not in _ACTIVE:
            return case
        client.get(f"/api/v1/cases/{case_id}/task", headers={"X-Subject-Id": "test-user"})
    case["timeout"] = True
    return case


def test_case_creation_completes_evidence_to_result_flow() -> None:
    """Contract: a valid request produces a traceable result with evidence."""
    response = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析订单延迟原因"},
        headers=headers(uuid4().hex),
    )

    assert response.status_code == 202
    case = wait_completion(response.json()["data"]["case_id"])
    assert case["status"] == "completed"
    assert case["evidence_count"] == 2
    result = client.get(f"/api/v1/cases/{case['case_id']}/results", headers={"X-Subject-Id": "test-user"})
    evidence = client.get(f"/api/v1/cases/{case['case_id']}/evidence", headers={"X-Subject-Id": "test-user"})

    assert result.status_code == 200
    assert result.json()["data"][0]["evidence_ids"] == [item["evidence_id"] for item in evidence.json()["data"]]
    assert result.json()["data"][0]["manual_review_required"] is True
    executions = client.get(f"/api/v1/cases/{case['case_id']}/executions", headers={"X-Subject-Id": "test-user"})
    details = {item["tool_name"]: item["details"] for item in executions.json()["data"]}
    assert details["query_business_data"]["sql"]
    assert details["query_business_data"]["rows"]
    assert details["query_knowledge_base"]["hits"]


def test_e2_case_persists_scenario_evidence_and_conclusion() -> None:
    """Contract: an E2 workbench request keeps its business diagnosis and all evidence in one Case."""
    response = client.post(
        "/api/v1/cases",
        json={
            "conversation_id": uuid4().hex,
            "scenario_hint": "E2",
            "question": "华东区本月业绩未达标，线索转化与回款周期是否为主要影响因素？",
        },
        headers=headers(uuid4().hex),
    )

    assert response.status_code == 202
    case = response.json()["data"]
    evidence = client.get(f"/api/v1/cases/{case['case_id']}/evidence", headers={"X-Subject-Id": "test-user"})
    result = client.get(f"/api/v1/cases/{case['case_id']}/results", headers={"X-Subject-Id": "test-user"})

    assert case["scenario_hint"] == "E2"
    assert any("本月业绩" in item["content_summary"] for item in evidence.json()["data"])
    assert "达成率" in result.json()["data"][-1]["conclusion"]
    # 场景结果应引用至少一条证据
    assert len(result.json()["data"][-1]["evidence_ids"]) >= 1


def test_s1_case_persists_battery_diagnosis_and_review_boundary() -> None:
    """Contract: an S1 workbench request persists the battery candidate and missing evidence in its Case."""
    response = client.post(
        "/api/v1/cases",
        json={
            "conversation_id": uuid4().hex,
            "scenario_hint": "S1",
            "question": "电池包SOC异常，SOH只有70%，请给出诊断路径。",
        },
        headers=headers(uuid4().hex),
    )

    assert response.status_code == 202
    case = response.json()["data"]
    evidence = client.get(f"/api/v1/cases/{case['case_id']}/evidence", headers={"X-Subject-Id": "test-user"})
    result = client.get(f"/api/v1/cases/{case['case_id']}/results", headers={"X-Subject-Id": "test-user"})

    assert case["scenario_hint"] == "S1"
    assert any(item["source_class"] == "MISSING" for item in evidence.json()["data"])
    assert "候选根因" in result.json()["data"][-1]["conclusion"]
    assert result.json()["data"][-1]["manual_review_required"] is True


def test_s1_case_persists_battery_diagnosis_and_review_boundary() -> None:
    """Contract: an S1 workbench request persists the battery candidate and missing evidence in its Case."""
    response = client.post(
        "/api/v1/cases",
        json={
            "conversation_id": uuid4().hex,
            "scenario_hint": "S1",
            "question": "电池包SOC异常，SOH只有70%，请给出诊断路径。",
        },
        headers=headers(uuid4().hex),
    )

    assert response.status_code == 202
    case = response.json()["data"]
    evidence = client.get(f"/api/v1/cases/{case['case_id']}/evidence", headers={"X-Subject-Id": "test-user"})
    result = client.get(f"/api/v1/cases/{case['case_id']}/results", headers={"X-Subject-Id": "test-user"})

    assert case["scenario_hint"] == "S1"
    assert any(item["source_class"] == "MISSING" for item in evidence.json()["data"])
    assert "候选根因" in result.json()["data"][0]["conclusion"]
    assert result.json()["data"][0]["manual_review_required"] is True


def test_duplicate_request_reuses_single_case() -> None:
    """Contract: the same idempotency scope cannot execute a second case."""
    request = {"conversation_id": uuid4().hex, "question": "分析客户流失原因"}
    key = uuid4().hex
    first = client.post("/api/v1/cases", json=request, headers=headers(key))
    first_waited = wait_completion(first.json()["data"]["case_id"])
    second = client.post("/api/v1/cases", json=request, headers=headers(key))
    second_waited = wait_completion(second.json()["data"]["case_id"])

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["reused"] is True
    assert second.json()["data"]["case_id"] == first.json()["data"]["case_id"]
    assert second_waited["evidence_count"] == first_waited["evidence_count"]
    assert second_waited["evidence_count"] >= 2


def test_follow_up_creates_new_result_version_and_keeps_evidence() -> None:
    """Contract: follow-up creates a new version without deleting prior evidence."""
    created = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析报价竞争力问题"},
        headers=headers(uuid4().hex),
    )
    case_id = created.json()["data"]["case_id"]
    wait_completion(case_id)
    follow_up = client.post(
        f"/api/v1/cases/{case_id}/follow-ups",
        json={"question": "补充客户分层后重新分析"},
        headers=headers(uuid4().hex),
    )
    waited = wait_completion(case_id)

    assert follow_up.status_code == 202
    assert waited["result_version"] == 2
    assert waited["evidence_count"] == 4


def test_cancelled_case_remains_readable() -> None:
    """Contract: cancellation is idempotent and never hides existing evidence."""
    created = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析库存不足原因"},
        headers=headers(uuid4().hex),
    )
    case_id = created.json()["data"]["case_id"]
    cancelled = client.post(f"/api/v1/cases/{case_id}/cancel", headers={"X-Subject-Id": "test-user"})
    evidence = client.get(f"/api/v1/cases/{case_id}/evidence", headers={"X-Subject-Id": "test-user"})

    assert cancelled.status_code == 202
    assert cancelled.json()["data"]["status"] == "completed"
    assert len(evidence.json()["data"]) == 2




def test_case_rejects_short_question_before_execution() -> None:
    """Contract: invalid input cannot create a plan or result."""
    response = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "短"},
        headers=headers(uuid4().hex),
    )

    assert response.status_code == 422


def test_case_rejects_unknown_scenario_before_execution() -> None:
    """Contract: only registered workbench scenarios may start a Case."""
    response = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "scenario_hint": "E9", "question": "请分析一个未知场景问题"},
        headers=headers(uuid4().hex),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "scenario must be one of E1-E5 or S1-S8"



def test_execution_projection_links_tool_status_to_evidence() -> None:
    """Contract: UI projections read real tool outcomes rather than inferring them from evidence count."""
    created = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析订单履约延迟"},
        headers=headers(uuid4().hex),
    )
    case_id = created.json()["data"]["case_id"]

    response = client.get(f"/api/v1/cases/{case_id}/executions", headers={"X-Subject-Id": "test-user"})

    assert response.status_code == 200
    executions = response.json()["data"]
    assert {item["tool_name"] for item in executions} >= {"query_business_data", "query_knowledge_base"}
    assert all(item["status"] in {"succeeded", "failed", "timeout"} for item in executions)
    assert all(isinstance(item["duration_ms"], int) and item["duration_ms"] >= 0 for item in executions)
    assert all("evidence_ids" in item for item in executions)


def test_plan_query_exposes_version_and_step_budget() -> None:
    """Contract: a stored plan is readable without exposing unexecuted results."""
    created = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析订单履约延迟"},
        headers=headers(uuid4().hex),
    )
    case_id = created.json()["data"]["case_id"]

    response = client.get(
        f"/api/v1/cases/{case_id}/plans/1",
        headers={"X-Subject-Id": "test-user"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["version_no"] == 1
    assert response.json()["data"]["max_steps"] == 8
    assert "evidence" not in response.json()["data"]


def test_case_task_projection_and_logs_are_subject_scoped() -> None:
    """Contract: callers can read derived task progress and redacted lifecycle logs only for their Case."""
    created = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "客户电话 13800138000 反映交付延迟"},
        headers=headers(uuid4().hex),
    )
    case_id = created.json()["data"]["case_id"]

    task = client.get(f"/api/v1/cases/{case_id}/task", headers={"X-Subject-Id": "test-user"})
    logs = client.get(f"/api/v1/cases/{case_id}/task-logs", headers={"X-Subject-Id": "test-user"})

    assert task.json()["data"]["status"] == "success"
    assert [entry["event"] for entry in logs.json()["data"]] == ["case.queued", "case.completed"]
    assert "13800138000" not in str(logs.json())


    """Contract: a subject cannot read another subject's case."""
    created = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析库存不足原因"},
        headers={"Idempotency-Key": uuid4().hex, "X-Subject-Id": "owner"},
    )
    case_id = created.json()["data"]["case_id"]

    response = client.get(f"/api/v1/cases/{case_id}", headers={"X-Subject-Id": "other"})

    assert response.status_code == 404


def test_workbench_is_served_from_the_same_origin_as_the_api() -> None:
    """Contract: the browser workbench is served by the API origin and can call protected Case routes."""
    response = client.get("/workbench/")

    assert response.status_code == 200
    assert "经营归因分析" in response.text
    assert client.get("/workbench/app.js").status_code == 200
