# API 契约

> **状态**：Slice 0 为 approved；业务 API 蓝图为 draft / D5，尚未获准实现。

## 已发布基线

Slice 0 仅发布：

| 方法 | 路径 | 成功响应 |
|---|---|---|
| GET | `/health` | `200 {"status":"ok","service":"attribution-analysis"}` |

## 业务 API 蓝图

[`ATTRIBUTION_API_V1.md`](ATTRIBUTION_API_V1.md) 定义 Case 创建、读取、证据、结果、追问、取消与导出的版本化契约、状态映射和错误语义。

该文档不授权实现业务路由。只有相应 Slice Spec 与测试计划获批后，才可按其契约新增接口；不得依据旧项目接口直接推断或提前实现新项目公共 API。
