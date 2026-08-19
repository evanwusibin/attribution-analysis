# S9 售前切片 B1 评审准备清单

## 评审依据
- 设计文档：`03_技术方案与架构.md` 第七节
- 数据模型：`02_数据模型与黄金数据集.md` 场景 E
- 切片规划：`04_垂直切片规划.md` § 五

## 一、白名单视图核对（6 个语义视图）

### 1. `v_opportunities`（商机视图）
- **用途**：商机丢单归因（E1）、业绩未达标归因（E2）
- **字段**：opportunity_id、customer_id、stage、amount、probability、close_date、lost_reason
- **安全边界**：只读、限行（无 DELETE/UPDATE/INSERT）
- **来源**：CRM 真实库 `opportunities` 表
- **状态**：⚠️ Demo 适配器已实现；CRM 真实视图 SQL 尚未在正式只读库验收

### 2. `v_customers`（客户视图）
- **用途**：客户流失预警归因（E3）
- **字段**：customer_id、name、level、industry、created_at、last_contact_date
- **安全边界**：只读、限行
- **来源**：CRM 真实库 `customers` 表
- **状态**：⚠️ Demo 适配器已实现；CRM 真实视图 SQL 尚未在正式只读库验收

### 3. `v_field_visits`（跟进记录视图）
- **用途**：客户流失预警归因（E3）、线索质量归因（E5）
- **字段**：visit_id、customer_id、salesperson_id、visit_date、visit_type、notes
- **安全边界**：只读、限行
- **来源**：CRM 真实库 `field_visits` 表
- **状态**：⚠️ Demo 适配器已实现；CRM 真实视图 SQL 尚未在正式只读库验收

### 4. `v_quotes`（报价单视图）
- **用途**：报价竞争力归因（E4）
- **字段**：quote_id、opportunity_id、quoted_price、competitor_price、deviation、status
- **安全边界**：只读、限行
- **来源**：CRM 真实库 `sales_orders` 表 + 扩展
- **状态**：⚠️ 需补充竞品价格字段（当前可能 MISSING）

### 5. `v_contracts`（合同视图）
- **用途**：业绩未达标归因（E2）
- **字段**：contract_id、opportunity_id、amount、signed_date、payment_terms
- **安全边界**：只读、限行
- **来源**：CRM 真实库 `contracts` 表
- **状态**：⚠️ Demo 适配器已实现；CRM 真实视图 SQL 尚未在正式只读库验收

### 6. `v_leads`（线索视图）
- **用途**：线索质量归因（E5）
- **字段**：lead_id、source、quality_score、assign_date、first_contact_date、conversion_date
- **安全边界**：只读、限行
- **来源**：CRM 真实库（需确认表名）
- **状态**：⚠️ 需确认 CRM 库是否有独立线索表

## 二、售前工具注册表评审（4 个工具）

### 1. `compute_funnel_conversion`
- **功能**：计算销售漏斗各阶段转化率
- **输入**：region（可选）、period（可选）
- **输出**：线索→客户→商机→合同各段转化率
- **SQL 边界**：只读 `v_opportunities`、`v_customers`、`v_leads`
- **来源标记**：`source_class=MOCK`（首版统计规则）
- **状态**：✅ Demo 计算工具已实现并有契约测试；正式 CRM 视图待验收

### 2. `score_customer_churn`
- **功能**：客户流失风险评分
- **输入**：customer_id
- **输出**：流失评分（0-1）、跟进频率递减、最后跟进质量、外勤缺失
- **SQL 边界**：只读 `v_customers`、`v_field_visits`
- **来源标记**：`source_class=MOCK`（评分模型）
- **状态**：✅ Demo 计算工具已实现并有契约测试；正式 CRM 视图待验收

### 3. `compute_quote_deviation`
- **功能**：报价偏离度分析
- **输入**：opportunity_id
- **输出**：偏离表条款差异、竞品价格对比、方案匹配度
- **SQL 边界**：只读 `v_quotes`、`v_opportunities`
- **来源标记**：竞品价格 `source_class=MISSING`（无数据源）
- **状态**：⚠️ 竞品价格缺失时降级为 MISSING

### 4. `analyze_lead_source`
- **功能**：线索来源质量分析
- **输入**：source（可选）、period（可选）
- **输出**：各来源转化率、跟进时效、销售员转化率对比
- **SQL 边界**：只读 `v_leads`、`v_field_visits`、`v_customers`
- **来源标记**：`source_class=MOCK`（统计规则）
- **状态**：✅ Demo 计算工具已实现并有契约测试；正式 CRM 视图待验收

## 三、黄金案例完整性检查（G-E1-1 ～ G-E5-1）

### G-E1-1：商机丢单归因
- **输入**：`商机 OPP-001 最终丢单，为什么？`
- **预期工具调用**：
  1. `query_business_data`：查该商机最后 5 次跟进记录
  2. `query_business_data`：查竞品信息
  3. `query_business_data`：查报价单
  4. `query_business_data`：查商机阶段停留时长
- **预期结论**：反看商机 10 维度，定位短板（如"关键人未覆盖+报价偏高"）
- **置信度**：≥0.7
- **状态**：✅ Demo 黄金案例已执行；正式 CRM 数据待验收

