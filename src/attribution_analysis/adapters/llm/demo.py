"""本地 LLM 适配器；保证默认测试和演示不依赖外网。"""
from attribution_analysis.ports.llm import LLMMessage, LLMResponse


class DemoLLMAdapter:
    def complete(self, messages: tuple[LLMMessage, ...]) -> LLMResponse:
        """演示模式：不调用远程模型，返回固定提示文本。"""
        if not messages:
            raise ValueError("at least one LLM message is required")
        return LLMResponse(
            content="演示模式未调用远程模型；请将 ATTRIBUTION_LLM_MODE 设置为 remote 后再进行模型验证。",
            model="demo",
            provider="demo",
        )
