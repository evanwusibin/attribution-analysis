# 原型评审：归因工作台

> **状态**：业务原型蓝图 draft / D6；Pencil 七态 draft 画板已绘制并完成结构与裁切检查，尚待业务/架构评审。

[`ATTRIBUTION_WORKBENCH_BLUEPRINT.md`](ATTRIBUTION_WORKBENCH_BLUEPRINT.md) 是完整的画板、跳转、可访问来源标签与评审记录模板。它以 G1 状态机为边界，不定义后端实现。

## 原型职责

原型采用“对话优先、结果按需展开”的工作台模式：用户先描述通用经营问题，系统在对话中澄清范围并反馈分析进度，右侧结果抽屉再展示本次分析的证据、评估和建议。原型只验证用户如何理解分析过程和不确定性；不定义后端实现。

默认场景覆盖售前与售后经营归因：商机丢单、业绩未达标、客户流失、报价竞争力、线索质量、索赔合规、服务店评定、供应商反向索赔、客户投诉等。电池包故障只是售后故障诊断下的可配置领域，不进入默认首页文案。
## 本轮深度优化目标

当前评审稿继续沿用七态状态契约，但视觉骨架升级为“左侧治理导航 → 中间对话与流程轨迹 → 右侧结果抽屉”：

- 左侧导航承载工作台、会话、证据、分析轨迹和导出入口。
- 结果区增加带来源等级、单位、周期和规则版本的趋势图、归因贡献图和证据覆盖矩阵。
- 分析轨迹改为**真实单向流程图**：P-03 固定以“输入边界 → RAG 检索 → 受控查询 → 证据评估 → 流式结果”五张节点卡片串联；当前节点展开可审计子任务、输入/输出与状态，右侧抽屉同步其明细。
- 静态稿以分段虚线箭头表达流向；真实运行时以连接线流动高亮、当前节点光晕、已完成节点渐隐和待执行节点弱化反馈进度。文字状态与徽标独立保留，动画不是唯一反馈。
- 不展示模型原始 CoT，只展示可审计的 Plan、RAG、受控 NL2SQL、Evidence、评估和 Result 事件。

具体视觉与交互契约见 [`ATTRIBUTION_WORKBENCH_BLUEPRINT.md`](ATTRIBUTION_WORKBENCH_BLUEPRINT.md) 第 7 节。当前 Pencil 画布的视觉优化仍是 draft，导出图片必须在完成节点、尺寸、裁切和七态存在性检查后回写索引。


| 状态 | 用户看到什么 | 系统行为约束 |
|---|---|---|
| 空态 | 示例问题、场景提示、数据来源说明 | 不暗示已有结论 |
| 规划中 | 当前子问题与预计证据源 | 可取消，不展示编造证据 |
| 部分成功 | 成功证据与失败工具并列 | 失败不被隐藏 |
| 证据不足 | 缺少字段、补数来源、人工复核入口 | 不给责任结论 |
| 有结论 | 六段结果、证据等级、来源定位 | `MOCK` 显著标识 |
| 已取消 | 已完成证据与未执行计划 | 禁止继续执行 |
| 追问 | 继承的证据摘要与新问题 | 不重复伪造历史查询 |

## Pencil 交付

当前源文件为 `D:\heimaAI\PytorchSDXX\pen_data\pencil-new.pen`。本次已用七态优化稿直接替换空白旧稿；旧稿保留为同目录的 `pencil-new.pen.before-optimized.bak`，仅用于回退，不参与评审。

优化稿固定为 7 张 `1440×900` 画板，涵盖 P-01 至 P-07，并将旧的无效空白画布从原始源文件中移除。

已在当前活动的 `pen_data/pencil-new.pen` 画布重构通用对话版 P-01 至 P-07。每张画板采用 CRM 风格的三栏结构：左侧会话列表、中间对话流与输入台、右侧按需展开的结果抽屉。

结果抽屉按分析状态展示：Plan、RAG 检索命中、受控 NL2SQL、Evidence、相关度/完整度评估、流式状态、Result 版本与人工复核限制。默认内容使用通用经营场景，不再把电池诊断写入主问题、默认证据或默认结论。

当前评审图片位于 [`attribution-workbench-conversation-universal/`](attribution-workbench-conversation-universal/)。其中 P-03 的现有 PNG 是流程图改版前的导出物，只能作为历史对照，**不得用于本轮评审**；已同步的有效 Pencil 源文件为 `D:\heimaAI\PytorchSDXX\pen_data\pencil-new.pen`，待可用导出通道恢复后必须重新导出 P-03 并更新下表索引。

| 画板 | 图像文件 | 主要用途 |
|---|---|---|
| P-01 空态 | [`bi8Au.png`](attribution-workbench-conversation-universal/bi8Au.png) | 新建对话、快捷场景、无结果空态 |
| P-02 规划中 | [`j5BE09.png`](attribution-workbench-conversation-universal/j5BE09.png) | 对话澄清与计划生成 |
| P-03 执行中 | [`P03-analysis-flow.png`](attribution-workbench-conversation-universal/P03-analysis-flow.png) | 原工作台底图上的可执行流程图：节点卡片、虚线连接、当前节点子任务与右侧同步明细 |
| P-04 部分成功 | [`FBVdM.png`](attribution-workbench-conversation-universal/FBVdM.png) | 失败工具与已有证据并列 |
| P-05 待补充 | [`bPa5F.png`](attribution-workbench-conversation-universal/bPa5F.png) | 缺失字段、追问和人工复核 |
| P-06 已取消 | [`qmgSY.png`](attribution-workbench-conversation-universal/qmgSY.png) | 取消后保留证据与新版本入口 |
| P-07 已完成 | [`R9dlm.png`](attribution-workbench-conversation-universal/R9dlm.png) | 对话结果、证据引用和建议 |

旧版 `attribution-workbench-g1-draft.png/` 与 `attribution-workbench-enterprise-draft/` 仅保留作演进对照，不作为当前评审稿。画板仍是评审材料，不得标注为“已验收”。