### G-E2-1：业绩未达标归因
- **输入**：`华东区本月签约目标达成率仅 45%，为什么？`
- **预期工具调用**：
  1. `query_business_data`：查本月线索量 vs 上月
  2. `compute_funnel_conversion`：查漏斗各段转化率
  3. `query_business_data`：查合同金额分布
  4. `query_business_data`：查回款周期
  5. `query_business_data`：按销售员/区域下钻
- **预期结论**：定位"线索量不足" OR "转化率低" OR "客单价低" OR "回款慢"
- **状态**：✅ Demo 黄金案例已执行；正式 CRM 数据待验收

### G-E3-1：客户流失预警归因
- **输入**：`A 级客户 C-001 被回收到公海池，为什么？`
- **预期工具调用**：
  1. `query_business_data`：查近 30/60/90 天跟进次数
  2. `query_business_data`：查最后一次跟进内容质量
  3. `query_business_data`：查外勤拜访记录
  4. `score_customer_churn`：计算流失评分
- **预期结论**：跟进频率递减+最后一次敷衍打卡+无外勤 → 流失风险高
- **状态**：✅ Demo 黄金案例已执行；正式 CRM 数据待验收

### G-E4-1：报价竞争力归因
- **输入**：`最近 5 个标丢了 3 个，为什么？`
- **预期工具调用**：
  1. `query_business_data`：查 5 个标的偏离表
  2. `compute_quote_deviation`：竞品中标价 vs 我方报价
  3. `query_business_data`：查方案匹配度
  4. `query_business_data`：查历史中标/丢标规律
- **预期结论**：偏离表商务条款偏差大+报价高于竞品 10%
- **状态**：⚠️ 竞品价格 MISSING 时降级

### G-E5-1：线索质量归因
- **输入**：`本月线索转化率只有 8%（历史均值 15%），为什么？`
- **预期工具调用**：
  1. `analyze_lead_source`：查线索来源分布
  2. `query_business_data`：查跟进时效
  3. `query_business_data`：查各销售员线索转化率对比
  4. `compute_funnel_conversion`：查全链路漏斗
- **预期结论**：某来源线索质量差+跟进时效超时+漏斗在"线索→客户"段流失最大
- **状态**：✅ Demo 黄金案例已执行；正式 CRM 数据待验收

## 四、数据接入边界确认

### CRM 真实库路径
- **期望路径**：`D:\heimaAI\PytorchSDXX\CRMProject_c\data\crm_database.db`
- **当前状态**：应用代码支持 `ATTRIBUTION_CRM_DB_PATH` 注入；本轮未对真实 CRM 文件执行连接验收
- **验收边界**：真实库必须通过只读快照接入，不能作为归因系统运行库

### 数据量确认
- `customers`：预期 3663 条
- `opportunities`：预期 100 条
- `contracts`：预期 106 条
- `sales_orders`：预期 3359 条
- `field_visits`：预期 2643 条
- `sales_persons`：预期 74 条

### 安全边界
- ✅ 只读快照访问，任何写操作在适配器层拒绝
- ✅ 销售策略规则（商机阶段、客户回收、跟进时效）首版 MOCK
- ✅ 竞品中标价、行业基准默认 MISSING，缺失时输出"待补充数据/人工复核"
- ✅ 售前结论只输出建议，不产生任何自动系统动作

## 五、评审阻塞项

### 必须解决（B1 门禁）
1. ⚠️ 白名单视图字段完整性需在真实 CRM 快照确认
2. ✅ 售前工具注册表设计评审材料已形成
3. ✅ CRM 路径已具备环境变量注入边界；真实库连接验收仍待执行
4. ✅ G-E1-1～G-E5-1 Demo 黄金案例已执行通过

### 可延后（实现阶段）
1. 竞品价格数据源（G-E4-1 降级方案已有）
2. 线索表结构确认（可能需要从 field_visits 推导）
3. 销售策略规则从 MOCK 升级到 FACT（需找到原始制度）

## 六、下一步行动

### 立即可做
1. ✅ 创建售前适配器端口定义：`ports/presales.py`
2. ✅ 实现售前工具集：`application/tools/presales.py`
3. ✅ 黄金案例测试框架：`tests/test_s9_presales.py`

### 需人工输入
1. ❌ **定位 CRM 真实库路径**（阻塞）
2. ⚠️ 白名单视图 SQL 定义评审
3. ⚠️ 黄金案例期望输出细化

## 七、评审材料清单

- [x] 设计文档：`03_技术方案与架构.md` § 七
- [x] 数据模型：`02_数据模型与黄金数据集.md` 场景 E
- [x] 切片规划：`04_垂直切片规划.md` § 五
- [ ] 白名单视图 SQL 定义（待补充）
- [ ] CRM 库 Schema 文档（待补充）
- [ ] 黄金案例详细输入输出（待细化）

## 八、本轮可复现实证（2026-08-17）

- 命令：`.venv\\Scripts\\python.exe -m pytest -q tests/test_s9_presales.py`
- 结果：`11 passed`
- 证据范围：Demo CRM、MOCK 规则、固定 seed 数据
- 结论：S9 本地演示闭环已形成；真实 CRM 只读视图、FACT 规则和生产数据接入仍未完成
