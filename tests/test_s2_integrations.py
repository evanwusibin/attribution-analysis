from pathlib import Path

from attribution_analysis.adapters.nl2sql.demo import DemoNL2SQLAdapter
from attribution_analysis.adapters.nl2sql.mysql import MySQLNL2SQLAdapter
from attribution_analysis.adapters.rag.demo import DemoRAGAdapter
from attribution_analysis.adapters.rag.http import HttpRAGAdapter
from attribution_analysis.application.tools.evidence import EvidenceToolset
from attribution_analysis.infrastructure.database.duckdb import open_database


def test_demo_database_and_adapters_form_read_only_evidence_contract(tmp_path: Path) -> None:
    """Contract: a fresh local database supports business and knowledge evidence collection."""
    connection = open_database(tmp_path / "demo.db")
    toolset = EvidenceToolset(DemoRAGAdapter(), DemoNL2SQLAdapter(connection))

    evidence = toolset.collect("分析订单延迟原因")

    assert len(evidence) == 2
    assert evidence[0].source_ref == "demo.duckdb.business.v1"
    assert evidence[1].source_ref == "demo.manual.delivery.v1"
    assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 2
    connection.close()


def test_nl2sql_uses_whitelisted_queries(tmp_path: Path) -> None:
    """Contract: demo NL2SQL maps supported intents to fixed SQL rather than raw input."""
    connection = open_database(tmp_path / "demo.db")
    result = DemoNL2SQLAdapter(connection).query("请执行 DROP TABLE orders")

    assert result.sql == "SELECT order_id, promised_date, delivered_date, delay_days FROM orders"
    assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 2
    connection.close()


def test_mysql_nl2sql_preserves_fact_source_and_whitelist() -> None:
    """Contract: MySQL mode queries only approved tables and marks results as FACT."""
    class Result:
        description = (("order_id",), ("delay_days",))

        def fetchall(self):
            return (("ORD-1", 2),)

    class Connection:
        def __init__(self):
            self.sql = ""

        def execute(self, sql, params=None):
            self.sql = sql
            return Result()

    connection = Connection()
    result = MySQLNL2SQLAdapter(connection).query("分析订单交付延迟")

    assert result.source_class == "FACT"
    assert result.source_ref == "mysql.attribution.business.v1"
    assert result.sql == "SELECT order_id, promised_date, delivered_date, delay_days FROM orders"
    assert "DROP" not in connection.sql
