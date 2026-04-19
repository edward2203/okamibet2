# app/models/apuesta.py
from app.database import get_db, release_db

class ApuestaModel:

    @staticmethod
    def obtener_suma_todas(deporte=None):
        """Calcula el volumen escalar total de todas las apuestas."""
        conn = get_db()
        try:
            cursor = conn.cursor()
            if deporte:
                # Cambiado a %s para Postgres
                cursor.execute('SELECT SUM(monto) FROM apuestas WHERE deporte = %s', (deporte,))
            else:
                cursor.execute('SELECT SUM(monto) FROM apuestas')
            
            row = cursor.fetchone()
            return float(row[0] or 0.0) if row else 0.0
        finally:
            release_db(conn) # Retorno seguro al Pool

    @staticmethod
    def obtener_distribucion(op1, op2, deporte=None):
        """Obtiene el mapa bidimensional de distribución de apuestas."""
        conn = get_db()
        try:
            cursor = conn.cursor()
            if deporte:
                cursor.execute('''SELECT pronostico, SUM(monto) 
                                  FROM apuestas WHERE deporte = %s 
                                  GROUP BY pronostico''', (deporte,))
            else:
                cursor.execute('SELECT pronostico, SUM(monto) FROM apuestas GROUP BY pronostico')

            # Mapeo manual para evitar errores de DictCursor
            distribucion = {}
            for row in cursor.fetchall():
                # row[0] es pronostico, row[1] es total
                distribucion[row[0]] = float(row[1] or 0.0)

            # Asegurar vértices base en la matriz
            for opcion in [op1, "Empate", op2]:
                if opcion not in distribucion:
                    distribucion[opcion] = 0.0
            return distribucion
        finally:
            release_db(conn)

    @staticmethod
    def obtener_primer_apostador(deporte=None):
        """Identifica el primer vector de usuario de la ronda."""
        conn = get_db()
        try:
            cursor = conn.cursor()
            if deporte:
                cursor.execute('SELECT usuario FROM apuestas WHERE deporte = %s ORDER BY id ASC LIMIT 1', (deporte,))
            else:
                cursor.execute('SELECT usuario FROM apuestas ORDER BY id ASC LIMIT 1')
                
            primer_ap = cursor.fetchone()
            # Acceso por índice 0 (usuario) para evitar fallos de 'NoneType' o 'KeyError'
            return primer_ap[0] if primer_ap else None
        finally:
            release_db(conn)