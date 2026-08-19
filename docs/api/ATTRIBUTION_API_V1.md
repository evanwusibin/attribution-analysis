# 归因 API v1 详细契约

> **状态**：draft / D5。本文是版本化 API 蓝图，不授权实现业务接口、认证接入、数据库连接或外部系统连接。
>
> **上游来源**：G1 领域状态机、G1 原型状态契约、`ARCHITECTURE_AND_BEHAVIOR_BLUEPRINT.md`、`DATABASE_LOGICAL_DESIGN.md`。
>
> **范围**：Slice 0 的 `GET /health` 保持既有独立契约；以下业务接口仅能在对应 Slice Spec 与测试计划获批后实施。

## 1. API 边界

```text
工作台
  → /api/v1/cases、/evidence、/results、/follow-ups、/cancel、/export
    → API 边界校验、身份上下文、幂等路由
      → Case 应用服务 / 编排器
        → 证据与结果读取模型
```

API 不直接调用 CRM、DMS、RAG、NL2SQL 或规则实现；其只能提交命令或读取已经持久化的 Case、Evidence、Result。所有外部读取均由编排器通过只读工具适配器完成。无接口可审批索赔、修改 DMS 状态、降级服务网点、扣款或发起供应商追偿。

## 2. 通用约定

| 项目 | 契约 |
|---|---|
| 基础路径 | `/api/v1`；版本升级采用新路径，不破坏已发布响应 |
| 编码 | JSON / UTF-8；时间为 ISO 8601 UTC |
| 身份上下文 | 网关注入 `subject_id`、角色和请求追踪号；请求体不得声明或覆盖主体身份 |
| 关联标识 | 响应含 `request_id`；创建命令额外含 `case_id` |
| 资源状态 | 以 G1 `created` 至终态状态机为准；外部单据状态只存在于只读快照 |
| 来源字段 | 任一 Evidence 返回 `source_class`、`source_ref`、`rule_version`；无来源的内容不作为证据返回 |
| 分页 | 集合读取使用游标 `cursor` 与 `limit`；默认 20，最大 100 |
| 内容限制 | 首期问题文本为 5–2,000 个 Unicode 字符；补充文本同上；超限在 API 边界拒绝 |

所有响应使用以下包络；`data` 仅承载成功业务数据，错误不伪装为正常结果。

```json
{
  "request_id": "req_...",
  "data": {}
}
```

```json
{
  "request_id": "req_...",
  "error": {
    "code": "CASE_INPUT_INVALID",
    "message": "请补充具体异常、对象或时间范围。",
    "retryable": false,
    "display_state": "input_error",
    "details": []
  }
}
```

## 3. 资源摘要

| 资源 | 最小对外字段 | 不暴露字段 |
|---|---|---|
| Case | `case_id`、场景、问题摘要、状态、进度、创建/更新时间、人工复核标记 | 内部工具参数、外部凭据、原始错误堆栈 |
| Plan | 版本、步骤号、工具类别、步骤状态、最大步数 | 未执行步骤的虚构结果、未授权工具名称 |
| Evidence | 摘要、来源等级、来源定位、规则版本、置信度、记录时间 | 非必要原始敏感载荷、连接信息 |
| Result | 版本、六段结果、关键指标、缺失项、人工复核、证据引用 | 未经证据支持的责任裁决 |
| Export | 导出状态、文件元数据、生成时间、结果版本 | 长期公开下载地址、其他主体的数据 |

## 4. 命令接口

### 4.1 创建或复用 Case

| 项目 | 契约 |
|---|---|
| 方法与路径 | `POST /api/v1/cases` |
| 允许起点 | 无任务 / 有效会话 |
| 状态效果 | 新建：`created → validating → planning`；重复：返回既有未完成 Case |
| 幂等 | 必须携带 `Idempotency-Key`；作用域为 `subject_id + conversation_id + input_fingerprint + key` |
| 成功 | 新建 `202 Accepted`；复用 `200 OK`，均返回同一 Case 摘要 |
| 禁止 | 不直接创建 Result、不直接执行任意工具、不接受外部单据状态写入 |

```json
{
  "conversation_id": "conv_...",
  "scenario_hint": "S1",
  "question": "电池包健康度异常，是否需要人工复核？"
}
```

响应的 `progress` 只可包含已持久化的状态与步骤，首次有效输入在 5 秒内必须处于 `planning` 或返回明确拒绝。

