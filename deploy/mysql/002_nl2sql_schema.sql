CREATE DATABASE IF NOT EXISTS attribution_meta CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE attribution_meta;
CREATE TABLE IF NOT EXISTS table_info (
  id VARCHAR(64) PRIMARY KEY, name VARCHAR(128) NOT NULL, role VARCHAR(32) NOT NULL, description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS column_info (
  id VARCHAR(64) PRIMARY KEY, name VARCHAR(128) NOT NULL, type VARCHAR(64) NOT NULL, role VARCHAR(32) NOT NULL,
  examples JSON NOT NULL, description TEXT NOT NULL, alias JSON NOT NULL, table_id VARCHAR(64) NOT NULL
);
CREATE TABLE IF NOT EXISTS metric_info (
  id VARCHAR(64) PRIMARY KEY, name VARCHAR(128) NOT NULL, description TEXT NOT NULL,
  relevant_columns JSON NOT NULL, alias JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS column_metric (
  column_id VARCHAR(64) NOT NULL, metric_id VARCHAR(64) NOT NULL, PRIMARY KEY (column_id, metric_id)
);

USE attribution_business;
CREATE TABLE IF NOT EXISTS dim_region (region_id VARCHAR(32) PRIMARY KEY, province VARCHAR(32), region_name VARCHAR(32), country VARCHAR(32));
CREATE TABLE IF NOT EXISTS dim_customer (customer_id VARCHAR(32) PRIMARY KEY, customer_name VARCHAR(64), gender VARCHAR(16), member_level VARCHAR(16));
CREATE TABLE IF NOT EXISTS dim_product (product_id VARCHAR(32) PRIMARY KEY, product_name VARCHAR(64), category VARCHAR(64), brand VARCHAR(64));
CREATE TABLE IF NOT EXISTS dim_date (date_id VARCHAR(8) PRIMARY KEY, year INT, quarter VARCHAR(8), month INT, day INT);
CREATE TABLE IF NOT EXISTS fact_order (
  order_id VARCHAR(32) PRIMARY KEY, customer_id VARCHAR(32), product_id VARCHAR(32), date_id VARCHAR(8), region_id VARCHAR(32),
  order_quantity INT NOT NULL, order_amount DECIMAL(12,2) NOT NULL
);
INSERT IGNORE INTO dim_region VALUES ('R001', '广东', '华南', '中国'), ('R002', '北京', '华北', '中国');
INSERT IGNORE INTO dim_customer VALUES ('C001', '张三', '男', '黄金'), ('C002', '李四', '女', '普通');
INSERT IGNORE INTO dim_product VALUES ('P001', '电池包检测服务', '售后服务', '归因演示'), ('P002', '交付保障服务', '售后服务', '归因演示');
INSERT IGNORE INTO dim_date VALUES ('20260301', 2026, 'Q1', 3, 1), ('20260302', 2026, 'Q1', 3, 2);
INSERT IGNORE INTO fact_order VALUES ('FO001', 'C001', 'P001', '20260301', 'R001', 2, 2999.00), ('FO002', 'C002', 'P002', '20260302', 'R002', 1, 1599.00);
