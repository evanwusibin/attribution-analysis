# 业务 Skill 契约目录（实施前草案）

> **状态**：draft / pre-implementation。
> **门禁**：仅定义职责、输入输出、工具白名单和验收契约；不创建 skill runtime、Prompt、业务代码、依赖、数据库或真实连接。
> **原则**：Skill 是受控业务能力声明，不是模型原始思维链。工作台只展示可审计步骤与持久化事件。

## 1. 统一 Skill 数据结构

```text
SkillContract {
  skill_id:           唯一标识
  scenario:           售后场景 S1–S5
  purpose:             单一业务职责
  input_contract:     已确认的业务输入与版本
  output_contract:    结构化候选结论、证据引用、缺失项、人工复核
  allowed_tools:      白名单工具及只读/写入边界
  evidence_policy:    FACT / MOCK / MISSING 规则
  state_policy:       允许的任务状态与失败降级
  golden_cases:       正常、异常、缺失、反例
  forbidden_actions:  不得执行的裁决或外部写操作
}
```

### 共用执行轨迹（用户可见，不是 CoT）

```text
接收已确认输入
  → 校验场景、主体和字段完整性
  → 生成最多 8 步的 AnalysisPlan
  → 调用白名单只读工具
  → 标准化 Evidence（来源、版本、等级、定位）
  → 评估相关度/完整度/一致性/冲突
  → 生成候选 Result 或 needs_input
  → 写入审计事件和人工复核限制
```

节点内部只显示这些可复核执行步骤和结果摘要，不显示隐藏提示词、逐 token 推理或模型原始 CoT。

## 2. Skill 清单

| Skill | 单一职责 | 当前状态 | 前置 |
|---|---|---|---|
| `after_sales_evidence_retrieval` | 汇总 VIN、工单、索赔、零件、保养等共享只读证据 | draft | S1/S2 共用底座、S2 |
| `battery_fault_attribution` | 在 S1 故障域内生成候选根因与补数清单 | draft | S3、固定快照、诊断路径 |
| `claim_compliance_assessment` | 在 S2 索赔域内输出资格建议与证据限制 | draft | S3、FACT 质保规则 |
| `service_complaint_attribution` | S3 投诉根因候选与服务改善建议 | blocked | 投诉/技师/SLA 契约不足 |
| `service_store_performance` | S4 服务店表现候选归因 | blocked | 星级制度、评分和一票否决规则不足 |
| `supplier_recovery_hypothesis` | S5 供应商责任候选假设 | blocked | 合同、批次追溯和责任比例不足 |

## 3. 已进入 S1–S3 设计范围的契约

### 3.1 `after_sales_evidence_retrieval`

```text
输入：已确认的业务主体标识 + 时间范围 + 证据类别
工具：只读快照查询、受控文本检索、来源版本读取
输出：Evidence[] + 缺失字段[] + 工具执行摘要
禁止：任意 SQL、外部系统写回、没有 source_ref 的可信证据
降级：单工具超时 → 保留其他 Evidence；无来源 → MISSING
```

### 3.2 `battery_fault_attribution`（S1）

```text
输入：车辆/电池域标识 + 故障现象 + 时间范围 + 可用检测信号
步骤：域匹配 → 信号完整性 → 诊断路径匹配 → 候选根因 → 反例检查
输出：候选根因[]、影响范围、Evidence 引用、缺失清单、人工复核原因
来源：信号 FACT；固定演示快照 MOCK；无定位制度/诊断报告 MISSING
禁止：仅凭 SOH < 80% 自动拒赔、追偿或责任裁决
黄金案例：正常、异常、证据不足、反例（异常数值但无制度依据）
```

### 3.3 `claim_compliance_assessment`（S2）

```text
输入：索赔快照 + 工单/车辆/零件/保养 + 质保规则版本
步骤：快照关联 → 规则版本确认 → 资格项逐项核验 → 冲突/缺失识别 → 建议生成
输出：资格建议、逐项理由、Evidence 引用、MISSING 清单、人工审核提示
来源：T5 质保/保养/重新授权规则 FACT；演示规则 MOCK；缺失条款 MISSING
禁止：审批、回写 DMS、拒赔执行、追偿执行
黄金案例：正常资格、超保、非原厂件、换表叠加、关键字段缺失
```

## 4. 被阻塞 Skill 的契约草案

| Skill | 允许先定义 | 阻塞条件 | 不能提前假设 |
|---|---|---|---|
| `service_complaint_attribution` | 输入字段、缺失清单、人工复核出口 | 投诉分类、维修尝试、技师记录、SLA | 不能假设投诉阈值或责任归属 |
| `service_store_performance` | 指标展示结构、来源标签 | 星级制度、评分规则、一票否决 | 不能假设扣分或降级动作 |
| `supplier_recovery_hypothesis` | 候选假设与证据关系 | 采购质保合同、批次追溯、历史追偿、责任比例 | 不能输出追偿决定或比例 |

## 5. 统一工具白名单草案

| 工具类别 | 允许 | 明确禁止 |
|---|---|---|
| 共享快照读取 | 参数化、只读、限行、超时、审计 | Agent 直连数据库、凭据进入上下文 |
| 受控文本检索 | 指定语料、版本、定位、相关度 | 无来源 RAG 命中当制度结论 |
| 受控 NL2SQL | 业务意图 → 白名单语义视图；服务端绑定参数 | 任意 SQL、DDL/DML、连接串、数据库账号 |
| 文件证据读取 | 已验证快照、路径沙箱、类型/大小校验 | 任意路径、越权读取、覆盖原始证据 |
| 结果导出 | 绑定主体与 Result 版本的短期授权 | 隐去 `MOCK/MISSING`、跨主体下载 |
| 外部 DMS/CRM | 只读适配器 | 状态回写、审批、拒赔、追偿、扣款 |

## 6. 实施前必须补齐

1. 为单个 Skill 绑定一个已批准 Slice，不允许跨 Slice 隐式施工。
2. 为每个 Skill 完成输入字段、版本、权限、工具参数和输出 schema 的评审。
3. 先写可失败契约测试：证据先于结论、来源等级、幂等、取消、超时、越权、禁止写回。
4. 固定黄金案例及预期 Evidence/Result；测试数据与真实数据命名空间隔离。
5. 通过 B1 后才可建立 runtime skill、适配器、接口和数据库实现。
