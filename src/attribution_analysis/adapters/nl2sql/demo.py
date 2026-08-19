"""NL2SQL 适配器的本地实现：固定白名单查询，不执行用户任意 SQL。"""
from duckdb import DuckDBPyConnection

from attribution_analysis.ports.evidence import NL2SQLPort, QueryResult


class DemoNL2SQLAdapter(NL2SQLPort):
    def __init__(self, connection: DuckDBPyConnection) -> None:
        """绑定演示数据库连接。"""
        self.connection = connection

    def query(self, question: str) -> QueryResult:
        """按关键词映射到固定白名单 SQL，不执行用户任意 SQL。"""
        if any(word in question for word in ("库存", "缺货")):
            sql = "SELECT sku, available_qty, requested_qty FROM inventory"
        else:
            sql = "SELECT order_id, promised_date, delivered_date, delay_days FROM orders"
        result = self.connection.execute(sql)
        rows = tuple(dict(zip([column[0] for column in result.description], row)) for row in result.fetchall())
        return QueryResult(tuple(column[0] for column in result.description), rows, sql, "demo.duckdb.business.v1")
