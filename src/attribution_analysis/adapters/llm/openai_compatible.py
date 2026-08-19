"""OpenAI-compatible LLM 传输适配器。

只处理协议转换和模型降级，不承担归因业务规则。
"""
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from attribution_analysis.ports.llm import LLMMessage, LLMResponse


class LLMProviderError(RuntimeError):
    """Remote provider rejected or failed a request."""


@dataclass(frozen=True)
class OpenAICompatibleLLM:
    base_url: str
    api_key: str
    provider: str
    models: tuple[str, ...]
    timeout_seconds: float = 30.0

    def complete(self, messages: tuple[LLMMessage, ...]) -> LLMResponse:
        """按配置模型顺序重试调用，全部失败时抛 LLMProviderError。"""
        if not messages:
            raise ValueError("at least one LLM message is required")
        failures: list[str] = []
        for model in self.models:
            try:
                payload = self._request(model, messages)
                content = payload["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise LLMProviderError("provider returned empty content")
                return LLMResponse(content=content, model=model, provider=self.provider)
            except (HTTPError, URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError, LLMProviderError) as exc:
                failures.append(f"{model}: {exc}")
        raise LLMProviderError(f"all configured models failed for {self.provider}: {'; '.join(failures)}")

    def _request(self, model: str, messages: tuple[LLMMessage, ...]) -> dict:
        """向 chat/completions 发起一次 HTTP 请求并解析 JSON 响应。"""
        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        body = json.dumps(
            {
                "model": model,
                "messages": [{"role": item.role, "content": item.content} for item in messages],
                "temperature": 0.1,
            }
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, dict):
            raise LLMProviderError("provider response must be a JSON object")
        return decoded
