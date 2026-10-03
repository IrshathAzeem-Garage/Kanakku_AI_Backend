"""
One-time database migration script: SQLite -> PostgreSQL.

Transfers all records from a legacy local SQLite kanakku.db into PostgreSQL.
The application itself does NOT depend on SQLite or this script for runtime operation.

Usage:
    python -m scripts.migrate_sqlite_to_postgres
"""
import os
import sys
import sqlite3
from decimal import Decimal
from sqlalchemy import create_engine, text

# Add backend to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.utils.logger import logger


def migrate_sqlite_to_postgres(sqlite_path: str = "kanakku.db"):
    if not os.path.exists(sqlite_path):
        logger.info(f"No SQLite file found at '{sqlite_path}'. Skipping migration.")
        return

    pg_url = settings.DATABASE_URL
    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql://", 1)

    logger.info(f"Starting one-time migration: {sqlite_path} -> PostgreSQL...")
    
    # 1. Read from SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    cur = sqlite_conn.cursor()

    # 2. Connect to PostgreSQL
    pg_engine = create_engine(pg_url, pool_pre_ping=True)

    with pg_engine.begin() as pg_conn:
        # Check if tables exist in PostgreSQL
        for table in ["users", "shops", "daily_records", "customer_receipts", "digital_entries", "expenses"]:
            try:
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
                if not rows:
                    continue
                
                col_names = [col[0] for col in cur.description]
                cols_str = ", ".join(col_names)
                params_str = ", ".join([f":{c}" for c in col_names])

                insert_sql = text(f"""
                    INSERT INTO {table} ({cols_str})
                    VALUES ({params_str})
                    ON CONFLICT (id) DO NOTHING
                """)

                count = 0
                for r in rows:
                    row_dict = dict(r)
                    # Convert float/int amounts to Decimal for Numeric fields
                    for k, v in row_dict.items():
                        if "amount" in k or "money" in k or "expenses" in k:
                            if v is not None:
                                row_dict[k] = Decimal(str(v))
                    pg_conn.execute(insert_sql, row_dict)
                    count += 1

                # Update sequence to prevent duplicate key errors on future inserts
                pg_conn.execute(text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table}), 1)
                    )
                """))
                logger.info(f"Migrated {count} rows into PostgreSQL table '{table}'.")

            except Exception as table_err:
                logger.warning(f"Notice while migrating table '{table}': {table_err}")

    sqlite_conn.close()
    logger.info("One-time migration from SQLite to PostgreSQL completed successfully.")


if __name__ == "__main__":
    sqlite_file = sys.argv[1] if len(sys.argv) > 1 else "kanakku.db"
    migrate_sqlite_to_postgres(sqlite_file)
