CREATE TABLE IF NOT EXISTS orders (
  order_id VARCHAR(64) PRIMARY KEY,
  promised_date DATE NOT NULL,
  delivered_date DATE NOT NULL,
  delay_days INT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory (
  sku VARCHAR(64) PRIMARY KEY,
  available_qty INT NOT NULL,
  requested_qty INT NOT NULL
);
INSERT IGNORE INTO orders VALUES
  ('ORD-1001', '2026-03-01', '2026-03-05', 4),
  ('ORD-1002', '2026-03-02', '2026-03-02', 0);
INSERT IGNORE INTO inventory VALUES
  ('SKU-001', 2, 10),
  ('SKU-002', 20, 5);
