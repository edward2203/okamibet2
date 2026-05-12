# app/routes/api.py
from flask import request, jsonify, Blueprint

api_bp = Blueprint('api', __name__, url_prefix='/api')
from app.database import get_db, release_db
from app.models.configuracion import get_config, get_config_batch
from app.models.apuesta import ApuestaModel
from app.models.log import LogModel
from app.services.calculos import extraer_equipos_partido, calcular_recomendaciones_escudo
from app.services.validacion import validar_acceso_admin
import psycopg2.extras

DICCIONARIO_IDIOMAS = {"es": {"ganador_txt": "ganó"}, "pt": {"ganador_txt": "ganhou"}}


@api_bp.route('/ganadores_recientes')
def api_ganadores():
    """Últimos 6 ganadores para mostrar en la pantalla pública."""
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('''
            SELECT usuario, premio, resultado AS detalle
            FROM historial_apuestas
            WHERE premio > 0
            ORDER BY fecha_registro DESC LIMIT 6
        ''')
        ganadores_db = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)

    respuesta = [
        {
            "usuario":     g['usuario'],
            "premio":      float(g['premio']),
            "detalle":     g['detalle'] or '',
            "ganador_txt": DICCIONARIO_IDIOMAS["es"]["ganador_txt"],
        }
        for g in ganadores_db
    ]
    return jsonify(respuesta)


@api_bp.route('/validar_usuario', methods=['POST'])
def validar_usuario():
    """Valida credenciales de usuario — usado por validacion.js en tiempo real."""
    data         = request.get_json(silent=True) or {}
    usuario      = data.get('usuario', '').strip().lower()
    pin_ingresado = data.get('pin', '').strip()

    # LOG: Intento de validación de usuario
    log_detalles = {
        'usuario': usuario,
        'pin_length': len(pin_ingresado),
        'ip': request.environ.get('HTTP_X_REAL_IP', request.environ.get('REMOTE_ADDR', 'N/A')),
        'user_agent': request.environ.get('HTTP_USER_AGENT', 'N/A')
    }

    if not usuario:
        LogModel.registrar(
            tipo='warning',
            titulo='⚠️ Validación de Usuario - Sin Usuario',
            descripcion='Intento de validación sin nombre de usuario',
            usuario='DESCONOCIDO',
            detalles=log_detalles
        )
        return jsonify({"existe": False})

    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT saldo, pin FROM usuarios WHERE usuario = %s', (usuario,))
        usuario_data = cur.fetchone()
        cur.close()
    finally:
        release_db(conn)

    if usuario_data:
        pin_correcto = str(usuario_data['pin']) == str(pin_ingresado)
        
        if pin_correcto:
            LogModel.registrar(
                tipo='success',
                titulo='✅ Usuario Validado Exitosamente',
                descripcion=f'Usuario {usuario} validado correctamente',
                usuario=usuario,
                detalles={**log_detalles, 'saldo': float(usuario_data['saldo']), 'pin_correcto': True}
            )
        else:
            LogModel.registrar(
                tipo='warning',
                titulo='⚠️ Validación de Usuario - PIN Incorrecto',
                descripcion=f'Usuario {usuario}: PIN incorrecto',
                usuario=usuario,
                detalles={**log_detalles, 'saldo': float(usuario_data['saldo']), 'pin_correcto': False}
            )
        
        return jsonify({
            "existe":       True,
            "saldo":        float(usuario_data['saldo']),
            "pin_correcto": pin_correcto,
        })
    
    # Usuario no encontrado
    LogModel.registrar(
        tipo='warning',
        titulo='⚠️ Validación de Usuario - No Encontrado',
        descripcion=f'Usuario {usuario} no encontrado en BD',
        usuario=usuario,
        detalles=log_detalles
    )
    return jsonify({"existe": False})


