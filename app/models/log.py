"""
Modelo de Logs del Sistema - Captura todos los eventos
"""
from datetime import datetime
from app.database import get_db, release_db

class LogModel:
    """Gestión de logs del sistema"""
    
    @staticmethod
    def registrar(tipo, titulo, descripcion, usuario="SISTEMA", detalles=None):
        """
        Registra un evento en el log del sistema
        
        Args:
            tipo: 'info', 'success', 'warning', 'error', 'config'
            titulo: Título del evento
            descripcion: Descripción corta
            usuario: Quién realizó la acción (default: SISTEMA)
            detalles: JSON con detalles adicionales
        """
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO logs_sistema 
                (tipo, titulo, descripcion, usuario, detalles, fecha)
                VALUES (%s, %s, %s, %s, %s, NOW())
            ''', (tipo, titulo, descripcion, usuario, detalles or ''))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error al registrar log: {e}")
        finally:
            release_db(conn)
    
    @staticmethod
    def obtener_ultimos(limite=50):
        """Obtiene los últimos N logs"""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tipo, titulo, descripcion, usuario, detalles, fecha
                FROM logs_sistema
                ORDER BY fecha DESC
                LIMIT %s
            ''', (limite,))
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'id': row[0],
                    'tipo': row[1],
                    'titulo': row[2],
                    'descripcion': row[3],
                    'usuario': row[4],
                    'detalles': row[5],
                    'fecha': row[6]
                })
            return logs
        finally:
            release_db(conn)
    
    @staticmethod
    def obtener_por_tipo(tipo, limite=50):
        """Obtiene logs de un tipo específico"""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tipo, titulo, descripcion, usuario, detalles, fecha
                FROM logs_sistema
                WHERE tipo = %s
                ORDER BY fecha DESC
                LIMIT %s
            ''', (tipo, limite))
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'id': row[0],
                    'tipo': row[1],
                    'titulo': row[2],
                    'descripcion': row[3],
                    'usuario': row[4],
                    'detalles': row[5],
                    'fecha': row[6]
                })
            return logs
        finally:
            release_db(conn)
    
    @staticmethod
    def limpiar_antiguos(dias=30):
        """Limpia logs más antiguos que N días"""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM logs_sistema 
                WHERE fecha < NOW() - INTERVAL '%s days'
            ''', (dias,))
            conn.commit()
            return cursor.rowcount
        finally:
            release_db(conn)
