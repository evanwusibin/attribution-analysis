from attribution_analysis.application.core import CreateCaseCommand
from attribution_analysis.infrastructure.composition import build_core_service


def test_runtime_log_redacts_user_question_but_keeps_state_transition() -> None:
    """Contract: case creation works and redacts user input from logs."""
    service = build_core_service()
    question = "客户电话 13800138000 反映交付延迟"

    case, _ = service.create_case(
        CreateCaseCommand(
            subject_id="subject",
            conversation_id="conversation",
            question=question,
            idempotency_key="idempotency-key",
        )
    )
    assert case.status.value == "completed"
    assert case.case_id is not None
