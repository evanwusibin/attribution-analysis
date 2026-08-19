"""MySQL 数据库初始化：建表 + 插入模拟数据。"""
import pymysql

MYSQL_CONFIG = {"host": "127.0.0.1", "port": 3307, "user": "root", "password": "Atguigu.123", "charset": "utf8mb4"}

DDL = """CREATE TABLE IF NOT EXISTS vehicles (vin VARCHAR(50) PRIMARY KEY, vehicle_model VARCHAR(50) NOT NULL, delivery_date VARCHAR(20) NOT NULL, customer_id VARCHAR(50) NOT NULL, contract_id VARCHAR(50) NOT NULL, battery_software_version VARCHAR(50) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS work_orders (wo_id VARCHAR(50) PRIMARY KEY, vin VARCHAR(50) NOT NULL, fault_code VARCHAR(50), fault_desc VARCHAR(200), fault_date VARCHAR(20), mileage DOUBLE, meter_replaced TINYINT DEFAULT 0, meter_calibrated TINYINT DEFAULT 0, prev_wo_id VARCHAR(50), ticket_type VARCHAR(50) NOT NULL, tech_id VARCHAR(50), service_station_code VARCHAR(50), status VARCHAR(50) NOT NULL, created_at VARCHAR(20) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS claims (claim_id VARCHAR(50) PRIMARY KEY, wo_id VARCHAR(50) NOT NULL, vin VARCHAR(50) NOT NULL, repair_process_desc VARCHAR(500), fault_desc VARCHAR(200), parts_list_json TEXT, labor_hours DOUBLE, labor_rate DOUBLE, labor_amount DOUBLE, parts_amount DOUBLE, discount_amount DOUBLE, discount_coefficient DOUBLE, customer_id VARCHAR(50), service_station_code VARCHAR(50), claim_amount DOUBLE, claim_reason VARCHAR(200), claim_status VARCHAR(50), total_mileage DOUBLE, submit_count INT DEFAULT 0, resubmitted_at VARCHAR(20), authorization_status VARCHAR(50) DEFAULT '草稿', destruction_notice_generated TINYINT DEFAULT 0, audit_date VARCHAR(20), rule_version VARCHAR(50), created_at VARCHAR(20) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS parts_master (part_no VARCHAR(50) PRIMARY KEY, part_name VARCHAR(100) NOT NULL, assembly VARCHAR(100) NOT NULL, warranty_type VARCHAR(50) NOT NULL, warranty_months INT, warranty_mileage DOUBLE, is_original TINYINT NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS maintenance_records (id VARCHAR(50) PRIMARY KEY, vin VARCHAR(50) NOT NULL, maintenance_type VARCHAR(50) NOT NULL, mileage_at_service DOUBLE NOT NULL, service_date VARCHAR(20) NOT NULL, wo_id VARCHAR(50)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS warranty_manuals (id VARCHAR(50) PRIMARY KEY, vehicle_model VARCHAR(50) NOT NULL, assembly VARCHAR(100) NOT NULL, part_no VARCHAR(50) NOT NULL, warranty_months INT NOT NULL, warranty_mileage DOUBLE NOT NULL, exclusion_clause VARCHAR(500)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS extended_warranty (id VARCHAR(50) PRIMARY KEY, vin VARCHAR(50) NOT NULL, part_no VARCHAR(50) NOT NULL, extended_months INT NOT NULL, extended_mileage DOUBLE NOT NULL, purchase_date VARCHAR(20) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS battery_health (id VARCHAR(50) PRIMARY KEY, vin VARCHAR(50) NOT NULL, soh DOUBLE, cycle_count INT, capacity DOUBLE, degradation_rate DOUBLE, soc DOUBLE, test_date VARCHAR(20) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS suppliers (supplier_id VARCHAR(50) PRIMARY KEY, supplier_name VARCHAR(100) NOT NULL, defect_rate DOUBLE, warranty_months INT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS part_batches (batch_id VARCHAR(50) PRIMARY KEY, part_no VARCHAR(50) NOT NULL, supplier_id VARCHAR(50) NOT NULL, total_units INT NOT NULL, failed_units INT NOT NULL, defect_rate DOUBLE NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS pre_customers (id VARCHAR(50) PRIMARY KEY, name VARCHAR(100) NOT NULL, region VARCHAR(50) NOT NULL, source VARCHAR(50), grade VARCHAR(10), created_at VARCHAR(20) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS pre_sales_persons (id VARCHAR(50) PRIMARY KEY, name VARCHAR(100) NOT NULL, dept_name VARCHAR(50), is_active VARCHAR(10)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS pre_opportunities (id VARCHAR(50) PRIMARY KEY, customer_id VARCHAR(50) NOT NULL, owner_id VARCHAR(50) NOT NULL, stage VARCHAR(50) NOT NULL, amount DOUBLE NOT NULL, created_at VARCHAR(20) NOT NULL, updated_at VARCHAR(20), product_category VARCHAR(100), competitors VARCHAR(500)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS pre_contracts (id VARCHAR(50) PRIMARY KEY, customer_id VARCHAR(50) NOT NULL, sign_date VARCHAR(20) NOT NULL, amount DOUBLE NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS pre_sales_orders (id VARCHAR(50) PRIMARY KEY, owner_id VARCHAR(50) NOT NULL, order_date VARCHAR(20) NOT NULL, amount DOUBLE NOT NULL, received_amount DOUBLE DEFAULT 0) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS pre_field_visits (id VARCHAR(50) PRIMARY KEY, opportunity_id VARCHAR(50), customer_id VARCHAR(50) NOT NULL, visit_date VARCHAR(20) NOT NULL, visit_type VARCHAR(50), content VARCHAR(500)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS pre_sales_targets (owner_id VARCHAR(50) NOT NULL, period VARCHAR(20) NOT NULL, target_amount DOUBLE NOT NULL, PRIMARY KEY (owner_id, period)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"""