### 4.2 追问并创建新版本

| 项目 | 契约 |
|---|---|
| 方法与路径 | `POST /api/v1/cases/{case_id}/follow-ups` |
| 允许起点 | `completed`、`needs_input`、`failed`、`cancelled` |
| 状态效果 | 创建新的 `AnalysisPlan(vN)`；随后进入 `planning`；历史 Evidence/Result 保留 |
| 幂等 | 必须携带新的 `Idempotency-Key`；同键重复返回同一追问 Case 版本 |
| 成功 | `202 Accepted`，返回父 Case、`plan_version` 与已复用证据数量 |
| 禁止 | 覆盖既有 Result、删除证据、重跑无关工具、跨 Case 注入证据 |

```json
{
  "question": "补充检测报告后，请重新判断是否仍需人工复核。",
  "attachments": [
    {"snapshot_ref": "snap_...", "purpose": "supplemental_evidence"}
  ]
}
```

附件只能引用已通过受控上传/适配器创建的快照标识；本接口不直接接收文件内容，避免将未验证文件直接纳入证据链。

### 4.3 请求取消

| 项目 | 契约 |
|---|---|
| 方法与路径 | `POST /api/v1/cases/{case_id}/cancel` |
| 允许起点 | `created`、`validating`、`planning`、`executing`、`synthesizing` |
| 状态效果 | 写入 `cancel_requested_at`；工具边界确认后 `cancelling → cancelled` |
| 幂等 | 同一 Case 多次取消均返回当前取消状态，不生成重复事件 |
| 成功 | `202 Accepted`；若已终态则 `200 OK` 返回既有终态 |
| 禁止 | 中断已完成的原子只读查询、删除已写 Evidence、伪造未执行步骤失败 |

取消是异步请求，不保证响应时已进入 `cancelled`；工作台应继续轮询 Case 状态。取消后只能读取历史证据、导出或发起追问。

### 4.4 创建导出任务

| 项目 | 契约 |
|---|---|
| 方法与路径 | `POST /api/v1/cases/{case_id}/exports` |
| 允许起点 | `completed`、`needs_input`、`failed`、`cancelled` |
| 状态效果 | 生成只读导出任务，不改变 Case/Result/Evidence |
| 幂等 | `Idempotency-Key` 在 `case_id + result_version + export_format` 作用域唯一 |
| 成功 | `202 Accepted`，返回 `export_id` 与绑定的 `result_version` |
| 禁止 | 导出其他主体数据、隐去 `MOCK`/`MISSING` 标记、产生外部处置指令 |

## 5. 认证、附件、Review 与管理员接口

### 5.1 认证与身份

| 方法与路径 | 职责 | 成功语义 |
|---|---|---|
| `GET /api/v1/auth/login` | 生成授权请求并跳转身份提供方 | 不返回或暴露长期访问令牌 |
| `GET /api/v1/auth/callback` | 校验 `state`、完成授权码交换、建立服务端会话 | 重定向至工作台；失败进入登录错误页 |
| `POST /api/v1/auth/refresh` | 在有效刷新会话下续期 | 仅更新短期访问会话 |
| `POST /api/v1/auth/logout` | 失效当前服务端会话和事件连接 | 后续资源请求返回未认证 |
| `GET /api/v1/me` | 返回主体、角色、会话过期时间与可用能力 | 不返回凭据、内部 IdP 声明或其他主体数据 |

身份提供方协议、令牌签名校验、密钥轮换和部署凭据属于运行配置，不写入请求体或前端持久化存储。开发演示可使用明确标记的本地身份适配器，但不得将 `x_subject_id` 视为正式认证机制。

### 5.2 附件与解析

| 方法与路径 | 约束 |
|---|---|
| `POST /api/v1/conversations/{conversation_id}/attachments` | `multipart/form-data`；返回附件元数据与 `parsing` 状态；校验主体、扩展名、MIME、大小、恶意内容与路径 |
| `GET /api/v1/attachments/{attachment_id}` | 主体授权后返回受限下载授权或内容流；不得返回物理路径 |
| `DELETE /api/v1/attachments/{attachment_id}` | 删除对象访问入口并记录审计；若已被 Evidence 引用则仅逻辑撤销，不破坏历史引用 |
| `GET /api/v1/attachments/{attachment_id}/status` | 返回 `parsing`、`ready`、`failed`、失败码、可重试性和快照引用 |

