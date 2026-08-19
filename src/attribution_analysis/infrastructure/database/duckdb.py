"""DuckDB 数据库生命周期与项目内模拟数据初始化。"""
from pathlib import Path
from urllib.parse import unquote, urlsplit

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR PRIMARY KEY, promised_date VARCHAR NOT NULL, delivered_date VARCHAR NOT NULL, delay_days INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory (
    sku VARCHAR PRIMARY KEY, available_qty INTEGER NOT NULL, requested_qty INTEGER NOT NULL
);
"""

SEED = (
    ("ORD-1001", "2026-03-01", "2026-03-05", 4),
    ("ORD-1002", "2026-03-02", "2026-03-02", 0),
)

# S3 售后共享证据底座：表结构对齐 `02_数据模型与黄金数据集.md` 一.1 场景A/C
AFTER_SALES_SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    vin VARCHAR PRIMARY KEY, vehicle_model VARCHAR NOT NULL, delivery_date VARCHAR NOT NULL,
    customer_id VARCHAR NOT NULL, contract_id VARCHAR NOT NULL, battery_software_version VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS work_orders (
    wo_id VARCHAR PRIMARY KEY, vin VARCHAR NOT NULL, fault_code VARCHAR, fault_desc VARCHAR,
    fault_date VARCHAR, mileage REAL, meter_replaced BOOLEAN DEFAULT FALSE, meter_calibrated BOOLEAN DEFAULT FALSE,
    prev_wo_id VARCHAR, ticket_type VARCHAR NOT NULL, tech_id VARCHAR, service_station_code VARCHAR,
    status VARCHAR NOT NULL, created_at VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id VARCHAR PRIMARY KEY, wo_id VARCHAR NOT NULL, vin VARCHAR NOT NULL, repair_process_desc VARCHAR,
    fault_desc VARCHAR, parts_list_json VARCHAR, labor_hours REAL, labor_rate REAL, labor_amount REAL,
    parts_amount REAL, discount_amount REAL, discount_coefficient REAL, customer_id VARCHAR,
    service_station_code VARCHAR, claim_amount REAL, claim_reason VARCHAR, claim_status VARCHAR,
    total_mileage REAL, submit_count INTEGER DEFAULT 0, resubmitted_at VARCHAR,
    authorization_status VARCHAR DEFAULT '草稿', destruction_notice_generated BOOLEAN DEFAULT FALSE,
    audit_date VARCHAR, rule_version VARCHAR, created_at VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS parts_master (
    part_no VARCHAR PRIMARY KEY, part_name VARCHAR NOT NULL, assembly VARCHAR NOT NULL,
    warranty_type VARCHAR NOT NULL, warranty_months INTEGER, warranty_mileage REAL, is_original BOOLEAN NOT NULL
);
CREATE TABLE IF NOT EXISTS maintenance_records (
    id VARCHAR PRIMARY KEY, vin VARCHAR NOT NULL, maintenance_type VARCHAR NOT NULL,
    mileage_at_service REAL NOT NULL, service_date VARCHAR NOT NULL, wo_id VARCHAR
);
CREATE TABLE IF NOT EXISTS warranty_manuals (
    id VARCHAR PRIMARY KEY, vehicle_model VARCHAR NOT NULL, assembly VARCHAR NOT NULL,
    part_no VARCHAR NOT NULL, warranty_months INTEGER NOT NULL, warranty_mileage REAL NOT NULL,
    exclusion_clause VARCHAR
);
CREATE TABLE IF NOT EXISTS extended_warranty (
    id VARCHAR PRIMARY KEY, vin VARCHAR NOT NULL, part_no VARCHAR NOT NULL,
    extended_months INTEGER NOT NULL, extended_mileage REAL NOT NULL, purchase_date VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS battery_health (
    id VARCHAR PRIMARY KEY, vin VARCHAR NOT NULL, soh REAL, cycle_count INTEGER, capacity REAL,
    degradation_rate REAL, soc REAL, test_date VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id VARCHAR PRIMARY KEY, supplier_name VARCHAR NOT NULL, defect_rate REAL, warranty_months INTEGER
);
CREATE TABLE IF NOT EXISTS part_batches (
    batch_id VARCHAR PRIMARY KEY, part_no VARCHAR NOT NULL, supplier_id VARCHAR NOT NULL,
    total_units INTEGER NOT NULL, failed_units INTEGER NOT NULL, defect_rate REAL NOT NULL
);
"""

