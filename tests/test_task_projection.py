from attribution_analysis.domain.core import CaseStatus, TaskStatus, task_status_from_case


def test_task_status_is_a_read_only_projection_of_case_status() -> None:
    """Contract: platform task state never becomes a second writable lifecycle."""
    expected = {
        CaseStatus.CREATED: TaskStatus.QUEUED,
        CaseStatus.VALIDATING: TaskStatus.QUEUED,
        CaseStatus.PLANNING: TaskStatus.QUEUED,
        CaseStatus.EXECUTING: TaskStatus.RUNNING,
        CaseStatus.SYNTHESIZING: TaskStatus.RUNNING,
        CaseStatus.CANCELLING: TaskStatus.RUNNING,
        CaseStatus.COMPLETED: TaskStatus.SUCCESS,
        CaseStatus.NEEDS_INPUT: TaskStatus.SUCCESS,
        CaseStatus.FAILED: TaskStatus.FAILED,
        CaseStatus.REJECTED: TaskStatus.FAILED,
        CaseStatus.CANCELLED: TaskStatus.CANCELLED,
    }

    assert {case: task_status_from_case(case) for case in CaseStatus} == expected
