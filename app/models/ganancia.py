# app/models/ganancia.py
from app.database import get_db, release_db
import psycopg2.extras


class GananciaModel:

    @staticmethod
    def obtener_historial_admin(limite=10):
        """
        Retorna las últimas N ganancias de la casa.
        Tabla ganancias_admin: id, monto, concepto, fecha
        """
        conn = get_db()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(
                'SELECT id, monto, concepto, fecha FROM ganancias_admin ORDER BY fecha DESC LIMIT %s',
                (limite,)
            )
            return cursor.fetchall()
        except Exception as e:
            print(f"⚠️ Error al obtener ganancias: {e}")
            return []
        finally:
            release_db(conn)

    @staticmethod
    def registrar_ganancia(monto, concepto="Liquidación"):
        """Registra una ganancia de la casa."""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO ganancias_admin (monto, concepto) VALUES (%s, %s)',
                (monto, concepto)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"⚠️ Error al registrar ganancia: {e}")
        finally:
            release_db(conn)