附件解析为异步工作，不得因上传成功而自动成为 Evidence；只有解析成功、来源被标准化并被 Case/Plan 显式引用后，才能进入证据链。

### 5.3 人工复核

| 方法与路径 | 允许起点 | 效果 |
|---|---|---|
| `POST /api/v1/cases/{case_id}/reviews` | `needs_input` 或 Result 标记 `manual_review_required` | 创建 `Review=requested`，返回复核原因和当前 Result 版本 |
| `GET /api/v1/cases/{case_id}/reviews` | 任意可读取 Case | 返回 Review 与 ReviewAction 时间线 |
| `POST /api/v1/reviews/{review_id}/actions` | `requested` / `in_review` | 追加 `confirm`、`reject`、`request_data` 或 `append_evidence`；不覆盖历史数据 |

`append_evidence` 只引用受控上传或适配器产生的快照。任何补录或追问导致的结论变化必须创建新 Result 版本；Review 本身不执行外部审批或处置。

### 5.4 管理与审计

| 方法与路径 | 角色 | 约束 |
|---|---|---|
| `POST /api/v1/admin/config/reload` | 系统管理员 | 校验完整配置后原子替换；失败保留上一有效版本并记录审计 |
| `GET /api/v1/admin/data-sources` | 系统管理员 | 仅返回健康、版本、延迟和能力，不泄露连接串或凭据 |
| `GET /api/v1/admin/audit-events` | 系统管理员 | 游标分页、按时间/Case/事件类型过滤；业务正文和敏感字段脱敏 |

## 6. 实时事件与恢复

实时事件是已持久化状态变化的加速投影；HTTP 查询是刷新、断线和事件缺失时的权威恢复来源。选择 WebSocket 作为首期实时通道，不允许将轮询当作唯一交互方式，也不要求事件承载未持久化的模型原始输出。

| 事件 | 最小字段 | 触发约束 |
|---|---|---|
| `case.status_changed` | `event_id`、`case_id`、`status`、`occurred_at` | 对应已写入状态迁移 |
| `plan.updated` | `event_id`、`case_id`、`plan_version`、`current_step` | 对应已持久化 Plan |
| `execution.updated` | `event_id`、`case_id`、`execution_id`、`status`、`duration_ms` | 不泄露工具凭据或任意 SQL |
| `evidence.recorded` | `event_id`、`case_id`、`evidence_id`、`source_class` | 只通知可读取的 Evidence 摘要 |
| `result.available` | `event_id`、`case_id`、`result_version`、`manual_review_required` | 对应已持久化 Result |
| `review.updated` | `event_id`、`case_id`、`review_id`、`status` | 对应已持久化 ReviewAction |
| `attachment.updated` | `event_id`、`attachment_id`、`status` | 仅通知对象所有者/授权复核人 |

连接路径为 `GET /api/v1/events?cursor={last_event_id}` 的 WebSocket 升级请求。服务端按主体授权过滤事件，客户端重连携带最后已确认 `event_id`；游标过期、事件缺口或页面刷新时，客户端依次查询 Case、Plan、Evidence、Result、Review 与附件状态恢复投影。心跳仅证明连接存活，不改变 Case 状态。

## 7. 查询接口

| 方法与路径 | 返回资源 | 状态与一致性要求 |
|---|---|---|
| `GET /api/v1/cases/{case_id}` | Case 摘要、当前 Plan 摘要、进度 | 刷新时的权威恢复入口；不含未持久化进度 |
| `GET /api/v1/cases/{case_id}/task` | 由 Case 状态派生的只读任务状态 | `task_id` 固定等于 `case_id`；不得写入或覆盖 Case 状态 |
| `GET /api/v1/cases/{case_id}/task-logs` | 脱敏的生命周期日志 | 仅返回调用主体可读取 Case 的事件；当前演示实现为内存记录，重启后不保留 |
| `GET /api/v1/conversations/{conversation_id}/cases` | Case 时间线 | 仅返回当前主体所属 Case；游标分页 |
| `GET /api/v1/cases/{case_id}/plans/{version_no}` | 计划步骤及状态 | 仅显示已计划内容；未执行步骤不带 Evidence |
| `GET /api/v1/cases/{case_id}/evidence` | Evidence 列表 | 按 `sequence_no` 稳定排序；支持 `source_class` 过滤 |
| `GET /api/v1/cases/{case_id}/results` | Result 版本列表 | 仅返回版本摘要和人工复核标记 |
| `GET /api/v1/cases/{case_id}/results/{version_no}` | 完整六段 Result 与 Evidence 引用 | 任何事实性结论必须含至少一条可读取引用 |
| `GET /api/v1/exports/{export_id}` | 导出任务状态及一次性下载授权 | 授权短期有效且绑定当前主体 |

