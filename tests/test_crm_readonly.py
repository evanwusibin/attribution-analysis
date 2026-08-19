import sqlite3
from pathlib import Path

import duckdb
import pytest

from attribution_analysis.adapters.crm.demo import CrmReadonlyAdapter, CrmSchemaError


def test_crm_adapter_rejects_missing_external_database(tmp_path: Path) -> None:
    """Contract: a missing CRM source fails explicitly instead of falling back to Demo data."""
    with pytest.raises(FileNotFoundError, match="CRM database does not exist"):
        CrmReadonlyAdapter(db_path=str(tmp_path / "missing.db"))


def test_crm_adapter_requires_all_semantic_views_before_queries() -> None:
    """Contract: real CRM access is blocked until all six whitelist views are validated."""
    connection = duckdb.connect(":memory:")
    adapter = CrmReadonlyAdapter(connection=connection)

    with pytest.raises(CrmSchemaError, match="v_opportunities"):
        adapter.require_semantic_views()
    with pytest.raises(CrmSchemaError, match="v_opportunities"):
        adapter.query_opportunity_funnel()
    connection.close()


def test_crm_adapter_context_manager_closes_owned_connection(tmp_path: Path) -> None:
    """Contract: adapter-owned connections are closed at context exit."""
    database = tmp_path / "crm.db"
    sqlite3.connect(database.as_posix()).close()

    adapter = CrmReadonlyAdapter(db_path=str(database))
    connection = adapter.connection
    adapter.close()

    with pytest.raises(duckdb.ConnectionException):
        connection.execute("SELECT 1")