# S3 固定 seed=42 模拟样例：覆盖黄金集 G-A-1~G-A-7、G-C-1 所需关键数据
AFTER_SALES_SEED = {
    "vehicles": (
        ("LSGAB52R7DF000001", "T5轻卡", "2024-01-15", "CUST-001", "CT-001", "BMS-2.4.1"),
        ("LSGAB52R7DF000002", "T5轻卡", "2023-06-01", "CUST-002", "CT-002", "BMS-2.4.1"),
        ("LSGAB52R7DF000003", "T5轻卡", "2023-06-01", "CUST-003", "CT-003", "BMS-2.4.1"),
        ("LSGAB52R7DF000004", "T5轻卡", "2022-09-10", "CUST-004", "CT-004", "BMS-2.3.0"),
        ("LSGAB52R7DF000005", "T5轻卡", "2022-09-10", "CUST-005", "CT-005", "BMS-2.3.0"),
        ("LSGAB52R7DF000006", "T5轻卡", "2021-03-20", "CUST-006", "CT-006", "BMS-2.1.0"),
    ),
    "work_orders": (
        ("WO-001", "LSGAB52R7DF000001", "E104", "电池包SOC异常", "2024-02-10", 35000, False, False, None, "报修", "TECH-01", "SS-001", "closed", "2024-02-10"),
        ("WO-002", "LSGAB52R7DF000002", "E104", "电池包SOC异常", "2023-07-01", 52000, False, False, None, "报修", "TECH-01", "SS-001", "closed", "2023-07-01"),
        ("WO-003", "LSGAB52R7DF000003", "E104", "电池包SOC异常", "2023-08-15", 68000, False, False, None, "报修", "TECH-02", "SS-002", "closed", "2023-08-15"),
        ("WO-004", "LSGAB52R7DF000004", "E105", "电池包容量衰减", "2023-11-05", 95000, False, False, None, "报修", "TECH-02", "SS-002", "closed", "2023-11-05"),
        ("WO-005", "LSGAB52R7DF000005", "E105", "电池包容量衰减", "2024-01-20", 105000, False, False, None, "报修", "TECH-01", "SS-001", "closed", "2024-01-20"),
        ("WO-006", "LSGAB52R7DF000006", "E104", "电池包SOC异常", "2022-06-01", 3000, True, False, "WO-007", "报修", "TECH-03", "SS-003", "closed", "2022-06-01"),
        ("WO-007", "LSGAB52R7DF000006", None, "换表", "2022-06-01", 80000, False, False, None, "换表", "TECH-03", "SS-003", "closed", "2022-06-01"),
        ("WO-008", "LSGAB52R7DF000006", None, "换表", "2022-09-01", 50000, False, False, None, "换表", "TECH-03", "SS-003", "closed", "2022-09-01"),
        ("WO-009", "LSGAB52R7DF000001", None, "保养", "2024-04-01", 37000, False, False, None, "保养", "TECH-01", "SS-001", "closed", "2024-04-01"),
        ("WO-010", "LSGAB52R7DF000002", None, "保养", "2023-09-01", 54000, False, False, None, "保养", "TECH-01", "SS-001", "closed", "2023-09-01"),
    ),
    "claims": (
        ("CL-001", "WO-001", "LSGAB52R7DF000001", "更换电池包模组", "电池包SOC异常", '[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',
         4.0, 120, 480, 32000, 0, 1.0, "CUST-001", "SS-001", 32480, "保内电池异常", "已提交", 35000, 0, None, "草稿", False, None, "warranty.t5.v1", "2024-02-12"),
        ("CL-002", "WO-002", "LSGAB52R7DF000002", "更换电池包模组", "电池包SOC异常", '[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',
         4.0, 120, 480, 32000, 0, 1.0, "CUST-002", "SS-001", 32480, "超保延保覆盖", "已提交", 120000, 0, None, "草稿", False, None, "warranty.t5.v1", "2023-07-03"),
        ("CL-003", "WO-003", "LSGAB52R7DF000003", "更换电池包模组", "电池包SOC异常", '[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',
         4.0, 120, 480, 32000, 0, 1.0, "CUST-003", "SS-002", 32480, "超保无延保", "已提交", 120000, 0, None, "草稿", False, None, "warranty.t5.v1", "2023-08-17"),
        ("CL-004", "WO-004", "LSGAB52R7DF000004", "更换电池包模组", "电池包容量衰减", '[]',
         3.0, 120, 360, 28000, 0, 1.0, "CUST-004", "SS-002", 28360, "保内但非原厂件", "已提交", 95000, 0, None, "草稿", False, None, "warranty.t5.v1", "2023-11-08"),
        ("CL-005", "WO-005", "LSGAB52R7DF000005", "更换电池包模组", "电池包容量衰减", '[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',
         4.0, 120, 480, 32000, 0, 1.0, "CUST-005", "SS-001", 32480, "电池健康度异常", "待补充", 105000, 0, None, "草稿", False, None, "warranty.t5.v1", "2024-01-22"),
        ("CL-006", "WO-006", "LSGAB52R7DF000006", "更换电池包模组", "电池包SOC异常", '[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',
         4.0, 120, 480, 32000, 0, 1.0, "CUST-006", "SS-003", 32480, "换表里程叠加超保", "已提交", 3000, 0, None, "草稿", False, None, "warranty.t5.v1", "2022-06-03"),
        ("CL-007", "WO-005", "LSGAB52R7DF000005", "更换电池包模组", "电池包容量衰减", '[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',
         4.0, 120, 480, 32000, 0, 1.0, "CUST-005", "SS-001", 32480, "普通索赔重新授权", "已拒绝", 105000, 1, None, "已拒绝", False, "2023-01-10", "reauthorize.v1.0", "2024-02-01"),
    ),
    "parts_master": (
        ("P-201", "电池包模组", "动力电池", "standard", 36, 100000, True),
        ("P-202", "电池包模组-延保", "动力电池", "extended", 60, 150000, True),
        ("P-101", "驱动电机", "动力系统", "standard", 36, 100000, True),
        ("P-301", "空调压缩机", "空调系统", "standard", 36, 100000, True),
        ("P-401", "制动总泵", "制动系统", "standard", 36, 100000, True),
        ("P-501", "车灯总成", "车身电气", "standard", 12, 30000, True),
        ("P-601", "雨刮电机", "车身电气", "standard", 12, 30000, True),
        ("P-701", "非原厂电池模组", "动力电池", "excluded", 0, 0, False),
    ),
    "maintenance_records": (
        ("M-001", "LSGAB52R7DF000001", "首保", 4800, "2024-04-20", "WO-009"),
        ("M-002", "LSGAB52R7DF000001", "定保", 35000, "2024-02-10", "WO-001"),
        ("M-003", "LSGAB52R7DF000002", "首保", 5000, "2023-09-01", "WO-010"),
        ("M-004", "LSGAB52R7DF000003", "定保", 30000, "2023-08-15", "WO-003"),
        ("M-005", "LSGAB52R7DF000004", "定保", 30000, "2023-11-05", "WO-004"),
        ("M-006", "LSGAB52R7DF000005", "首保", 15000, "2023-10-01", None),
        ("M-007", "LSGAB52R7DF000006", "首保", 2500, "2022-06-01", "WO-006"),
    ),
    "warranty_manuals": (
        ("WM-001", "T5轻卡", "动力电池", "P-201", 36, 100000, "自然衰减/人为损坏除外"),
        ("WM-002", "T5轻卡", "动力电池", "P-202", 60, 150000, "延保条款"),
        ("WM-003", "T5轻卡", "动力系统", "P-101", 36, 100000, None),
        ("WM-004", "T5轻卡", "空调系统", "P-301", 36, 100000, None),
        ("WM-005", "T5轻卡", "制动系统", "P-401", 36, 100000, None),
        ("WM-006", "T5轻卡", "车身电气", "P-501", 12, 30000, None),
        ("WM-007", "T5轻卡", "车身电气", "P-601", 12, 30000, None),
        ("WM-008", "T5轻卡", "动力电池", "P-701", 0, 0, "非原厂件不保"),
    ),
    "extended_warranty": (
        ("EW-001", "LSGAB52R7DF000002", "P-201", 60, 150000, "2023-07-01"),
        ("EW-002", "LSGAB52R7DF000003", "P-201", 60, 150000, "2023-08-15"),
    ),
    "battery_health": (
        ("BH-001", "LSGAB52R7DF000001", 92.0, 300, 100.0, 0.08, 55.0, "2024-02-10"),
        ("BH-002", "LSGAB52R7DF000002", 88.0, 520, 98.0, 0.12, 48.0, "2023-07-01"),
        ("BH-003", "LSGAB52R7DF000003", 90.0, 480, 99.0, 0.10, 50.0, "2023-08-15"),
        ("BH-004", "LSGAB52R7DF000004", 85.0, 700, 96.0, 0.15, 45.0, "2023-11-05"),
        ("BH-005", "LSGAB52R7DF000005", 70.0, 1200, 82.0, 0.30, 30.0, "2024-01-20"),
        ("BH-006", "LSGAB52R7DF000006", 80.0, 900, 90.0, 0.20, 40.0, "2022-06-01"),
    ),
    "suppliers": (
        ("SUP-001", "宁德时代", 0.02, 36),
        ("SUP-002", "比亚迪弗迪", 0.02, 36),
        ("SUP-003", "国轩高科", 0.03, 36),
        ("SUP-004", "中创新航", 0.03, 36),
        ("SUP-005", "瑞浦兰钧", 0.08, 36),
    ),
    "part_batches": (
        ("B-2024-Q1", "P-201", "SUP-005", 200, 16, 0.08),
    ),
}

