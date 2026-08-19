"""运行时配置及生产启动门禁。"""
from dataclasses import dataclass, field
import os
from os import getenv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_local_env() -> None:
    """Load ignored local configuration without overriding deployment environment."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name and name.isidentifier():
            os.environ.setdefault(name, value.strip('"').strip("'"))


_load_local_env()
_PLACEHOLDER_MARKERS = ("change-me", "replace-with", "your-", "example.com")
_LLM_PROVIDERS = {
    "sensenova": ("https://token.sensenova.cn/v1", "SENSENOVA_API_KEY"),
    "stepfun": ("https://api.stepfun.com/step_plan/v1", "STEPFUN_API_KEY"),
}
_DEFAULT_MODELS = {
    "sensenova": ("sensenova-6.8-flash-lite", "deepseek-v4-flash", "glm-5.2"),
    "stepfun": ("step-3.7-flash",),
}


@dataclass(frozen=True)
class LLMSettings:
    mode: str = getenv("ATTRIBUTION_LLM_MODE", "demo")
    provider: str = getenv("ATTRIBUTION_LLM_PROVIDER", "sensenova")
    base_url: str = getenv("ATTRIBUTION_LLM_BASE_URL", "")
    api_key: str = field(default_factory=lambda: getenv("ATTRIBUTION_LLM_API_KEY", ""), repr=False)
    models: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            model.strip()
            for model in getenv("ATTRIBUTION_LLM_MODELS", "").split(",")
            if model.strip()
        )
    )
    timeout_seconds: float = float(getenv("ATTRIBUTION_LLM_TIMEOUT_SECONDS", "30"))

    def resolved_base_url(self) -> str:
        """返回 LLM 基础 URL（显式配置或提供方默认）。"""
        if self.base_url:
            return self.base_url
        return _LLM_PROVIDERS.get(self.provider, ("", ""))[0]

    def resolved_api_key(self) -> str:
        """返回 LLM API key（显式配置或提供方专属变量）。"""
        if self.api_key:
            return self.api_key
        key_name = _LLM_PROVIDERS.get(self.provider, ("", ""))[1]
        return getenv(key_name, "")

    def resolved_models(self) -> tuple[str, ...]:
        """返回模型列表（显式配置或提供方默认）。"""
        return self.models or _DEFAULT_MODELS.get(self.provider, ())


@dataclass(frozen=True)
class Settings:
    environment: str = getenv("ATTRIBUTION_ENV", "local")
    database_url: str = getenv("ATTRIBUTION_DATABASE_URL", f"duckdb:///{PROJECT_ROOT / 'data' / 'attribution_demo.db'}")
    runtime_database_url: str = getenv("ATTRIBUTION_RUNTIME_DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'attribution_runtime.sqlite3'}")
    auth_database_url: str = getenv("ATTRIBUTION_AUTH_DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'attribution_auth.sqlite3'}")
    rag_mode: str = getenv("ATTRIBUTION_RAG_MODE", "demo")
    rag_base_url: str = getenv("ATTRIBUTION_RAG_BASE_URL", "")
    rag_import_base_url: str = getenv("ATTRIBUTION_RAG_IMPORT_BASE_URL", "")
    nl2sql_mode: str = getenv("ATTRIBUTION_NL2SQL_MODE", "demo")
    nl2sql_database_url: str = getenv("ATTRIBUTION_NL2SQL_DATABASE_URL", "")
    nl2sql_base_url: str = getenv("ATTRIBUTION_NL2SQL_BASE_URL", "")
    integration_timeout_seconds: float = float(getenv("ATTRIBUTION_INTEGRATION_TIMEOUT_SECONDS", "30"))
    max_plan_steps: int = int(getenv("ATTRIBUTION_MAX_PLAN_STEPS", "8"))
    auth_issuer: str = getenv("ATTRIBUTION_AUTH_ISSUER", "")
    auth_audience: str = getenv("ATTRIBUTION_AUTH_AUDIENCE", "")
    auth_jwks_url: str = getenv("ATTRIBUTION_AUTH_JWKS_URL", "")
    dms_base_url: str = getenv("ATTRIBUTION_DMS_BASE_URL", "")
    llm: LLMSettings = field(default_factory=LLMSettings)


def validate_llm_settings(llm: LLMSettings) -> tuple[str, ...]:
    """Return configuration blockers without ever returning the secret value."""
    if llm.mode == "demo":
        return ()
    errors: list[str] = []
    if llm.mode != "remote":
        errors.append("ATTRIBUTION_LLM_MODE must be demo or remote")
    if llm.provider not in _LLM_PROVIDERS:
        errors.append("ATTRIBUTION_LLM_PROVIDER must be sensenova or stepfun")
    if not llm.resolved_base_url().startswith("https://"):
        errors.append("ATTRIBUTION_LLM_BASE_URL must be an HTTPS URL")
    if not llm.resolved_api_key():
        errors.append("LLM API key is required in remote mode")
    if not llm.resolved_models():
        errors.append("at least one LLM model is required in remote mode")
    if llm.timeout_seconds <= 0:
        errors.append("ATTRIBUTION_LLM_TIMEOUT_SECONDS must be positive")
    return tuple(errors)


def validate_production_settings(settings: Settings) -> tuple[str, ...]:
    """Return startup blockers; production never falls back to demo trust boundaries."""
    if settings.environment != "production":
        return ()

    errors: list[str] = []
    if not settings.database_url.startswith("postgresql"):
        errors.append("ATTRIBUTION_DATABASE_URL must use PostgreSQL in production")
    if settings.rag_mode == "demo":
        errors.append("ATTRIBUTION_RAG_MODE must not be demo in production")
    if settings.nl2sql_mode == "demo":
        errors.append("ATTRIBUTION_NL2SQL_MODE must not be demo in production")
    if settings.llm.mode == "demo":
        errors.append("ATTRIBUTION_LLM_MODE must not be demo in production")

    for name, value in (
        ("ATTRIBUTION_AUTH_ISSUER", settings.auth_issuer),
        ("ATTRIBUTION_AUTH_AUDIENCE", settings.auth_audience),
        ("ATTRIBUTION_AUTH_JWKS_URL", settings.auth_jwks_url),
        ("ATTRIBUTION_DMS_BASE_URL", settings.dms_base_url),
    ):
        if not value:
            errors.append(f"{name} is required in production")
        elif any(marker in value.lower() for marker in _PLACEHOLDER_MARKERS):
            errors.append(f"{name} must not use a placeholder value in production")

    for name, value in (
        ("ATTRIBUTION_AUTH_ISSUER", settings.auth_issuer),
        ("ATTRIBUTION_AUTH_JWKS_URL", settings.auth_jwks_url),
        ("ATTRIBUTION_DMS_BASE_URL", settings.dms_base_url),
    ):
        if value and not value.startswith("https://"):
            errors.append(f"{name} must be an HTTPS URL in production")
    return tuple(errors)


def validate_integration_settings(runtime: Settings) -> tuple[str, ...]:
    """阻止未知模式静默降级为 Demo，确保真实依赖失败可见。"""
    errors: list[str] = []
    if runtime.rag_mode not in {"demo", "remote"}:
        errors.append("ATTRIBUTION_RAG_MODE must be demo or remote")
    if runtime.nl2sql_mode not in {"demo", "mysql", "remote"}:
        errors.append("ATTRIBUTION_NL2SQL_MODE must be demo, mysql, or remote")
    if runtime.rag_mode == "remote" and not runtime.rag_base_url:
        errors.append("ATTRIBUTION_RAG_BASE_URL is required in remote mode")
    if runtime.nl2sql_mode == "remote" and not runtime.nl2sql_base_url:
        errors.append("ATTRIBUTION_NL2SQL_BASE_URL is required in remote mode")
    if runtime.nl2sql_mode == "mysql" and not runtime.nl2sql_database_url.startswith("mysql://"):
        errors.append("ATTRIBUTION_NL2SQL_DATABASE_URL must be a mysql:// URL in mysql mode")
    if runtime.integration_timeout_seconds <= 0:
        errors.append("ATTRIBUTION_INTEGRATION_TIMEOUT_SECONDS must be positive")
    return tuple(errors)


settings = Settings()