@api_bp.route('/resumen', methods=['GET'])
def api_resumen():
    """
    Resumen de apuestas activas y estadísticas del sistema.
    Retorna información útil para el dashboard y pantalla principal.
    """
    from app.models.apuesta import ApuestaModel
    from app.models.usuario import UsuarioModel
    from app.services.calculos import calcular_pozo_visible
    
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Total de apuestas activas
        cur.execute('SELECT COUNT(*) as total FROM apuestas')
        total_apuestas_activas = cur.fetchone()['total']
        
        # Total apostado
        cur.execute('SELECT COALESCE(SUM(monto), 0) as total FROM apuestas')
        total_apostado = float(cur.fetchone()['total'])
        
        # Total de usuarios
        cur.execute('SELECT COUNT(*) as total FROM usuarios')
        total_usuarios = cur.fetchone()['total']
        
        # Saldo total en el sistema
        cur.execute('SELECT COALESCE(SUM(saldo), 0) as total FROM usuarios')
        saldo_total_usuarios = float(cur.fetchone()['total'])
        
        # Distribución por pronóstico
        cur.execute('''
            SELECT pronostico, COUNT(*) as cantidad, SUM(monto) as total_monto
            FROM apuestas
            GROUP BY pronostico
        ''')
        distribucion = {}
        for row in cur.fetchall():
            distribucion[row['pronostico']] = {
                'cantidad': row['cantidad'],
                'monto': float(row['total_monto'])
            }
        
        cur.close()
    finally:
        release_db(conn)
    
    # Obtener configuraciones
    configs = get_config_batch([
        'comision', 'partido_actual', 'deporte_actual',
        'saldo_semilla', 'pozo_acumulado', 'min_apuesta', 'max_apuesta'
    ])
    
    # Calcular pozo visible
    pozo_bruto = total_apostado + float(configs.get('saldo_semilla', 0)) + float(configs.get('pozo_acumulado', 0))
    pozo_visible = calcular_pozo_visible(total_apostado)
    
    return jsonify({
        'status': 'ok',
        'apuestas_activas': {
            'total': total_apuestas_activas,
            'monto_total': round(total_apostado, 2),
            'pozo_visible': round(pozo_visible, 2),
            'pozo_bruto': round(pozo_bruto, 2),
            'distribucion': {k: {'cantidad': v['cantidad'], 'monto': round(v['monto'], 2)} 
                           for k, v in distribucion.items()}
        },
        'usuarios': {
            'total': total_usuarios,
            'saldo_total': round(saldo_total_usuarios, 2)
        },
        'configuracion': {
            'partido_actual': configs.get('partido_actual', 'N/A'),
            'deporte': configs.get('deporte_actual', 'futbol'),
            'comision': float(configs.get('comision', 20)),
            'min_apuesta': float(configs.get('min_apuesta', 20)),
            'max_apuesta': float(configs.get('max_apuesta', 200))
        }
    })


@api_bp.route('/shield/rules', methods=['GET'])
def get_shield_rules():
    """Lista todas las reglas del escudo anti-pérdidas."""
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT estrategia_id, nombre, activa, valor_numerico FROM admin_shield_rules ORDER BY id')
        rules = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)

    return jsonify([dict(r) for r in rules])


@api_bp.route('/shield/recommendation', methods=['GET'])
def get_shield_recommendation():
    """Devuelve recomendaciones de escudo anti-pérdidas según la matemática actual."""
    total_bruto = ApuestaModel.obtener_suma_todas()
    partido_actual = get_config('partido_actual') or ''
    op1, op2 = extraer_equipos_partido(partido_actual)
    distribucion = ApuestaModel.obtener_distribucion(op1, op2)
    recomendacion = calcular_recomendaciones_escudo(total_bruto, distribucion)
    return jsonify(recomendacion)


@api_bp.route('/shield/rules/update', methods=['POST'])
def update_shield_rules():
    """Actualiza activa/valor de una regla del escudo."""
    data = request.get_json(silent=True) or {}
    estrategia_id = data.get('estrategia_id', '').strip()
    activa        = int(data.get('activa', 0))
    valor         = float(data.get('valor', 0.0))

    if not estrategia_id:
        return jsonify({"status": "error", "message": "estrategia_id requerido"}), 400

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            'UPDATE admin_shield_rules SET activa = %s, valor_numerico = %s WHERE estrategia_id = %s',
            (activa, valor, estrategia_id)
        )
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        release_db(conn)

    return jsonify({"status": "success", "message": "Regla actualizada"})


@api_bp.route('/registrar_evento', methods=['POST'])
def registrar_evento():
    """
    Registra un evento en el log del sistema
    
    Body JSON:
    {
        "tipo": "info|success|warning|error|config",
        "titulo": "Título del evento",
        "descripcion": "Descripción corta",
        "usuario": "usuario (opcional)",
        "detalles": "JSON string (opcional)"
    }
    """
    try:
        data = request.get_json()
        
        tipo = data.get('tipo', 'info')
        titulo = data.get('titulo', 'Evento sin título')
        descripcion = data.get('descripcion', '')
        usuario = data.get('usuario', 'WEB')
        detalles = data.get('detalles', '')
        
        LogModel.registrar(tipo, titulo, descripcion, usuario, detalles)
        
        return jsonify({'status': 'ok', 'mensaje': 'Evento registrado'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'mensaje': str(e)}), 500