# S9 售前模拟黄金数据集：对齐瑞能 CRM 6 表结构，覆盖 G-E1-1～G-E5-1
# 全部标记 MOCK（seed=42 可复现），竞品/行业基准 MISSING 降级
PRE_SALES_SCHEMA = """
CREATE TABLE IF NOT EXISTS pre_customers (
    id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, region VARCHAR NOT NULL,
    source VARCHAR, grade VARCHAR, created_at VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS pre_sales_persons (
    id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, dept_name VARCHAR, is_active VARCHAR
);
CREATE TABLE IF NOT EXISTS pre_opportunities (
    id VARCHAR PRIMARY KEY, customer_id VARCHAR NOT NULL, owner_id VARCHAR NOT NULL,
    stage VARCHAR NOT NULL, amount REAL NOT NULL, created_at VARCHAR NOT NULL,
    updated_at VARCHAR, product_category VARCHAR, competitors VARCHAR
);
CREATE TABLE IF NOT EXISTS pre_contracts (
    id VARCHAR PRIMARY KEY, customer_id VARCHAR NOT NULL, sign_date VARCHAR NOT NULL, amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pre_sales_orders (
    id VARCHAR PRIMARY KEY, owner_id VARCHAR NOT NULL, order_date VARCHAR NOT NULL,
    amount REAL NOT NULL, received_amount REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pre_field_visits (
    id VARCHAR PRIMARY KEY, opportunity_id VARCHAR, customer_id VARCHAR NOT NULL,
    visit_date VARCHAR NOT NULL, visit_type VARCHAR, content VARCHAR
);
CREATE TABLE IF NOT EXISTS pre_sales_targets (
    owner_id VARCHAR NOT NULL, period VARCHAR NOT NULL, target_amount REAL NOT NULL
);
"""

