# 项目框架

> 状态：S1 公共内核已实现。本文定义模块职责、依赖方向和业务切片准入，不代表真实业务数据接入或项目整体验收。

## 1. 目标与边界

系统将经营问题组织为一条可追溯的数据流：

```text
业务输入
  → Case 生命周期
    → AnalysisPlan 执行计划
      → 只读工具适配器
        → Evidence 证据
          → AttributionResult 归因结果
```

S0 建立可运行的 HTTP 边界和工程隔离；S1 公共内核已实现 Case、Plan、Execution、Evidence、Result 的本地运行闭环。以下能力仍在对应切片完成后才可进入：

- PostgreSQL 持久化与真实业务数据库连接
- DMS/CRM、LLM、RAG、NL2SQL 和业务规则接入
- 自动审批、扣款、追偿、降级或任何外部写操作

## 2. 目录与职责

```text
src/attribution_analysis/
├── app.py                 # 组合根：创建并导出 FastAPI 应用
├── api/                   # HTTP 边界：路由、协议校验、系统响应
│   ├── cases.py            # S1 Case、追问、取消、证据/结果查询
│   ├── constants.py        # 服务级常量
│   └── health.py           # 系统健康检查
├── application/
│   └── core.py             # S1 公共内核用例服务
├── domain/
│   └── core.py             # S1 领域对象、状态转换和审计
├── adapters/              # 外部只读能力适配器；不得绕过此边界直连系统
└── infrastructure/        # 持久化、配置和运行时实现；S1+ 按批准切片增加

tests/
└── test_health.py         # S0 可执行契约测试
```

## 3. 依赖方向

```text
api → application → domain
                    ↑
infrastructure ──────┘
adapters ────────────┘
```

约束：

1. `domain` 不导入 FastAPI、数据库驱动、LLM SDK 或外部项目模块。
2. `api` 不创建数据库连接、不调用模型、不执行任意 SQL，只装配 HTTP 入口。
3. `application` 只依赖领域协议，通过适配器协议请求外部读取。
4. `adapters` 是 RAG、NL2SQL、DMS/CRM 读取等能力的唯一接入位置。
5. `infrastructure` 提供实现，不向上层泄露连接字符串、凭据或内部错误堆栈。

## 4. 稳定数据结构

后续切片围绕以下对象演进，不能在 API 层拼装平行模型：

```text
AttributionCase
  ├─ subject / conversation / input_fingerprint
  ├─ lifecycle_state
  ├─ AnalysisPlan(version, steps)
  ├─ ToolExecution(sequence, status, duration, failure)
  ├─ Evidence(source_class, source_ref, rule_version, confidence)
  └─ AttributionResult(version, claims, gaps, review_required)
```

证据等级是跨模块不变量：

- `FACT`：必须有可定位来源，才可进入事实覆盖范围。
- `MOCK`：必须标明模拟数据或规则版本，不得单独形成自动处置。
- `MISSING`：必须输出缺失字段、预期来源和人工复核路径。

## 5. 状态与交付准入

```text
draft → review → approved → implemented → accepted
  └──────────────────────────────→ blocked
```

- `draft`：内容存在但未完成跨文档核验。
- `review`：准出材料齐备，等待产品/架构评审。
- `approved`：允许为指定切片编写测试和最小实现。
- `implemented`：实现已存在，但尚无可复现运行证据。
- `accepted`：已执行并记录安装、测试和运行验收结果。
- `blocked`：前置设计、数据、规则或评审未完成。

当前状态：

| 范围 | 状态 | 可执行动作 |
|---|---|---|
| S0 工程基线 | `accepted` | 已执行安装、测试、健康检查并记录证据；保持基线 |
| S1 归因任务状态机 | `implemented` | 已完成本地公共内核闭环和契约验证；补持久化后再做运行域验收 |
| S2 统一证据模型 | `blocked` | 在 S1 持久化边界确认后补数据契约和来源测试 |
| S3 只读工具适配器 | `blocked` | 在 S2 完成后补安全、超时和降级契约 |
| S4 黄金案例 | `blocked` | 在 S3 完成后接入固定种子和端到端验收 |

## 6. 当前可验证闭环

```text
客户端
  → POST /api/v1/cases
    → Case → Plan → ToolExecution → MOCK Evidence → Result
      → GET /cases/{id}/plans/{version}
      → GET /cases/{id}/evidence
      → GET /cases/{id}/results
      → POST /cases/{id}/follow-ups 或 /cancel
```

该闭环是本地进程内 S1 验证实现，不等同于 PostgreSQL 持久化或真实业务闭环。

## 7. 后续切片准入条件

S1 公共内核已按用户明确授权完成本地闭环。进入 S2 只读证据工具前必须同时满足：

- S1 的持久化边界和迁移策略完成评审；
- 工具白名单、来源三元组、超时和部分失败契约明确；
- 测试计划覆盖无来源响应、只读限制、超时和 `MISSING` 降级；
- 通过评审后先写 S2 契约测试，再接入只读适配器。
