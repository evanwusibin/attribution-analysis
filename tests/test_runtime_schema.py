from pathlib import Path


SCHEMA = (
    Path(__file__).resolve().parents[1] / "deploy" / "postgres" / "002_runtime_schema.sql"
).read_text(encoding="utf-8")


def test_runtime_schema_persists_only_attribution_owned_state() -> None:
    """Contract: the runtime schema owns Case audit data, never external DMS/CRM records."""
    assert "runtime.attribution_cases" in SCHEMA
    assert "runtime.case_state_transitions" in SCHEMA
    assert "runtime.tool_executions" in SCHEMA
    assert "runtime.evidence" in SCHEMA
    assert "runtime.attribution_results" in SCHEMA
    assert "dms" not in SCHEMA.lower()
    assert "crm" not in SCHEMA.lower()


def test_runtime_schema_protects_idempotency_and_append_only_evidence_order() -> None:
    """Contract: duplicate submissions and evidence ordering are constrained by the database."""
    assert "UNIQUE (subject_id, conversation_id, input_fingerprint, idempotency_key)" in SCHEMA
    assert "UNIQUE (case_id, sequence_no)" in SCHEMA
    assert "UNIQUE (case_id, version_no)" in SCHEMA


def test_runtime_schema_requires_explicit_source_class_and_result_citations() -> None:
    """Contract: a persisted result retains source grading and direct evidence references."""
    assert "source_class IN ('FACT', 'MOCK', 'MISSING')" in SCHEMA
    assert "source_version_id TEXT NOT NULL" in SCHEMA
    assert "runtime.result_evidence_refs" in SCHEMA
    assert "manual_review_required BOOLEAN NOT NULL" in SCHEMA