# seed=42 固定数据：5 个黄金案例的痛点信号全部埋入
PRE_SALES_SEED = {
    "pre_customers": (
        ("C-001", "华东科技", "华东", "广告", "A", "2024-01-15"),
        ("C-002", "华南实业", "华东", "转介绍", "B", "2024-02-01"),
        ("C-003", "华东集团", "华东", "广告", "A", "2024-03-10"),
        ("C-004", "华南贸易", "华南", "展会", "B", "2024-01-20"),
        ("C-005", "华南物流", "华南", "广告", "C", "2024-04-01"),
        ("C-006", "华东创新", "华东", "推广", "A", "2024-06-01"),
    ),
    "pre_sales_persons": (
        ("S-001", "张三", "华东", "1"),
        ("S-002", "李四", "华东", "1"),
        ("S-003", "王五", "华南", "1"),
        ("S-004", "赵六", "华南", "1"),
    ),
    "pre_opportunities": (
        # G-E1-1：OPP-001 丢单——关键人未覆盖 + 报价偏高 11% + 阶段停留 45 天
        ("OPP-001", "C-001", "S-001", "丢单", 500000, "2024-01-01", "2024-03-15", "电池包", "竞品A报价450000"),
        # G-E2-1：OPP-002/007 成交（对照组）
        ("OPP-002", "C-002", "S-001", "成交", 300000, "2024-02-01", "2024-03-01", "电控", ""),
        # G-E4-1：OPP-003 丢单——报价高于竞品 14%
        ("OPP-003", "C-003", "S-002", "丢单", 800000, "2024-03-01", "2024-05-20", "电池包", "竞品B报价700000"),
        # G-E4-1：OPP-004 丢单——报价高于竞品 14%
        ("OPP-004", "C-004", "S-003", "丢单", 200000, "2024-03-15", "2024-05-10", "电机", "竞品A报价175000"),
        # G-E4-1：OPP-005 丢单——报价高于竞品 15%
        ("OPP-005", "C-005", "S-003", "丢单", 150000, "2024-04-01", "2024-06-01", "电控", "竞品C报价130000"),
        ("OPP-006", "C-002", "S-001", "跟进", 250000, "2024-05-01", "2024-07-01", "电池包", ""),
        ("OPP-007", "C-006", "S-002", "成交", 600000, "2024-06-01", "2024-07-15", "电池包", ""),
        ("OPP-008", "C-003", "S-001", "跟进", 400000, "2024-07-01", "2024-08-01", "电机", ""),
        # G-E1-1：OPP-009 丢单——报价偏高 9%
        ("OPP-009", "C-004", "S-004", "丢单", 350000, "2024-04-10", "2024-06-15", "电池包", "竞品B报价320000"),
        # G-E4-1：OPP-010 丢单——报价偏高 12.5%
        ("OPP-010", "C-001", "S-002", "丢单", 450000, "2024-05-15", "2024-07-20", "电池包", "竞品A报价400000"),
    ),
    "pre_contracts": (
        ("CT-001", "C-002", "2024-03-01", 300000),
        ("CT-002", "C-006", "2024-07-15", 600000),
        ("CT-003", "C-003", "2024-06-01", 200000),
        ("CT-004", "C-001", "2024-02-01", 150000),
    ),
    "pre_sales_orders": (
        # 华东区（S-001/S-002）：目标达成率 45% 的埋点
        ("SO-001", "S-001", "2024-08-01", 30000, 30000),
        ("SO-002", "S-001", "2024-08-05", 15000, 10000),
        ("SO-003", "S-001", "2024-08-10", 0, 0),
        ("SO-004", "S-002", "2024-08-02", 25000, 25000),
        ("SO-005", "S-002", "2024-08-08", 11000, 5000),
        ("SO-006", "S-001", "2024-07-15", 40000, 35000),
        ("SO-007", "S-001", "2024-07-20", 20000, 15000),
        ("SO-008", "S-002", "2024-07-10", 35000, 30000),
        # 华南区（S-003/S-004）：达成率 70%
        ("SO-009", "S-003", "2024-08-03", 50000, 50000),
        ("SO-010", "S-003", "2024-08-12", 30000, 20000),
        ("SO-011", "S-004", "2024-08-05", 40000, 35000),
        ("SO-012", "S-004", "2024-08-15", 20000, 10000),
        ("SO-013", "S-003", "2024-07-08", 60000, 55000),
        ("SO-014", "S-004", "2024-07-12", 45000, 40000),
        # 回款慢的合同（G-E2-1 回款维度）
        ("SO-015", "S-001", "2024-05-01", 100000, 0),
        ("SO-016", "S-001", "2024-06-01", 80000, 0),
    ),
    "pre_field_visits": (
        # G-E3-1：C-001 跟进递减 90 天 5→2→0，最后一次敷衍，无外勤
        ("FV-001", "OPP-001", "C-001", "2024-01-20", "电话", "初步沟通需求"),
        ("FV-002", "OPP-001", "C-001", "2024-02-01", "拜访", "演示产品方案"),
        ("FV-003", "OPP-001", "C-001", "2024-02-15", "电话", "跟进报价"),
        ("FV-004", "OPP-001", "C-001", "2024-03-01", "电话", "客户说再考虑"),
        ("FV-005", "OPP-001", "C-001", "2024-03-10", "电话", "敷衍打卡 - 客户已接触竞品"),
        # 无外勤记录给 C-001（近 90 天 visit_type=拜访 为 0）
        # G-E1-1：OPP-001 跟进记录（最后 5 次）
        ("FV-006", "OPP-001", "C-001", "2024-03-12", "电话", "客户态度变化，竞品报价更低"),
        ("FV-007", "OPP-001", "C-001", "2024-03-14", "电话", "最终确认丢单"),
        # 正常客户跟进
        ("FV-008", "OPP-002", "C-002", "2024-02-10", "拜访", "现场考察"),
        ("FV-009", "OPP-002", "C-002", "2024-02-20", "电话", "确认需求"),
        ("FV-010", "OPP-002", "C-002", "2024-02-25", "拜访", "签约"),
        ("FV-011", "OPP-003", "C-003", "2024-03-10", "拜访", "产品演示"),
        ("FV-012", "OPP-003", "C-003", "2024-04-01", "电话", "报价沟通"),
        ("FV-013", "OPP-007", "C-006", "2024-06-10", "拜访", "初次接触"),
        ("FV-014", "OPP-007", "C-006", "2024-06-25", "拜访", "技术交流"),
        ("FV-015", "OPP-007", "C-006", "2024-07-05", "电话", "确认合同"),
        ("FV-016", "OPP-008", "C-003", "2024-07-10", "拜访", "跟进现有项目"),
        ("FV-017", "OPP-004", "C-004", "2024-04-01", "拜访", "初次沟通"),
        ("FV-018", "OPP-004", "C-004", "2024-04-20", "电话", "报价"),
        ("FV-019", "OPP-005", "C-005", "2024-04-10", "电话", "初步沟通"),
        ("FV-020", "OPP-006", "C-002", "2024-05-10", "拜访", "维护关系"),
        # 华南区跟进
        ("FV-021", "OPP-009", "C-004", "2024-04-15", "拜访", "需求沟通"),
        ("FV-022", "OPP-009", "C-004", "2024-05-01", "电话", "报价"),
        ("FV-023", "OPP-010", "C-001", "2024-05-20", "电话", "竞品对接"),
    ),
    "pre_sales_targets": (
        # 华东区 S-001：月目标 10 万，签约 4.5 万（45%）
        ("S-001", "2024-08", 100000),
        # 华东区 S-002：月目标 8 万，签约 3.6 万（45%）
        ("S-002", "2024-08", 80000),
        # 华南区 S-003：月目标 10 万，签约 8 万（80%）
        ("S-003", "2024-08", 100000),
        # 华南区 S-004：月目标 8 万，签约 6 万（75%）
        ("S-004", "2024-08", 80000),
        # 年度累计目标（YTD）
        ("S-001", "2024-YTD", 800000),
        ("S-002", "2024-YTD", 640000),
        ("S-003", "2024-YTD", 800000),
        ("S-004", "2024-YTD", 640000),
    ),
}


