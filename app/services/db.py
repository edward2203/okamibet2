# app/services/db.py
import psycopg2
from psycopg2.extras import DictCursor
from contextlib import contextmanager
from app.database import get_db, release_db


def obtener_conexion():
    return get_db()


@contextmanager
def transaction():
    conn = obtener_conexion()
    if conn is None:
        raise Exception("No se pudo obtener conexión del pool.")
    cursor = conn.cursor(cursor_factory=DictCursor)
    try:
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[!] Error en Transacción PG: {e}")
        raise e
    finally:
        cursor.close()
        release_db(conn)


def init_db():
    """Inicializa el esquema base completo en PostgreSQL."""
    conn = obtener_conexion()

    # ✅ CORRECCIÓN PRINCIPAL: validar conn antes de usarlo
    if conn is None:
        print("❌ [SISTEMA-PG] No se pudo obtener conexión. init_db() abortado.")
        return

    cursor = None
    try:
        cursor = conn.cursor()
        print("🏗️  [SISTEMA-PG] Construyendo infraestructura completa...")

        # 1. Tabla Usuarios
        cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                            id SERIAL PRIMARY KEY,
                            usuario TEXT UNIQUE NOT NULL,
                            pin TEXT NOT NULL,
                            saldo DECIMAL(15,2) DEFAULT 0.0,
                            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                          )''')

        # 2. Tabla Bonificaciones
        cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios_bonificacion (
                            id SERIAL PRIMARY KEY,
                            usuario TEXT UNIQUE REFERENCES usuarios(usuario) ON DELETE CASCADE,
                            bono_bienvenida_usado INTEGER DEFAULT 0
                          )''')

        # 3. Tabla Apuestas
        cursor.execute('''CREATE TABLE IF NOT EXISTS apuestas (
                            id SERIAL PRIMARY KEY,
                            usuario_id INTEGER,
                            usuario TEXT,
                            evento_id TEXT,
                            monto DECIMAL(15,2),
                            pronostico TEXT,
                            deporte TEXT DEFAULT 'futbol',
                            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                          )''')

        # 4. Tabla Configuraciones
        cursor.execute('''CREATE TABLE IF NOT EXISTS configuraciones (
                            id SERIAL PRIMARY KEY,
                            clave TEXT UNIQUE,
                            valor TEXT
                          )''')

        # 5. Tabla Ganancias Admin
        cursor.execute('''CREATE TABLE IF NOT EXISTS ganancias_admin (
                            id SERIAL PRIMARY KEY,
                            monto DECIMAL(15,2) NOT NULL,
                            concepto TEXT,
                            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                          )''')

        # 6. Tabla Historial de Apuestas (registro permanente por ronda)
        cursor.execute('''CREATE TABLE IF NOT EXISTS historial_apuestas (
                            id SERIAL PRIMARY KEY,
                            usuario TEXT NOT NULL,
                            usuario_id INTEGER,
                            monto DECIMAL(15,2) NOT NULL,
                            pronostico TEXT,
                            resultado TEXT,
                            premio DECIMAL(15,2) DEFAULT 0.0,
                            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                          )''')

        # 7. Tabla Reglas del Escudo Anti-Pérdidas
        cursor.execute('''CREATE TABLE IF NOT EXISTS admin_shield_rules (
                            id SERIAL PRIMARY KEY,
                            estrategia_id TEXT UNIQUE NOT NULL,
                            nombre TEXT,
                            activa INTEGER DEFAULT 0,
                            valor_numerico DECIMAL(10,4) DEFAULT 0.0
                          )''')

        # Semillas de reglas del escudo (solo si no existen)
        shield_rules = [
            ('sacrificio_comision',      'Sacrificio de Comisión',      0, 5.0),
            ('cuota_minima_garantizada', 'Cuota Mínima Garantizada',    0, 1.0),
            ('bloqueo_mercado',          'Bloqueo de Mercado',          0, 0.0),
        ]
        for estrategia_id, nombre, activa, valor in shield_rules:
            cursor.execute("""
                INSERT INTO admin_shield_rules (estrategia_id, nombre, activa, valor_numerico)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (estrategia_id) DO NOTHING
            """, (estrategia_id, nombre, activa, valor))

        # Semillas críticas
        configs = [
            ('min_apuesta', '20.0'),
            ('max_apuesta', '200.0'),
            ('comision', '10.0'),
            ('deporte_actual', 'futbol'),
            ('partido_actual', 'Palmeiras vs São Paulo')
        ]

        for k, v in configs:
            cursor.execute("""
                INSERT INTO configuraciones (clave, valor)
                VALUES (%s, %s)
                ON CONFLICT (clave) DO NOTHING
            """, (k, v))

        conn.commit()
        print("✅ [SISTEMA-PG] Inicialización completada con semillas.")

    except Exception as e:
        conn.rollback()
        print(f"❌ [SISTEMA-PG] Error durante init_db: {e}")
        raise

    finally:
        # ✅ CORRECCIÓN: cerrar cursor siempre y liberar conexión
        if cursor:
            cursor.close()
        release_db(conn)


def aplicar_migraciones():
    """Sincroniza columnas faltantes en caliente."""
    conn = obtener_conexion()

    # ✅ CORRECCIÓN: validar conn
    if conn is None:
        print("❌ [SISTEMA-PG] No se pudo obtener conexión. Migraciones abortadas.")
        return

    cursor = None
    try:
        cursor = conn.cursor()
        print("🔍 [SISTEMA-PG] Verificando integridad de columnas...")

        cambios = False
        # Añade aquí ALTER TABLE si detectas columnas faltantes en el futuro

        if cambios:
            conn.commit()
            print("✅ [MIGRACIÓN] Estructura alineada.")
        else:
            print("✅ [SISTEMA] Estructura validada.")

    except Exception as e:
        conn.rollback()
        print(f"❌ [MIGRACIÓN] Error: {e}")
        raise

    finally:
        # ✅ CORRECCIÓN: cerrar cursor siempre y liberar conexión
        if cursor:
            cursor.close()
        release_db(conn)