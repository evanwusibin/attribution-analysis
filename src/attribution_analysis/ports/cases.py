"""Case 聚合的持久化边界；应用层不依赖具体数据库结构。"""

from __future__ import annotations

from typing import Protocol

from attribution_analysis.application.runtime_logs import RuntimeLog
from attribution_analysis.domain.core import AttributionCase, TaskStatus


class CaseRepository(Protocol):
    """保存和读取完整 Case 聚合的最小端口。"""

    def find_by_idempotency(
        self,
        subject_id: str,
        conversation_id: str,
        input_fingerprint: str,
        idempotency_key: str,
    ) -> AttributionCase | None:
        """按主体边界查询已提交的幂等请求。"""
        ...

    def get(self, case_id: str, subject_id: str) -> AttributionCase | None:
        """按主体读取 Case；不存在或越权时返回 None。"""
        ...

    def list(self, subject_id: str, conversation_id: str | None = None) -> tuple[AttributionCase, ...]:
        """按主体列出 Case。"""
        ...

    def save(self, case: AttributionCase) -> None:
        """以一个可提交聚合快照保存 Case。"""
        ...

    def logs(self, case_id: str, subject_id: str) -> tuple[RuntimeLog, ...]:
        """读取 Case 生命周期日志。"""
        ...

    def register_follow_up(self, case_id: str, idempotency_key: str) -> bool:
        """登记追问幂等键；首次登记返回 True。"""
        ...

    def append_log(self, case_id: str, event: str, task_status: TaskStatus) -> None:
        """追加一个去敏生命周期事件。"""
        ...

    def discard(self, case_id: str) -> None:
        """回滚未提交的 Case 聚合及其审计记录。"""
        ...