def open_database(path: str | Path) -> duckdb.DuckDBPyConnection:
    """打开（或创建）项目内演示 DuckDB 库，并保证 schema 与 seed 就绪。"""
    connection = duckdb.connect(str(path))
    connection.execute(SCHEMA)
    row = connection.execute("SELECT COUNT(*) FROM orders").fetchone()
    if row is not None and row[0] == 0:
        connection.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", SEED)
        connection.executemany("INSERT INTO inventory VALUES (?, ?, ?)", (("SKU-001", 2, 10), ("SKU-002", 20, 5)))
    connection.execute(AFTER_SALES_SCHEMA)
    vehicle_row = connection.execute("SELECT COUNT(*) FROM vehicles").fetchone()
    if vehicle_row is not None and vehicle_row[0] == 0:
        for table, rows in AFTER_SALES_SEED.items():
            if rows:
                placeholders = ", ".join("?" * len(rows[0]))
                connection.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
    connection.execute(PRE_SALES_SCHEMA)
    cust_row = connection.execute("SELECT COUNT(*) FROM pre_customers").fetchone()
    if cust_row is not None and cust_row[0] == 0:
        for table, rows in PRE_SALES_SEED.items():
            if rows:
                placeholders = ", ".join("?" * len(rows[0]))
                connection.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
    return connection


