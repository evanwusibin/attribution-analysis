# 02 Requirements

## R-S0-01 健康检查

WHEN 本地客户端请求 `GET /health`，系统 SHALL 返回 HTTP 200 和固定载荷：

```json
{"status":"ok","service":"attribution-analysis"}
```

## R-S0-02 独立性

系统 SHALL 不直接导入 `CRMProject_c` 的任何内部模块。后续复用只能经本工程的适配器边界进行。

## R-S0-03 证据约束

任何后续归因结果 SHALL 区分 `FACT`、`MOCK`、`MISSING`。`MISSING` 或仅 `MOCK` 支撑的关键判断 SHALL 要求人工复核。

## 失败处理

Slice 0 不创建归因任务；未定义的业务路由应返回标准 HTTP 404，而不是伪造结论。