@api_bp.route('/obtener_logs', methods=['GET'])
def obtener_logs():
    """Obtiene los últimos logs (máximo 100)"""
    try:
        limite = request.args.get('limite', 50, type=int)
        if limite > 100:
            limite = 100
        
        logs = LogModel.obtener_ultimos(limite)
        
        # Convertir fechas a string
        logs_serializable = []
        for log in logs:
            logs_serializable.append({
                'id': log['id'],
                'tipo': log['tipo'],
                'titulo': log['titulo'],
                'descripcion': log['descripcion'],
                'usuario': log['usuario'],
                'detalles': log['detalles'],
                'fecha': log['fecha'].isoformat() if log['fecha'] else None
            })
        
        return jsonify({'status': 'ok', 'logs': logs_serializable}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'mensaje': str(e)}), 500

@api_bp.route('/client_log', methods=['POST'])
def client_log():
    """Recibe logs del cliente (JavaScript) y los registra en el sistema."""
    data = request.get_json(silent=True) or {}
    
    tipo = data.get('tipo', 'info')
    titulo = data.get('titulo', 'Evento Cliente')
    descripcion = data.get('descripcion', '')
    usuario = data.get('usuario', 'ANONIMO')
    detalles = data.get('detalles', {})
    
    # Agregar IP y User Agent
    ip = request.environ.get('HTTP_X_REAL_IP', request.environ.get('REMOTE_ADDR', 'N/A'))
    user_agent = request.environ.get('HTTP_USER_AGENT', 'N/A')
    
    if isinstance(detalles, dict):
        detalles['ip'] = ip
        detalles['user_agent'] = user_agent
        detalles['referer'] = request.environ.get('HTTP_REFERER', 'N/A')
    
    LogModel.registrar(
        tipo=tipo,
        titulo=titulo,
        descripcion=descripcion,
        usuario=usuario,
        detalles=detalles,
        ip_address=ip,
        user_agent=user_agent
    )
    
    return jsonify({'status': 'ok'}), 200


@api_bp.route('/clear_logs', methods=['POST'])
def clear_logs():
    """
    Elimina TODOS los logs del sistema tras validar contraseña de administrador.
    Registra el evento de limpieza en el log (auditoría).
    """
    data = request.get_json(silent=True) or {}
    admin_pass = data.get('admin_pass', '')
    
    # Validar contraseña
    if not validar_acceso_admin(admin_pass):
        LogModel.registrar(
            tipo='warning',
            titulo='⚠️ Intento de Limpieza de Logs - Acceso Denegado',
            descripcion='Intento de limpiar logs sin contraseña válida',
            usuario='ADMIN',
            detalles={
                'ip': request.environ.get('HTTP_X_REAL_IP', request.environ.get('REMOTE_ADDR', 'N/A')),
                'user_agent': request.environ.get('HTTP_USER_AGENT', 'N/A')
            },
            nivel='WARNING'
        )
        return jsonify({'status': 'error', 'message': 'Contraseña de administrador incorrecta'}), 403
    
    # Contar registros antes de eliminar
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM logs_sistema")
        total_registros = cursor.fetchone()[0]
    finally:
        release_db(conn)
    
    # Eliminar todos los logs
    registros_eliminados = LogModel.limpiar_todos()
    
    # Registrar evento de auditoría (este log SÍ se guarda para auditoría)
    LogModel.registrar(
        tipo='config',
        titulo='🗑️ Logs del Sistema Eliminados',
        descripcion=f'Se eliminaron {registros_eliminados} registros del log del sistema',
        usuario='ADMIN',
        detalles={
            'total_registros_eliminados': registros_eliminados,
            'ip': request.environ.get('HTTP_X_REAL_IP', request.environ.get('REMOTE_ADDR', 'N/A')),
            'user_agent': request.environ.get('HTTP_USER_AGENT', 'N/A')
        },
        nivel='CRITICAL'
    )
    
    return jsonify({
        'status': 'ok',
        'message': f'Se eliminaron {registros_eliminados} registros del log',
        'registros_eliminados': registros_eliminados
    }), 200
