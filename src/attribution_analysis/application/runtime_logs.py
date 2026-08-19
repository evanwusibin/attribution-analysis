"""运行观测记录：只承载生命周期事实，不记录业务输入或凭据。"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from attribution_analysis.domain.core import TaskStatus, utc_now


@dataclass(frozen=True)
class RuntimeLog:
    case_id: str
    event: str
    task_status: str
    message: str
    occurred_at: str


def record_runtime_event(
    records: list[RuntimeLog],
    *,
    case_id: str,
    event: str,
    task_status: TaskStatus,
) -> None:
    """记录一次去敏的运行事件（如 queued/completed）到内存日志流，并输出 loguru。

    消息只包含生命周期事实，不包含用户问题、证据内容或凭据。
    """
    message = f"case lifecycle event={event} task_status={task_status.value}"
    record = RuntimeLog(
        case_id=case_id,
        event=event,
        task_status=task_status.value,
        message=message,
        occurred_at=utc_now(),
    )
    records.append(record)
    logger.bind(case_id=case_id, event=event, task_status=task_status.value).info(message)
