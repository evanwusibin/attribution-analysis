import pytest

from attribution_analysis.domain.core import AttributionCase, CaseStatus


def test_state_machine_records_legal_transitions() -> None:
    """Contract: every legal lifecycle change is auditable in order."""
    case = AttributionCase(
        case_id="case_test",
        subject_id="subject_test",
        conversation_id="conversation_test",
        question="分析订单延迟原因",
        scenario_hint=None,
        input_fingerprint="fingerprint",
        idempotency_key="key",
    )

    case.transition(CaseStatus.VALIDATING)
    case.transition(CaseStatus.PLANNING)

    assert [(item.from_status, item.to_status) for item in case.transitions] == [
        (CaseStatus.CREATED, CaseStatus.VALIDATING),
        (CaseStatus.VALIDATING, CaseStatus.PLANNING),
    ]


def test_state_machine_rejects_illegal_transition() -> None:
    """Contract: a terminal rejected case cannot be revived by an illegal jump."""
    case = AttributionCase(
        case_id="case_test",
        subject_id="subject_test",
        conversation_id="conversation_test",
        question="分析订单延迟原因",
        scenario_hint=None,
        input_fingerprint="fingerprint",
        idempotency_key="key",
    )
    case.transition(CaseStatus.VALIDATING)
    case.transition(CaseStatus.REJECTED)

    with pytest.raises(ValueError, match="illegal case transition"):
        case.transition(CaseStatus.PLANNING)

    assert case.status is CaseStatus.REJECTED
    assert len(case.transitions) == 2
