"""MySQL 业务数据适配器：只执行项目批准的查询，不接受用户 SQL。"""
from __future__ import annotations

from typing import Protocol

from attribution_analysis.ports.evidence import NL2SQLPort, QueryResult


class SQLConnection(Protocol):
    def execute(self, sql: str, params: list | None = None):
        """执行 SQL 并返回带 description 的结果集（协议契约）。"""
        ...


class MySQLNL2SQLAdapter(NL2SQLPort):
    """将演示问题映射到 MySQL 白名单查询，保留真实数据来源。"""

    SOURCE_REF = "mysql.attribution.business.v1"

    def __init__(self, connection: SQLConnection) -> None:
        """绑定 MySQL 业务连接。"""
        self.connection = connection

    def query(self, question: str) -> QueryResult:
        """按关键词映射到 MySQL 白名单查询并保留真实来源。"""
        if any(word in question for word in ("库存", "缺货")):
            sql = "SELECT sku, available_qty, requested_qty FROM inventory"
        else:
            sql = "SELECT order_id, promised_date, delivered_date, delay_days FROM orders"
        result = self.connection.execute(sql)
        columns = tuple(column[0] for column in result.description)
        rows = tuple(dict(zip(columns, row)) for row in result.fetchall())
        return QueryResult(columns, rows, sql, self.SOURCE_REF, "FACT")
