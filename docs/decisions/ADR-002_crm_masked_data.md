# ADR-002 · 真实 CRM 数据脱敏口径适配

> **状态**：accepted（2026-08-17）
> **影响范围**：`adapters/crm/mysql.py`、售前场景服务
> **逆转成本**：低（仅影响查询逻辑）

## 背景

瑞能 CRM 真实库 `crm_database.db` 迁移到 MySQL 后发现数据经过**脱敏处理**：

| 字段 | 脱敏情况 |
|---|---|
| `customer_id` / `owner_id` / `visitor_id` / `opportunity_id` | 部分清空（NULL） |
| `customer_name` | 替换为 `**` |
| `order_date` / `delivery_date` / `acceptance_date` | 全部 NULL |
| `first_deal_date` | 全部 NULL |

直接按原设计查询（按 owner_id 聚合业绩、按 first_deal_date 判断成交）会得到空结果。

## 决策

`MysqlCrmAdapter` 适配可用字段：

| 原始意图 | 适配方案 |
|---|---|
| 销售业绩按人聚合 | 改为按部门 `owner_dept` 聚合（sales_persons.dept_name ↔ sales_orders.owner_dept） |
| 订单时间（order_date） | 改用 `created_at`（有完整数据） |
| 客户成交判断（first_deal_date） | 改用 `deal_status`（已成交/多次成交/未成交） |
| 拜访判断（visit_type = '拜访'） | 改用 `LIKE '%拜访%'`（真实值是 签到-出差拜访报告 等） |
| 销售员激活（is_active = '1'） | 改用 `is_active = '在职'` |
| 商机跟进（opportunity_id） | 退化按 customer_id 匹配（opportunity_id 被清空） |

时间维度错位问题：订单 `created_at` 是 2025 年、目标是 2026 年 → 业绩统计退化为全量对比（不按当前年月过滤）。

## 后果

### 正面
- 售前 E1-E5 场景用真实数据跑通（线索来源转化率、部门业绩对比、客户流失评分）
- 72+ 测试通过，含真实数据适配器验证

### 负面
- 业绩达成率是"全量对比"而非"当月达成"，口径需向业务方说明
- 商机跟进记录无法精确到单个商机（opportunity_id 丢失）
- `crm_*` 表的完整字段结构依赖脱敏前的 SQLite 源库

## 备选方案

- **等待未脱敏数据**：需要用户重新提供原始库，阻塞当前进度
- **用模拟数据替代**：失去"真实数据验证"的价值，用户明确要求用真实数据