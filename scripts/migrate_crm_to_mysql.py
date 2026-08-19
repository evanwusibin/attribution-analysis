"""将瑞能 CRM 真实数据从 SQLite 迁移到 MySQL。"""
import sqlite3, pymysql

SQLITE_PATH = "D:/heimaAI/PytorchSDXX/CRMProject/CRMProject_c/data/crm_database.db"
MYSQL_CONFIG = {"host": "127.0.0.1", "port": 3307, "user": "root", "password": "Atguigu.123", "charset": "utf8mb4"}
TABLES = ["customers", "opportunities", "contracts", "sales_orders", "field_visits", "sales_persons", "sales_targets", "contacts"]

def mt(t):
    u = t.upper()
    if "INT" in u: return "INT"
    if "FLOAT" in u or "DOUBLE" in u or "REAL" in u: return "DOUBLE"
    if "TEXT" in u or "CHAR" in u or "VARCHAR" in u: return "TEXT"
    return "VARCHAR(255)"

def migrate():
    src = sqlite3.connect(SQLITE_PATH)
    dst = pymysql.connect(**MYSQL_CONFIG)
    try:
        dst.select_db("attribution")
        with dst.cursor() as c:
            for table in TABLES:
                cols = src.execute("PRAGMA table_info([%s])" % table).fetchall()
                pk_cols = [col[1] for col in cols if col[5] > 0]
                cds = []
                for col in cols:
                    if col[5] > 0:
                        cds.append("`%s` VARCHAR(255) NOT NULL" % col[1])
                    else:
                        cds.append("`%s` %s NULL" % (col[1], mt(col[2])))
                if pk_cols:
                    cds.append("PRIMARY KEY (`%s`)" % pk_cols[0])
                c.execute("DROP TABLE IF EXISTS `crm_%s`" % table)
                c.execute("CREATE TABLE `crm_%s` (%s) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" % (table, ", ".join(cds)))
                dst.commit()
                rows = src.execute("SELECT * FROM [%s]" % table).fetchall()
                if not rows:
                    print("  crm_%s: 0 行" % table)
                    continue
                names = ["`%s`" % col[1] for col in cols]
                ph = ",".join(["%s"] * len(names))
                sql = "INSERT INTO `crm_%s` (%s) VALUES (%s)" % (table, ",".join(names), ph)
                for i in range(0, len(rows), 100):
                    for row in rows[i:i+100]:
                        c.execute(sql, tuple(None if isinstance(v, bytes) else v for v in row))
                    dst.commit()
                print("  ✅ crm_%s: %d 行" % (table, len(rows)))
        print("🎉 迁移完成")
    finally:
        src.close()
        dst.close()

if __name__ == "__main__":
    migrate()