# ── MySQL 支持 ─────────────────────────────────────────────

class _MySQLResult:
    """包装查询结果：行数据在锁内读取完毕，锁外只读缓存（线程安全）。"""
    def __init__(self, rows: tuple, description: object) -> None:
        """绑定结果行与列描述（均为锁内已读取的快照）。"""
        self._rows = rows
        self._index = 0
        self.description = description
    def fetchall(self):
        """返回全部结果行。"""
        return self._rows
    def fetchone(self):
        """返回下一行结果；无更多行时返回 None。"""
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row


class MySQLConnection:
    """包装 PyMySQL 连接，提供与 DuckDB 相同的 execute() 接口。

    线程安全与断线自愈：
    - PyMySQL 连接非线程安全，全局单例被 FastAPI 线程池并发访问会导致
      协议序列号错乱（Packet sequence number wrong）；本类用锁把
      execute/executemany 的完整操作（含结果读取）串行化。
    - MySQL 服务重启或空闲超时后旧连接失效，抛 InterfaceError /
      OperationalError(2006/2013) / InternalError(Packet sequence) /
      OSError(socket 操作)；此时按保存的 URL 重建连接并重试一次。
    """
    def __init__(self, conn, url: str | None = None):
        """绑定 PyMySQL 连接、保存重建 URL 并创建串行化锁。"""
        import threading
        self._conn = conn
        self._url = url
        self._lock = threading.Lock()
    def _sql(self, sql: str) -> str:
        """把 DuckDB 的 ? 占位符转换为 MySQL 的 %s。"""
        return sql.replace("?", "%s")
    def _is_connection_loss(self, exc: BaseException) -> bool:
        """判断异常是否为连接失效/破坏（可安全重连重试）。"""
        import pymysql
        if isinstance(exc, pymysql.err.InterfaceError):
            return True
        if isinstance(exc, pymysql.err.OperationalError):
            return exc.args and exc.args[0] in (2006, 2013)  # server gone away / lost connection
        if isinstance(exc, pymysql.err.InternalError):
            return "Packet sequence" in str(exc)  # 协议错乱 = 连接被破坏
        if isinstance(exc, OSError):
            return True  # socket 已关闭/非法操作（WinError 10038 等）
        if isinstance(exc, ValueError):
            return "closed file" in str(exc)  # read of closed file
        return False
    def _retry_after_reconnect(self, fn):
        """在锁内执行 fn；连接失效时按保存的 URL 重建连接并重试一次。"""
        with self._lock:
            try:
                return fn()
            except BaseException as exc:  # noqa: BLE001 - 先判断是否为连接失效
                if not self._is_connection_loss(exc) or not self._url:
                    raise
                self._conn = open_mysql(self._url)._conn
                return fn()
    def execute(self, sql: str, params: list | None = None):
        """锁内执行查询并缓存结果（兼容 fetchall/fetchone/description）。"""
        def _run():
            cursor = self._conn.cursor()
            cursor.execute(self._sql(sql), params or ())
            return _MySQLResult(tuple(cursor.fetchall()), cursor.description)
        return self._retry_after_reconnect(_run)
    def executemany(self, sql: str, params: list[tuple]):
        """批量执行插入，完成后提交事务（全程持锁）。"""
        def _run():
            cursor = self._conn.cursor()
            cursor.executemany(self._sql(sql), params)
            self._conn.commit()
        self._retry_after_reconnect(_run)
    def commit(self):
        """提交当前事务（pymysql 默认不自动提交）。"""
        with self._lock:
            self._conn.commit()
    def close(self):
        """关闭底层连接。"""
        with self._lock:
            self._conn.close()


def open_mysql(url: str) -> MySQLConnection:
    """从 mysql://user:pass@host:port/db 格式 URL 创建 MySQL 连接。"""
    import pymysql

    parsed = urlsplit(url)
    if parsed.scheme != "mysql" or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("database URL must be mysql://user:pass@host:port/database")
    password = unquote(parsed.password or "")
    database = parsed.path.strip("/")
    conn = pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=password,
        database=database,
        charset="utf8mb4",
    )
    return MySQLConnection(conn, url=url)

