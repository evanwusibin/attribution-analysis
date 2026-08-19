import json
from contextlib import contextmanager

import pytest

from attribution_analysis.adapters.llm.openai_compatible import LLMProviderError, OpenAICompatibleLLM
from attribution_analysis.config.settings import LLMSettings, validate_llm_settings
from attribution_analysis.ports.llm import LLMMessage


def test_remote_settings_resolve_provider_defaults_without_secret_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contract: provider selection supplies safe endpoint/models and never exposes API keys."""
    # 隔离 .env 注入的 ATTRIBUTION_LLM_MODELS，验证 provider 默认模型契约本身（而非本地配置覆盖）
    monkeypatch.delenv("ATTRIBUTION_LLM_MODELS", raising=False)
    settings = LLMSettings(mode="remote", provider="sensenova", api_key="secret-token")

    assert settings.resolved_base_url() == "https://token.sensenova.cn/v1"
    assert settings.resolved_models() == (
        "sensenova-6.8-flash-lite",
        "deepseek-v4-flash",
        "glm-5.2",
    )
    assert "secret-token" not in repr(settings)
    assert validate_llm_settings(settings) == ()


def test_remote_settings_reject_missing_key_and_insecure_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contract: remote calls cannot start with missing credentials or non-HTTPS transport."""
    monkeypatch.delenv("ATTRIBUTION_LLM_API_KEY", raising=False)
    monkeypatch.delenv("STEPFUN_API_KEY", raising=False)
    settings = LLMSettings(mode="remote", provider="stepfun", base_url="http://localhost/v1")

    errors = validate_llm_settings(settings)

    assert "LLM API key is required in remote mode" in errors
    assert "ATTRIBUTION_LLM_BASE_URL must be an HTTPS URL" in errors


def test_adapter_uses_first_working_model_and_preserves_provider_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contract: a failed primary model falls back to the next configured model."""
    calls: list[str] = []

    class Response:
        def read(self) -> bytes:
            return json.dumps({"choices": [{"message": {"content": "可用结果"}}]}).encode()

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(request: object, timeout: float) -> Response:
        model = json.loads(request.data.decode())["model"]
        calls.append(model)
        if model == "primary":
            raise TimeoutError("primary timed out")
        return Response()

    monkeypatch.setattr(
        "attribution_analysis.adapters.llm.openai_compatible.urlopen",
        fake_urlopen,
    )
    adapter = OpenAICompatibleLLM("https://llm.example/v1", "secret", "sensenova", ("primary", "backup"))

    result = adapter.complete((LLMMessage("user", "分析延迟"),))

    assert calls == ["primary", "backup"]
    assert result.content == "可用结果"
    assert result.model == "backup"
    assert result.provider == "sensenova"


def test_adapter_reports_all_model_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contract: exhausted degradation order returns an actionable aggregate failure."""
    @contextmanager
    def failing_urlopen(request: object, timeout: float):
        raise TimeoutError("network unavailable")
        yield

    monkeypatch.setattr(
        "attribution_analysis.adapters.llm.openai_compatible.urlopen",
        failing_urlopen,
    )
    adapter = OpenAICompatibleLLM("https://llm.example/v1", "secret", "stepfun", ("only-model",))

    with pytest.raises(LLMProviderError, match="only-model"):
        adapter.complete((LLMMessage("user", "测试"),))
