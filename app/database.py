from contextlib import contextmanager

from mysql.connector.pooling import MySQLConnectionPool

from config import settings

_pool = MySQLConnectionPool(
    pool_name="pet_hydration_pool",
    pool_size=20,
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    user=settings.DB_USER,
    password=settings.DB_PASSWORD,
    database=settings.DB_NAME,
    charset="utf8mb4",
    collation="utf8mb4_unicode_ci",
    autocommit=False,
    time_zone="+01:00",
)


@contextmanager
def get_db():
    conn = _pool.get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor(conn):
    cursor = conn.cursor(dictionary=True)
    try:
        yield cursor
    finally:
        cursor.close()