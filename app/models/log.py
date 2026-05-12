"""
Modelo de Logs del Sistema - Captura todos los eventos
Soporta niveles: DEBUG, INFO, WARNING, ERROR, CRITICAL
Almacena trazas de pila, parámetros de entrada, metadatos contextuales en formato JSON
"""
from datetime import datetime
from flask import request
from app.database import get_db, release_db
import json
import sys
import traceback
import inspect

class LogModel:
    """Gestión de logs del sistema"""
    
    _tabla_migrada = False
    
    @classmethod
    def _asegurar_tabla(cls, conn):
        """Asegura que la tabla tenga todas las columnas necesarias"""
        if cls._tabla_migrada:
            return
        
        try:
            cursor = conn.cursor()
            
            # Verificar columnas existentes
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'logs_sistema' 
                AND column_name IN ('ip_address', 'user_agent', 'nivel')
            """)
            existing_columns = [row[0] for row in cursor.fetchall()]
            
            # Agregar ip_address si no existe
            if 'ip_address' not in existing_columns:
                try:
                    cursor.execute("ALTER TABLE logs_sistema ADD COLUMN ip_address VARCHAR(45) DEFAULT 'N/A'")
                    conn.commit()
                    print("✓ Columna ip_address agregada a logs_sistema")
                except Exception as e:
                    print(f"Error agregando ip_address: {e}")
                    conn.rollback()
            
            # Agregar user_agent si no existe
            if 'user_agent' not in existing_columns:
                try:
                    cursor.execute("ALTER TABLE logs_sistema ADD COLUMN user_agent TEXT DEFAULT 'N/A'")
                    conn.commit()
                    print("✓ Columna user_agent agregada a logs_sistema")
                except Exception as e:
                    print(f"Error agregando user_agent: {e}")
                    conn.rollback()
            
            # Agregar nivel (severidad) si no existe
            if 'nivel' not in existing_columns:
                try:
                    cursor.execute("ALTER TABLE logs_sistema ADD COLUMN nivel VARCHAR(20) DEFAULT 'INFO'")
                    conn.commit()
                    print("✓ Columna nivel agregada a logs_sistema")
                except Exception as e:
                    print(f"Error agregando nivel: {e}")
                    conn.rollback()
            
            cursor.close()
            cls._tabla_migrada = True
            
        except Exception as e:
            print(f"Error en _asegurar_tabla: {e}")
            conn.rollback()
    
    @staticmethod
    def registrar(tipo, titulo, descripcion, usuario="SISTEMA", detalles=None, ip_address=None, user_agent=None, nivel='INFO'):
        """
        Registra un evento en el log del sistema (DETALLADO)
        
        Args:
            tipo: Categoría del evento ('config', 'apuesta', 'usuario', 'sistema', etc.)
            titulo: Título del evento
            descripcion: Descripción corta
            usuario: Quién realizó la acción (default: SISTEMA)
            detalles: Dict o JSON con detalles adicionales
            ip_address: IP del cliente (se auto-detecta si no se pasa)
            user_agent: User Agent del cliente (se auto-detecta si no se pasa)
            nivel: Nivel de severidad ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        """
        # Auto-detectar IP y User Agent si están disponibles
        if ip_address is None and request:
            ip_address = request.environ.get('HTTP_X_REAL_IP', request.environ.get('REMOTE_ADDR', 'N/A'))
        if user_agent is None and request:
            user_agent = request.environ.get('HTTP_USER_AGENT', 'N/A')
        
        # Convertir detalles a JSON string si es dict
        if isinstance(detalles, dict):
            detalles = json.dumps(detalles, ensure_ascii=False, default=str)
        
        conn = get_db()
        try:
            # Asegurar que la tabla tenga todas las columnas
            LogModel._asegurar_tabla(conn)
            
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO logs_sistema 
                (tipo, titulo, descripcion, usuario, detalles, ip_address, user_agent, fecha, nivel)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
            ''', (tipo, titulo, descripcion, usuario, detalles or '', ip_address or 'N/A', user_agent or 'N/A', nivel))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error al registrar log: {e}")
        finally:
            release_db(conn)
    
    @staticmethod
    def log_exception(exception, tipo='error', titulo=None, usuario="SISTEMA", detalles_extra=None, nivel='ERROR'):
        """
        Registra una excepción con traza completa de pila, módulo, función, parámetros de entrada.
        
        Args:
            exception: La excepción capturada
            tipo: Categoría del evento
            titulo: Título personalizado (si no se pasa, se genera automáticamente)
            usuario: Usuario afectado
            detalles_extra: Diccionario con detalles adicionales
            nivel: Nivel de severidad (default: ERROR)
        """
        # Capturar traza de pila
        tb_str = traceback.format_exc()
        if not tb_str or tb_str == 'NoneType: None\n':
            tb_str = ''.join(traceback.format_stack())
        
        # Capturar información del caller (módulo, función, línea)
        caller_info = {}
        try:
            # Obtener la frame del caller (saltando las frames de log_exception y registrar)
            stack = inspect.stack()
            # Buscar la primera frame que no sea de este módulo
            for frame_info in stack[2:]:  # Saltar log_exception y registrar
                if frame_info.filename != __file__:
                    caller_info = {
                        'modulo': frame_info.filename,
                        'funcion': frame_info.function,
                        'linea': frame_info.lineno
                    }
                    break
        except Exception:
            caller_info = {'modulo': 'unknown', 'funcion': 'unknown', 'linea': 0}
        
        # Construir detalles
        detalles = {
            'exception_type': type(exception).__name__,
            'exception_message': str(exception),
            'stack_trace': tb_str,
            'caller': caller_info
        }
        
        # Agregar parámetros de entrada si hay request
        if request:
            input_params = {}
            try:
                if request.args:
                    input_params['args'] = dict(request.args)
                if request.form:
                    input_params['form'] = dict(request.form)
                if request.is_json:
                    input_params['json'] = request.get_json(silent=True)
                if request.view_args:
                    input_params['view_args'] = request.view_args
                if input_params:
                    detalles['input_params'] = input_params
            except Exception:
                pass
        
        # Agregar detalles extra
        if detalles_extra and isinstance(detalles_extra, dict):
            detalles['extra'] = detalles_extra
        
        # Generar título si no se pasó
        if not titulo:
            titulo = f"{type(exception).__name__} en {caller_info.get('funcion', 'unknown')}"
        
        # Registrar
        LogModel.registrar(
            tipo=tipo,
            titulo=titulo,
            descripcion=str(exception),
            usuario=usuario,
            detalles=detalles,
            nivel=nivel
        )
    
    @staticmethod
    def obtener_ultimos(limite=50):
        """Obtiene los últimos N logs (incluye nivel de severidad)"""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tipo, titulo, descripcion, usuario, detalles, ip_address, user_agent, fecha, nivel
                FROM logs_sistema
                ORDER BY fecha DESC
                LIMIT %s
            ''', (limite,))
            
            logs = []
            for row in cursor.fetchall():
                detalles = row[5]
                # Intentar parsear JSON si es string
                if isinstance(detalles, str):
                    try:
                        import json
                        detalles = json.loads(detalles)
                    except:
                        detalles = {'raw': detalles}
                
                # Asegurar que sea dict y convertir listas a strings
                if isinstance(detalles, dict):
                    for key in detalles:
                        if isinstance(detalles[key], list):
                            detalles[key] = ', '.join(str(item) for item in detalles[key])
                        elif not isinstance(detalles[key], (str, int, float)):
                            detalles[key] = str(detalles[key])
                elif not isinstance(detalles, dict):
                    detalles = {'value': str(detalles)}
                
                logs.append({
                    'id': row[0],
                    'tipo': row[1],
                    'titulo': row[2],
                    'descripcion': row[3],
                    'usuario': row[4],
                    'detalles': detalles,
                    'ip_address': row[6],
                    'user_agent': row[7],
                    'fecha': row[8],
                    'nivel': row[9] or 'INFO'
                })
            return logs
        finally:
            release_db(conn)
    
    @staticmethod
    def obtener_por_tipo(tipo, limite=50):
        """Obtiene logs de un tipo específico (incluye nivel de severidad)"""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tipo, titulo, descripcion, usuario, detalles, ip_address, user_agent, fecha, nivel
                FROM logs_sistema
                WHERE tipo = %s
                ORDER BY fecha DESC
                LIMIT %s
            ''', (tipo, limite))
            
            logs = []
            for row in cursor.fetchall():
                detalles = row[5]
                # Intentar parsear JSON si es string
                if isinstance(detalles, str):
                    try:
                        import json
                        detalles = json.loads(detalles)
                    except:
                        detalles = {'raw': detalles}
                
                # Asegurar que sea dict y convertir listas a strings
                if isinstance(detalles, dict):
                    for key in detalles:
                        if isinstance(detalles[key], list):
                            detalles[key] = ', '.join(str(item) for item in detalles[key])
                        elif not isinstance(detalles[key], (str, int, float)):
                            detalles[key] = str(detalles[key])
                elif not isinstance(detalles, dict):
                    detalles = {'value': str(detalles)}
                
                logs.append({
                    'id': row[0],
                    'tipo': row[1],
                    'titulo': row[2],
                    'descripcion': row[3],
                    'usuario': row[4],
                    'detalles': detalles,
                    'ip_address': row[6],
                    'user_agent': row[7],
                    'fecha': row[8],
                    'nivel': row[9] or 'INFO'
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
    
    @staticmethod
    def obtener_por_nivel(nivel, limite=50):
        """Obtiene logs filtrados por nivel de severidad"""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tipo, titulo, descripcion, usuario, detalles, ip_address, user_agent, fecha, nivel
                FROM logs_sistema
                WHERE nivel = %s
                ORDER BY fecha DESC
                LIMIT %s
            ''', (nivel, limite))
            
            logs = []
            for row in cursor.fetchall():
                detalles = row[5]
                if isinstance(detalles, str):
                    try:
                        import json
                        detalles = json.loads(detalles)
                    except:
                        detalles = {'raw': detalles}
                if isinstance(detalles, dict):
                    for key in detalles:
                        if isinstance(detalles[key], list):
                            detalles[key] = ', '.join(str(item) for item in detalles[key])
                        elif not isinstance(detalles[key], (str, int, float)):
                            detalles[key] = str(detalles[key])
                elif not isinstance(detalles, dict):
                    detalles = {'value': str(detalles)}
                
                logs.append({
                    'id': row[0],
                    'tipo': row[1],
                    'titulo': row[2],
                    'descripcion': row[3],
                    'usuario': row[4],
                    'detalles': detalles,
                    'ip_address': row[6],
                    'user_agent': row[7],
                    'fecha': row[8],
                    'nivel': row[9] or 'INFO'
                })
            return logs
        finally:
            release_db(conn)
    
    @staticmethod
    def obtener_niveles():
        """Obtiene los distintos niveles de severidad presentes en los logs"""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT nivel FROM logs_sistema ORDER BY nivel")
            return [row[0] for row in cursor.fetchall()]
        finally:
            release_db(conn)

    @staticmethod
    def limpiar_todos():
        """Elimina TODOS los registros de la tabla logs_sistema"""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM logs_sistema")
            conn.commit()
            return cursor.rowcount
        finally:
            release_db(conn)
