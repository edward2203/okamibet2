import psycopg2
from psycopg2 import pool
import sys

try:
    from config_postgres import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
except ImportError:
    print("❌ ERROR: No se encontró 'config_postgres.py'.")
    sys.exit(1)

_connection_pool = None


def init_pool():
    global _connection_pool
    if _connection_pool is None:
        try:
            print("[🚀] Conectando Okami Bet a Supabase (Modo Directo)...")
            _connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 10,
                host=DB_HOST,
                port=int(DB_PORT),
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASS,
                sslmode='require'
            )
            if _connection_pool:
                print("✅ Pool de conexiones PostgreSQL creado con éxito.")
        except Exception as error:
            print(f"❌ ERROR CRÍTICO al conectar con Supabase: {error}")
            _connection_pool = None
            raise  # ← Re-lanza para que create_app() sepa que falló


def get_db():
    global _connection_pool
    if _connection_pool is None:
        init_pool()
    if _connection_pool:
        return _connection_pool.getconn()
    return None


def release_db(conn):
    global _connection_pool
    if _connection_pool and conn:
        _connection_pool.putconn(conn)

