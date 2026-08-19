"""运行时组合根：在基础设施层装配演示适配器，不泄露给领域层。"""
from pathlib import Path
import sqlite3

from attribution_analysis.adapters.after_sales.demo import DemoAfterSalesAdapter
from attribution_analysis.adapters.crm.demo import DemoCrmAdapter
from attribution_analysis.adapters.llm.demo import DemoLLMAdapter
from attribution_analysis.adapters.llm.openai_compatible import OpenAICompatibleLLM
from attribution_analysis.adapters.nl2sql.demo import DemoNL2SQLAdapter
from attribution_analysis.adapters.nl2sql.http import HttpNL2SQLAdapter
from attribution_analysis.adapters.nl2sql.mysql import MySQLNL2SQLAdapter
from attribution_analysis.adapters.rag.demo import DemoRAGAdapter
from attribution_analysis.adapters.rag.http import HttpRAGAdapter
from attribution_analysis.adapters.warranty.demo import DemoWarrantyAdapter
from attribution_analysis.application.core import CoreService
from attribution_analysis.application.scenarios.claim_compliance import ClaimComplianceService
from attribution_analysis.application.scenarios.after_sales import FaultDiagnosisService
from attribution_analysis.application.scenarios.presales import PresalesDiagnosisService
from attribution_analysis.application.scenarios.workbench import BusinessScenarioRunner
from attribution_analysis.application.tools.evidence import EvidenceToolset
from attribution_analysis.config.settings import (
    PROJECT_ROOT,
    settings,
    validate_integration_settings,
    validate_llm_settings,
    validate_production_settings,
)
from attribution_analysis.infrastructure.database.duckdb import open_database, open_mysql
from attribution_analysis.infrastructure.database.runtime import PersistentCaseStore
from attribution_analysis.ports.evidence import KnowledgeImportPort
from attribution_analysis.ports.llm import LLMPort


DEMO_DATABASE_PATH = PROJECT_ROOT / "data" / "attribution_demo.db"


def open_database_by_url(url: str | None = None):
    """根据 database_url 类型打开 DuckDB、SQLite 或 MySQL 连接。"""
    url = url or settings.database_url
    if url.startswith("mysql://"):
        return open_mysql(url)
    sqlite_prefix = "sqlite:///"
    if url.startswith(sqlite_prefix):
        path = url.removeprefix(sqlite_prefix)
        if path == ":memory:":
            return sqlite3.connect(":memory:", check_same_thread=False)
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(path_obj, check_same_thread=False)
    prefix = "duckdb:///"
    if not url.startswith(prefix):
        raise ValueError(f"unsupported database URL: {url}")
    path = url.removeprefix(prefix)
    if path == ":memory:":
        return open_database(":memory:")
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    return open_database(path_obj)


def open_demo_database():
    """打开本地演示分析库；测试内存 URL 直接用内存库，避免与运行服务抢文件锁。"""
    url = settings.database_url
    if url == "duckdb:///:memory:":
        return open_database(":memory:")
    DEMO_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return open_database(DEMO_DATABASE_PATH)


def open_auth_database():
    """认证存储使用独立 SQLite 库（settings.auth_database_url），与 DuckDB 演示库文件锁解耦。"""
    return open_database_by_url(settings.auth_database_url)


def open_runtime_database():
    """打开独立 Case 运行态库，永不复用业务 NL2SQL 数据源。"""
    return open_database_by_url(settings.runtime_database_url)


def demo_database_path() -> Path:
    """返回演示数据库路径（仅 DuckDB 模式）。"""
    return DEMO_DATABASE_PATH


def build_core_service() -> CoreService:
    """组合根：装配数据库连接与证据工具，返回 CoreService。"""
    integration_errors = (*validate_integration_settings(settings), *validate_production_settings(settings))
    if integration_errors:
        raise ValueError("invalid integration settings: " + "; ".join(integration_errors))

    if settings.nl2sql_mode == "mysql":
        nl2sql = MySQLNL2SQLAdapter(open_database_by_url(settings.nl2sql_database_url))
    elif settings.nl2sql_mode == "remote":
        nl2sql = HttpNL2SQLAdapter(settings.nl2sql_base_url, settings.integration_timeout_seconds)
    else:
        nl2sql = DemoNL2SQLAdapter(open_demo_database())

    if settings.rag_mode == "remote":
        rag = HttpRAGAdapter(settings.rag_base_url, settings.integration_timeout_seconds, settings.rag_import_base_url or None)
    else:
        rag = DemoRAGAdapter()
    scenario_connection = open_demo_database()
    scenario_runner = BusinessScenarioRunner(
        presales=PresalesDiagnosisService(DemoCrmAdapter(scenario_connection)),
        after_sales=FaultDiagnosisService(DemoAfterSalesAdapter(scenario_connection)),
        claim_compliance=ClaimComplianceService(DemoWarrantyAdapter()),
    )
    return CoreService(
        EvidenceToolset(rag=rag, nl2sql=nl2sql),
        store=PersistentCaseStore(open_runtime_database()),
        scenario_runner=scenario_runner,
        llm=build_llm_port(),
    )


def build_llm_port() -> LLMPort:
    """Select the local-safe adapter or a validated remote provider."""
    if settings.llm.mode == "demo":
        return DemoLLMAdapter()
    errors = validate_llm_settings(settings.llm)
    if errors:
        raise ValueError("invalid LLM settings: " + "; ".join(errors))
    return OpenAICompatibleLLM(
        base_url=settings.llm.resolved_base_url(),
        api_key=settings.llm.resolved_api_key(),
        provider=settings.llm.provider,
        models=settings.llm.resolved_models(),
        timeout_seconds=settings.llm.timeout_seconds,
    )