DATA = {
    "vehicles": [("LSGAB52R7DF000001","T5轻卡","2024-01-15","CUST-001","CT-001","BMS-2.4.1"),("LSGAB52R7DF000002","T5轻卡","2023-06-01","CUST-002","CT-002","BMS-2.4.1"),("LSGAB52R7DF000003","T5轻卡","2023-06-01","CUST-003","CT-003","BMS-2.4.1"),("LSGAB52R7DF000004","T5轻卡","2022-09-10","CUST-004","CT-004","BMS-2.3.0"),("LSGAB52R7DF000005","T5轻卡","2022-09-10","CUST-005","CT-005","BMS-2.3.0"),("LSGAB52R7DF000006","T5轻卡","2021-03-20","CUST-006","CT-006","BMS-2.1.0")],
    "work_orders": [("WO-001","LSGAB52R7DF000001","E104","电池包SOC异常","2024-02-10",35000,0,0,None,"报修","TECH-01","SS-001","closed","2024-02-10"),("WO-002","LSGAB52R7DF000002","E104","电池包SOC异常","2023-07-01",52000,0,0,None,"报修","TECH-01","SS-001","closed","2023-07-01"),("WO-003","LSGAB52R7DF000003","E104","电池包SOC异常","2023-08-15",68000,0,0,None,"报修","TECH-02","SS-002","closed","2023-08-15"),("WO-004","LSGAB52R7DF000004","E105","电池包容量衰减","2023-11-05",95000,0,0,None,"报修","TECH-02","SS-002","closed","2023-11-05"),("WO-005","LSGAB52R7DF000005","E105","电池包容量衰减","2024-01-20",105000,0,0,None,"报修","TECH-01","SS-001","closed","2024-01-20"),("WO-006","LSGAB52R7DF000006","E104","电池包SOC异常","2022-06-01",3000,1,0,"WO-007","报修","TECH-03","SS-003","closed","2022-06-01"),("WO-007","LSGAB52R7DF000006",None,"换表","2022-06-01",80000,0,0,None,"换表","TECH-03","SS-003","closed","2022-06-01"),("WO-008","LSGAB52R7DF000006",None,"换表","2022-09-01",50000,0,0,None,"换表","TECH-03","SS-003","closed","2022-09-01"),("WO-009","LSGAB52R7DF000001",None,"保养","2024-04-01",37000,0,0,None,"保养","TECH-01","SS-001","closed","2024-04-01"),("WO-010","LSGAB52R7DF000002",None,"保养","2023-09-01",54000,0,0,None,"保养","TECH-01","SS-001","closed","2023-09-01")],
    "claims": [("CL-001","WO-001","LSGAB52R7DF000001","更换电池包模组","电池包SOC异常",'[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',4.0,120,480,32000,0,1.0,"CUST-001","SS-001",32480,"保内电池异常","已提交",35000,0,None,"草稿",0,None,"warranty.t5.v1","2024-02-12"),("CL-002","WO-002","LSGAB52R7DF000002","更换电池包模组","电池包SOC异常",'[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',4.0,120,480,32000,0,1.0,"CUST-002","SS-001",32480,"超保延保覆盖","已提交",120000,0,None,"草稿",0,None,"warranty.t5.v1","2023-07-03"),("CL-003","WO-003","LSGAB52R7DF000003","更换电池包模组","电池包SOC异常",'[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',4.0,120,480,32000,0,1.0,"CUST-003","SS-002",32480,"超保无延保","已提交",120000,0,None,"草稿",0,None,"warranty.t5.v1","2023-08-17"),("CL-004","WO-004","LSGAB52R7DF000004","更换电池包模组","电池包容量衰减",'[]',3.0,120,360,28000,0,1.0,"CUST-004","SS-002",28360,"保内但非原厂件","已提交",95000,0,None,"草稿",0,None,"warranty.t5.v1","2023-11-08"),("CL-005","WO-005","LSGAB52R7DF000005","更换电池包模组","电池包容量衰减",'[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',4.0,120,480,32000,0,1.0,"CUST-005","SS-001",32480,"电池健康度异常","待补充",105000,0,None,"草稿",0,None,"warranty.t5.v1","2024-01-22"),("CL-006","WO-006","LSGAB52R7DF000006","更换电池包模组","电池包SOC异常",'[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',4.0,120,480,32000,0,1.0,"CUST-006","SS-003",32480,"换表里程叠加超保","已提交",3000,0,None,"草稿",0,None,"warranty.t5.v1","2022-06-03"),("CL-007","WO-005","LSGAB52R7DF000005","更换电池包模组","电池包容量衰减",'[{"part_no":"P-201","name":"电池包模组","supplier":"SUP-005","qty":1}]',4.0,120,480,32000,0,1.0,"CUST-005","SS-001",32480,"普通索赔重新授权","已拒绝",105000,1,None,"已拒绝",0,"2023-01-10","reauthorize.v1.0","2024-02-01")],
    "parts_master": [("P-201","电池包模组","动力电池","standard",36,100000,1),("P-202","电池包模组-延保","动力电池","extended",60,150000,1),("P-101","驱动电机","动力系统","standard",36,100000,1),("P-301","空调压缩机","空调系统","standard",36,100000,1),("P-401","制动总泵","制动系统","standard",36,100000,1),("P-501","车灯总成","车身电气","standard",12,30000,1),("P-601","雨刮电机","车身电气","standard",12,30000,1),("P-701","非原厂电池模组","动力电池","excluded",0,0,0)],
    "maintenance_records": [("M-001","LSGAB52R7DF000001","首保",4800,"2024-04-20","WO-009"),("M-002","LSGAB52R7DF000001","定保",35000,"2024-02-10","WO-001"),("M-003","LSGAB52R7DF000002","首保",5000,"2023-09-01","WO-010"),("M-004","LSGAB52R7DF000003","定保",30000,"2023-08-15","WO-003"),("M-005","LSGAB52R7DF000004","定保",30000,"2023-11-05","WO-004"),("M-006","LSGAB52R7DF000005","首保",15000,"2023-10-01",None),("M-007","LSGAB52R7DF000006","首保",2500,"2022-06-01","WO-006")],
    "warranty_manuals": [("WM-001","T5轻卡","动力电池","P-201",36,100000,"自然衰减/人为损坏除外"),("WM-002","T5轻卡","动力电池","P-202",60,150000,"延保条款"),("WM-003","T5轻卡","动力系统","P-101",36,100000,None),("WM-004","T5轻卡","空调系统","P-301",36,100000,None),("WM-005","T5轻卡","制动系统","P-401",36,100000,None),("WM-006","T5轻卡","车身电气","P-501",12,30000,None),("WM-007","T5轻卡","车身电气","P-601",12,30000,None),("WM-008","T5轻卡","动力电池","P-701",0,0,"非原厂件不保")],
    "extended_warranty": [("EW-001","LSGAB52R7DF000002","P-201",60,150000,"2023-07-01"),("EW-002","LSGAB52R7DF000003","P-201",60,150000,"2023-08-15")],
    "battery_health": [("BH-001","LSGAB52R7DF000001",92.0,300,100.0,0.08,55.0,"2024-02-10"),("BH-002","LSGAB52R7DF000002",88.0,520,98.0,0.12,48.0,"2023-07-01"),("BH-003","LSGAB52R7DF000003",90.0,480,99.0,0.10,50.0,"2023-08-15"),("BH-004","LSGAB52R7DF000004",85.0,700,96.0,0.15,45.0,"2023-11-05"),("BH-005","LSGAB52R7DF000005",70.0,1200,82.0,0.30,30.0,"2024-01-20"),("BH-006","LSGAB52R7DF000006",80.0,900,90.0,0.20,40.0,"2022-06-01")],
    "suppliers": [("SUP-001","宁德时代",0.02,36),("SUP-002","比亚迪弗迪",0.02,36),("SUP-003","国轩高科",0.03,36),("SUP-004","中创新航",0.03,36),("SUP-005","瑞浦兰钧",0.08,36)],
    "part_batches": [("B-2024-Q1","P-201","SUP-005",200,16,0.08)],
    "pre_customers": [("C-001","华东科技","华东","广告","A","2024-01-15"),("C-002","华南实业","华东","转介绍","B","2024-02-01"),("C-003","华东集团","华东","广告","A","2024-03-10"),("C-004","华南贸易","华南","展会","B","2024-01-20"),("C-005","华南物流","华南","广告","C","2024-04-01"),("C-006","华东创新","华东","推广","A","2024-06-01")],
    "pre_sales_persons": [("S-001","张三","华东","1"),("S-002","李四","华东","1"),("S-003","王五","华南","1"),("S-004","赵六","华南","1")],
    "pre_opportunities": [("OPP-001","C-001","S-001","丢单",500000,"2024-01-01","2024-03-15","电池包","竞品A报价450000"),("OPP-002","C-002","S-001","成交",300000,"2024-02-01","2024-03-01","电控",""),("OPP-003","C-003","S-002","丢单",800000,"2024-03-01","2024-05-20","电池包","竞品B报价700000"),("OPP-004","C-004","S-003","丢单",200000,"2024-03-15","2024-05-10","电机","竞品A报价175000"),("OPP-005","C-005","S-003","丢单",150000,"2024-04-01","2024-06-01","电控","竞品C报价130000"),("OPP-006","C-002","S-001","跟进",250000,"2024-05-01","2024-07-01","电池包",""),("OPP-007","C-006","S-002","成交",600000,"2024-06-01","2024-07-15","电池包",""),("OPP-008","C-003","S-001","跟进",400000,"2024-07-01","2024-08-01","电机",""),("OPP-009","C-004","S-004","丢单",350000,"2024-04-10","2024-06-15","电池包","竞品B报价320000"),("OPP-010","C-001","S-002","丢单",450000,"2024-05-15","2024-07-20","电池包","竞品A报价400000")],
    "pre_contracts": [("CT-001","C-002","2024-03-01",300000),("CT-002","C-006","2024-07-15",600000),("CT-003","C-003","2024-06-01",200000),("CT-004","C-001","2024-02-01",150000)],
    "pre_sales_orders": [("SO-001","S-001","2024-08-01",30000,30000),("SO-002","S-001","2024-08-05",15000,10000),("SO-003","S-001","2024-08-10",0,0),("SO-004","S-002","2024-08-02",25000,25000),("SO-005","S-002","2024-08-08",11000,5000),("SO-006","S-001","2024-07-15",40000,35000),("SO-007","S-001","2024-07-20",20000,15000),("SO-008","S-002","2024-07-10",35000,30000),("SO-009","S-003","2024-08-03",50000,50000),("SO-010","S-003","2024-08-12",30000,20000),("SO-011","S-004","2024-08-05",40000,35000),("SO-012","S-004","2024-08-15",20000,10000),("SO-013","S-003","2024-07-08",60000,55000),("SO-014","S-004","2024-07-12",45000,40000),("SO-015","S-001","2024-05-01",100000,0),("SO-016","S-001","2024-06-01",80000,0)],
    "pre_field_visits": [("FV-001","OPP-001","C-001","2024-01-20","电话","初步沟通需求"),("FV-002","OPP-001","C-001","2024-02-01","拜访","演示产品方案"),("FV-003","OPP-001","C-001","2024-02-15","电话","跟进报价"),("FV-004","OPP-001","C-001","2024-03-01","电话","客户说再考虑"),("FV-005","OPP-001","C-001","2024-03-10","电话","敷衍打卡 - 客户已接触竞品"),("FV-006","OPP-001","C-001","2024-03-12","电话","客户态度变化，竞品报价更低"),("FV-007","OPP-001","C-001","2024-03-14","电话","最终确认丢单"),("FV-008","OPP-002","C-002","2024-02-10","拜访","现场考察"),("FV-009","OPP-002","C-002","2024-02-20","电话","确认需求"),("FV-010","OPP-002","C-002","2024-02-25","拜访","签约"),("FV-011","OPP-003","C-003","2024-03-10","拜访","产品演示"),("FV-012","OPP-003","C-003","2024-04-01","电话","报价沟通"),("FV-013","OPP-007","C-006","2024-06-10","拜访","初次接触"),("FV-014","OPP-007","C-006","2024-06-25","拜访","技术交流"),("FV-015","OPP-007","C-006","2024-07-05","电话","确认合同"),("FV-016","OPP-008","C-003","2024-07-10","拜访","跟进现有项目"),("FV-017","OPP-004","C-004","2024-04-01","拜访","初次沟通"),("FV-018","OPP-004","C-004","2024-04-20","电话","报价"),("FV-019","OPP-005","C-005","2024-04-10","电话","初步沟通"),("FV-020","OPP-006","C-002","2024-05-10","拜访","维护关系"),("FV-021","OPP-009","C-004","2024-04-15","拜访","需求沟通"),("FV-022","OPP-009","C-004","2024-05-01","电话","报价"),("FV-023","OPP-010","C-001","2024-05-20","电话","竞品对接")],
    "pre_sales_targets": [("S-001","2024-08",100000),("S-002","2024-08",80000),("S-003","2024-08",100000),("S-004","2024-08",80000),("S-001","2024-YTD",800000),("S-002","2024-YTD",640000),("S-003","2024-YTD",800000),("S-004","2024-YTD",640000)],
}

