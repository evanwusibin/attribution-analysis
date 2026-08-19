# LLM 运行配置

## 边界

项目提供一个最小 `LLMPort`，远程实现使用 OpenAI-compatible 的
`/chat/completions` 协议。领域层不依赖供应商名称、SDK 或 API key。

默认模式是 `demo`，不会访问外网，也不会改变现有归因结果。只有显式设置
`ATTRIBUTION_LLM_MODE=remote` 后，组合根才创建远程适配器。

## 商汤脱管

在本机未跟踪的 `.env` 或部署平台密钥中设置：

```dotenv
ATTRIBUTION_LLM_MODE=remote
ATTRIBUTION_LLM_PROVIDER=sensenova
ATTRIBUTION_LLM_BASE_URL=https://token.sensenova.cn/v1
ATTRIBUTION_LLM_MODELS=sensenova-6.8-flash-lite,deepseek-v4-flash,glm-5.2
SENSENOVA_API_KEY=<本机注入，不要提交>
```

模型按配置顺序尝试；前一个模型发生网络、HTTP 或响应格式错误时才尝试下一个。

## 阶跃托管

```dotenv
ATTRIBUTION_LLM_MODE=remote
ATTRIBUTION_LLM_PROVIDER=stepfun
ATTRIBUTION_LLM_BASE_URL=https://api.stepfun.com/step_plan/v1
ATTRIBUTION_LLM_MODELS=step-3.7-flash
STEPFUN_API_KEY=<本机注入，不要提交>
```

也可以统一使用 `ATTRIBUTION_LLM_API_KEY` 覆盖供应商专属变量。配置校验要求远程
地址使用 HTTPS、密钥非空、模型至少一个、超时时间为正数；错误信息不会回显密钥。

## 验证

先验证离线边界：

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_llm.py
```

远程连通性验证应在本机通过密钥管理注入后执行。不要把 key 放进 `.env.example`、
源码、测试、日志、截图或提交历史。当前远程适配器只验证模型调用链路，尚未把模型
输出接入归因结论；这需要单独定义输出结构、证据约束和审计契约。
