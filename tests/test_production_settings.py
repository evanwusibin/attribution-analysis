from dataclasses import replace

import pytest

from attribution_analysis.config.settings import (
    LLMSettings,
    Settings,
    validate_integration_settings,
    validate_production_settings,
)


def production_settings(**changes: str) -> Settings:
    """Contract fixture: production settings declare every trust boundary explicitly."""
    baseline = Settings(
        environment="production",
        database_url="postgresql+psycopg://runtime@db.example/attribution",
        rag_mode="remote",
        nl2sql_mode="remote",
        max_plan_steps=8,
        auth_issuer="https://identity.example",
        auth_audience="attribution-api",
        auth_jwks_url="https://identity.example/.well-known/jwks.json",
        dms_base_url="https://dms.example",
        llm=LLMSettings(mode="remote", provider="sensenova", api_key="injected-key", models=("sensenova-6.8-flash-lite",)),
    )
    return replace(baseline, **changes)


def test_integration_settings_reject_unknown_modes_instead_of_using_demo() -> None:
    """Contract: a typo cannot silently cross the real/demo trust boundary."""
    runtime = Settings(rag_mode="production", nl2sql_mode="unknown")

    errors = validate_integration_settings(runtime)

    assert "ATTRIBUTION_RAG_MODE must be demo or remote" in errors
    assert "ATTRIBUTION_NL2SQL_MODE must be demo, mysql, or remote" in errors


def test_remote_integration_requires_endpoint_and_positive_timeout() -> None:
    """Contract: remote dependencies are explicit and bounded before startup."""
    runtime = Settings(
        rag_mode="remote",
        rag_base_url="",
        nl2sql_mode="remote",
        nl2sql_base_url="",
        integration_timeout_seconds=0,
    )

    errors = validate_integration_settings(runtime)

    assert "ATTRIBUTION_RAG_BASE_URL is required in remote mode" in errors
    assert "ATTRIBUTION_NL2SQL_BASE_URL is required in remote mode" in errors
    assert "ATTRIBUTION_INTEGRATION_TIMEOUT_SECONDS must be positive" in errors
def test_production_settings_reject_demo_modes_and_missing_trust_boundaries() -> None:
    """Contract: production startup cannot silently use demo data or unauthenticated identity."""
    errors = validate_production_settings(
        production_settings(rag_mode="demo", auth_issuer="", dms_base_url="replace-with-dms-url")
    )

    assert "ATTRIBUTION_RAG_MODE must not be demo in production" in errors
    assert "ATTRIBUTION_AUTH_ISSUER is required in production" in errors
    assert "ATTRIBUTION_DMS_BASE_URL must be an HTTPS URL in production" in errors


def test_production_settings_accept_explicitly_configured_boundaries() -> None:
    """Contract: a production process starts only after its runtime trust boundaries are configured."""
    assert validate_production_settings(production_settings()) == ()


def test_production_settings_reject_local_database_and_placeholder_values() -> None:
    """Contract: production state cannot fall back to local files or template credentials."""
    errors = validate_production_settings(
        production_settings(
            database_url="duckdb:///data/attribution_demo.db",
            auth_audience="change-me-audience",
        )
    )

    assert "ATTRIBUTION_DATABASE_URL must use PostgreSQL in production" in errors
    assert "ATTRIBUTION_AUTH_AUDIENCE must not use a placeholder value in production" in errors


def test_app_factory_blocks_incomplete_production_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contract: a production API process refuses to start with incomplete trust configuration."""
    from attribution_analysis.api import app as api_app

    monkeypatch.setattr(api_app, "settings", production_settings(auth_jwks_url=""))

    with pytest.raises(RuntimeError, match="ATTRIBUTION_AUTH_JWKS_URL is required in production"):
        api_app.create_app()