SQL = {
    "vehicles": "INSERT INTO vehicles VALUES (%s,%s,%s,%s,%s,%s)",
    "work_orders": "INSERT INTO work_orders VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    "claims": "INSERT INTO claims VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    "parts_master": "INSERT INTO parts_master VALUES (%s,%s,%s,%s,%s,%s,%s)",
    "maintenance_records": "INSERT INTO maintenance_records VALUES (%s,%s,%s,%s,%s,%s)",
    "warranty_manuals": "INSERT INTO warranty_manuals VALUES (%s,%s,%s,%s,%s,%s,%s)",
    "extended_warranty": "INSERT INTO extended_warranty VALUES (%s,%s,%s,%s,%s,%s)",
    "battery_health": "INSERT INTO battery_health VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
    "suppliers": "INSERT INTO suppliers VALUES (%s,%s,%s,%s)",
    "part_batches": "INSERT INTO part_batches VALUES (%s,%s,%s,%s,%s,%s)",
    "pre_customers": "INSERT INTO pre_customers VALUES (%s,%s,%s,%s,%s,%s)",
    "pre_sales_persons": "INSERT INTO pre_sales_persons VALUES (%s,%s,%s,%s)",
    "pre_opportunities": "INSERT INTO pre_opportunities VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    "pre_contracts": "INSERT INTO pre_contracts VALUES (%s,%s,%s,%s)",
    "pre_sales_orders": "INSERT INTO pre_sales_orders VALUES (%s,%s,%s,%s,%s)",
    "pre_field_visits": "INSERT INTO pre_field_visits VALUES (%s,%s,%s,%s,%s,%s)",
    "pre_sales_targets": "INSERT INTO pre_sales_targets VALUES (%s,%s,%s)",
}

def init():
    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        with conn.cursor() as c:
            c.execute("CREATE DATABASE IF NOT EXISTS attribution")
        conn.select_db("attribution")
        with conn.cursor() as c:
            for s in DDL.split(";"):
                s = s.strip()
                if s: c.execute(s)
        conn.commit()
        print("✅ 表结构创建完成")
        with conn.cursor() as c:
            for table, sql in SQL.items():
                rows = DATA[table]
                c.execute(f"SELECT COUNT(*) FROM {table}")
                if c.fetchone()[0] == 0:
                    for row in rows:
                        c.execute(sql, row)
                    print(f"  ✅ {table}: {len(rows)} 条")
                else:
                    print(f"  ⏭️  {table}: 已有数据")
        conn.commit()
        print("✅ 数据插入完成")
    finally:
        conn.close()

if __name__ == "__main__":
    init()
    print("🎉 MySQL 初始化完成")