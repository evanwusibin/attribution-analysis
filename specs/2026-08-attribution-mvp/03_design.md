# 03 Design

## 模块关系

```text
HTTP client → FastAPI app → /health
```

Slice 0 没有状态机、持久化或外部副作用。其唯一职责是提供一个可验证的应用边界。

## 后续稳定边界

```text
API → case service → attribution orchestrator → adapters/tools
                              ↓
                         evidence store
```

`adapters` 是唯一允许接入 RAG、NL2SQL 或模型供应商的区域。领域规则与外部集成不得进入 API 层。

## 约束

- 所有将来写入的证据都必须携带来源等级、来源定位与规则版本。
- 自动处置路径在本项目首期不存在。