Case、Evidence、Result 读取均须验证 `subject_id` 的资源归属。对于 `needs_input`、`failed`、`cancelled`，读取接口仍返回已持久化证据和版本化结果，禁止以空响应掩盖失败。

## 8. 状态与工作台映射

| API 可见状态 | 工作台画板 | 可用接口动作 | 不可见或不可用动作 |
|---|---|---|---|
| `rejected` / 输入校验错误 | P-01 | 修正后创建 Case | 创建计划、读取不存在 Evidence |
| `planning` | P-02 | 读取 Case、取消 | 把计划显示为结论 |
| `executing` | P-03 | 读取 Case/Plan/Evidence、取消 | 显示未来步骤结果 |
| `executing` 且存在非致命失败 | P-04 | 读取部分 Evidence、取消 | 标记为整体完成 |
| `needs_input` | P-05 | 读取 Result/Evidence、追问、导出 | 责任裁决与处置操作 |
| `cancelled` | P-06 | 读取 Evidence、追问、导出 | 调度后续工具 |
| `completed` | P-07 | 读取 Result/Evidence、追问、导出 | 隐去来源等级或提供审批按钮 |

## 9. 错误分类与前端语义

| 错误码 | HTTP | 触发条件 | `retryable` | 前端语义 |
|---|---:|---|---|---|
| `CASE_INPUT_INVALID` | 422 | 文本长度、场景枚举或输入结构无效 | 否 | P-01 字段提示 |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | 创建/追问/导出缺少幂等键 | 否 | 要求客户端重新提交 |
| `CASE_NOT_FOUND` | 404 | Case 不存在或不属于当前主体 | 否 | 无权限/不存在通用提示 |
| `CASE_STATE_CONFLICT` | 409 | 当前状态不允许追问、取消或导出 | 否 | 刷新状态后展示可用动作 |
| `CASE_ALREADY_COMPLETED` | 200 | 对终态重复取消 | 否 | 展示现有终态，不当作异常 |
| `RATE_LIMITED` | 429 | 主体或会话超过限额 | 是 | 显示稍后重试 |
| `TOOL_PARTIAL_FAILURE` | 200 | 一项独立工具失败但 Case 可继续 | 由 Case 决定 | P-04，展示已得证据与缺失项 |
| `DEPENDENCY_TIMEOUT` | 200 / 504 | 单工具或整案超时 | 仅瞬时错误一次 | P-04、P-05 或失败状态，保留证据 |
| `EVIDENCE_INSUFFICIENT` | 200 | `MISSING` 或仅 `MOCK` 无法裁决 | 否 | P-05，强制人工复核 |
| `INTERNAL_FAILURE` | 500 | 未分类服务错误 | 否 | 仅显示请求标识，不泄露堆栈 |

业务“证据不足”和“部分工具失败”是可读取的 Case 结果，不应误用 4xx/5xx 使工作台丢失已得证据。

## 10. 安全与可审计性

- 每个命令记录主体、请求标识、幂等键摘要、目标 Case、状态变化和时间；不得记录明文凭据。
- 所有查询按资源归属授权，导出以短期、单主体授权交付。
- API 不接收任意 SQL、数据库连接参数、工具名或外部写命令。
- 任何 Result 导出与读取均保持 `FACT`、`MOCK`、`MISSING` 的文字标记、来源定位、规则版本与人工复核限制。

## 11. D5 评审准出清单

- [ ] 每个接口都能映射到 G1 状态机和 P-01 至 P-07 的一项用户可见状态。
- [ ] 创建、追问、取消与导出均声明了幂等作用域、权限和状态前置条件。
- [ ] Case 不会绕过 `Evidence → Result` 约束；终态和失败态均可读取已有证据。
- [ ] 外部 DMS/CRM 写操作、任意 SQL 和处置动作均不存在于 API 表面。
- [ ] 错误码可转化为用户可理解的状态，且不泄露内部细节。
