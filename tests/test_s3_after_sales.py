"""S3 售后共享证据底座契约测试。"""
from pathlib import Path

from attribution_analysis.adapters.after_sales.demo import DemoAfterSalesAdapter
from attribution_analysis.infrastructure.database.duckdb import (
    AFTER_SALES_SEED,
    open_database,
)


def test_seed_42_is_reproducible(tmp_path: Path) -> None:
    """Contract: the same seed=42 fixture always initializes identical rows."""
    first = open_database(tmp_path / "a.db")
    second = open_database(tmp_path / "b.db")

    counts_a = {table: first.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in AFTER_SALES_SEED}
    counts_b = {table: second.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in AFTER_SALES_SEED}

    assert counts_a == counts_b
    assert counts_a["vehicles"] == 6
    assert counts_a["claims"] == 7
    assert counts_a["battery_health"] == 6
    first.close()
    second.close()


def test_mock_data_is_isolated_from_fact_views(tmp_path: Path) -> None:
    """Contract: simulated fixtures are MOCK; manual/FACT rules are explicitly tagged."""
    connection = open_database(tmp_path / "demo.db")
    adapter = DemoAfterSalesAdapter(connection)

    vehicle = adapter.get_vehicle("LSGAB52R7DF000001")
    assert vehicle.source_class == "MOCK"
    assert vehicle.source_ref == "demo.duckdb.after_sales.v1"

    manual = adapter.get_warranty_manual("P-201", "T5轻卡")
    assert manual.source_class == "MOCK"
    assert manual.rule_version == "manual.t5.v1"

    missing = adapter.get_vehicle("NO-SUCH-VIN")
    assert missing is None
    connection.close()


def test_external_key_coexists_across_read_times(tmp_path: Path) -> None:
    """Contract: the same VIN key resolves consistently across separate reads."""
    connection = open_database(tmp_path / "demo.db")
    adapter = DemoAfterSalesAdapter(connection)

    first_vehicle = adapter.get_vehicle("LSGAB52R7DF000001")
    first_orders = adapter.list_work_orders("LSGAB52R7DF000001")

    # 第二次打开同一库：数据保持稳定，同一外部键不同读取时刻可并存
    connection2 = open_database(tmp_path / "demo.db")
    adapter2 = DemoAfterSalesAdapter(connection2)
    second_vehicle = adapter2.get_vehicle("LSGAB52R7DF000001")
    second_orders = adapter2.list_work_orders("LSGAB52R7DF000001")

    assert second_vehicle == first_vehicle
    assert second_orders == first_orders
    assert len(first_orders) == 2
    connection.close()
    connection2.close()


def test_evidence_can_trace_to_snapshot_and_source_version(tmp_path: Path) -> None:
    """Contract: every snapshot carries source_class/source_ref/rule_version for Evidence backtrace."""
    connection = open_database(tmp_path / "demo.db")
    adapter = DemoAfterSalesAdapter(connection)

    claim = adapter.get_claim("CL-001")
    assert claim.source_class == "MOCK"
    assert claim.source_ref == "demo.duckdb.after_sales.v1"
    assert claim.rule_version == "warranty.t5.v1"

    battery = adapter.get_battery_health("LSGAB52R7DF000005")
    assert battery.soh == 70.0
    assert battery.test_date == "2024-01-20"
    connection.close()


def test_adapter_exposes_no_free_sql(tmp_path: Path) -> None:
    """Contract: the adapter surface offers only semantic methods, never raw SQL."""
    connection = open_database(tmp_path / "demo.db")
    adapter = DemoAfterSalesAdapter(connection)

    assert not hasattr(adapter, "execute")
    assert not hasattr(adapter, "query")
    assert {name for name in dir(adapter) if name.startswith(("get_", "list_"))} == {
        "get_vehicle",
        "list_work_orders",
        "get_claim",
        "get_part",
        "get_battery_health",
        "get_warranty_manual",
        "list_maintenance",
        "get_supplier",
        "get_batch",
    }
    connection.close()