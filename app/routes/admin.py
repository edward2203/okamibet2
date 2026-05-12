# app/routes/admin.py
from flask import render_template, request, redirect, url_for, jsonify, session, flash, Blueprint

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
from app.services.validacion import validar_acceso_admin
from app.services.calculos import extraer_equipos_partido, procesar_limpiar_pozo_completo, calcular_pozo_visible
from app.services.football_api import obtener_partidos_externos
from app.models.configuracion import get_config_batch, set_config, get_config
from app.models.log import LogModel
from app.database import get_db, release_db
from app.models.ganancia import GananciaModel
from app.models.apuesta import ApuestaModel
import psycopg2.extras
import subprocess
import os
import signal
import json
import time

# Variable global para el proceso ngrok
ngrok_process = None
ngrok_url = None


def login_required(f):
    """Decorador para proteger rutas que requieren autenticación admin."""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login para acceso al panel admin."""
    if request.method == 'POST':
        password = request.form.get('password', '')
        if validar_acceso_admin(password):
            session['admin_authenticated'] = True
            next_url = request.args.get('next')
            return redirect(next_url or url_for('admin.vista_admin'))
        else:
            flash('Contraseña incorrecta', 'error')
    return render_template('login.html')


@admin_bp.route('/logout')
def logout():
    """Cierra la sesión admin."""
    session.pop('admin_authenticated', None)
    flash('Sesión cerrada', 'info')
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
@login_required
def vista_admin():
    """Panel de control completo — PostgreSQL con DictCursor."""
    # Registrar acceso al panel
    ip = request.environ.get('HTTP_X_REAL_IP', request.environ.get('REMOTE_ADDR', 'N/A'))
    user_agent = request.environ.get('HTTP_USER_AGENT', 'N/A')
    LogModel.registrar(
        tipo='acceso',
        titulo='👤 Acceso al Panel Admin',
        descripcion='Acceso al panel de administración',
        usuario='ADMIN',
        detalles={'ip': ip, 'user_agent': user_agent},
        nivel='INFO'
    )
    
    # Obtener TODAS las configuraciones dinámicamente
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT clave, valor FROM configuraciones ORDER BY clave')
        rows = cursor.fetchall()
        configs = {row['clave']: row['valor'] for row in rows}
    finally:
        release_db(conn)

    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # 1. Usuarios + apuesta activa del mismo usuario en la ronda
        cursor.execute('''
            SELECT u.id, u.usuario, u.pin, u.saldo, u.email, u.telefono,
                   a.monto   AS monto_apuesta,
                   a.pronostico AS pronostico_apuesta
            FROM usuarios u
            LEFT JOIN apuestas a ON u.usuario = a.usuario
            ORDER BY u.usuario
        ''')
        usuarios = cursor.fetchall()

        # 2. Resumen de bolsa por pronóstico
        cursor.execute('''
            SELECT pronostico, SUM(monto), COUNT(*)
            FROM apuestas GROUP BY pronostico
        ''')
        apuestas_db = cursor.fetchall()

        # 3. Historial — DictCursor permite acceso por nombre de columna
        cursor.execute('''
            SELECT usuario, monto, pronostico, resultado, premio, fecha_registro
            FROM historial_apuestas
            ORDER BY fecha_registro DESC LIMIT 15
        ''')
        historial = cursor.fetchall()
    finally:
        release_db(conn)

    op1, op2 = extraer_equipos_partido(configs.get('partido_actual', ''))

    resumen_bolsa = {
        op1:      {'total': 0.0, 'cantidad': 0},
        'Empate': {'total': 0.0, 'cantidad': 0},
        op2:      {'total': 0.0, 'cantidad': 0},
    }
    for row in apuestas_db:
        pronostico = row[0]
        if pronostico in resumen_bolsa:
            resumen_bolsa[pronostico]['total']    = float(row[1] or 0)
            resumen_bolsa[pronostico]['cantidad'] = int(row[2] or 0)

    # Calcular pozo_visible (real + acumulado - comisión)
    pozo_real = sum(item['total'] for item in resumen_bolsa.values())
    acumulado = float(configs.get('pozo_acumulado') or 0.0)
    pozo_sin_semilla = pozo_real + acumulado
    pozo_visible = calcular_pozo_visible(pozo_sin_semilla)

    return render_template(
        'admin.html',
        usuarios=usuarios,
        resumen_bolsa=resumen_bolsa,
        op1=op1, op2=op2,
        ganancias_admin=GananciaModel.obtener_historial_admin(),
        historial=historial,
        logs_sistema=LogModel.obtener_ultimos(100),
        configs=configs,
        primer_apostador=ApuestaModel.obtener_primer_apostador() or '',
        pozo_visible=round(pozo_visible, 2),
        pozo_real=round(pozo_real, 2),
        acumulado=round(acumulado, 2)
    )


@admin_bp.route('/crear_usuario', methods=['POST'])
@login_required
def admin_crear_usuario():
    usuario = request.form.get('usuario', '').strip().lower()
    pin     = request.form.get('pin', '').strip()
    email   = request.form.get('email', '').strip() or None
    telefono = request.form.get('telefono', '').strip() or None
    aplicar_bono = request.form.get('aplicar_bono') == 'on'
    try:
        saldo = float(request.form.get('saldo', 0))
    except ValueError:
        return redirect(url_for('admin.vista_admin', error="saldo_invalido"))
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Validar unicidad de usuario
        cursor.execute('SELECT COUNT(*) FROM usuarios WHERE usuario = %s', (usuario,))
        if cursor.fetchone()[0] > 0:
            conn.rollback()
            return redirect(url_for('admin.vista_admin', error="usuario_duplicado"))
        
        # Validar unicidad de email (si se proporcionó)
        if email:
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE email = %s', (email,))
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                return redirect(url_for('admin.vista_admin', error="email_duplicado"))
        
        # Validar unicidad de telefono (si se proporcionó)
        if telefono:
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE telefono = %s', (telefono,))
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                return redirect(url_for('admin.vista_admin', error="telefono_duplicado"))
        
        cursor.execute(
            'INSERT INTO usuarios (usuario, pin, saldo, email, telefono) VALUES (%s, %s, %s, %s, %s)',
            (usuario, pin, saldo, email, telefono)
        )
        
        # Si se marca aplicar_bono, dejar bono_bienvenida_usado = 0 para que se pueda aplicar
        # Si no se marca, ponerlo en 1 (ya usado, no aplicar)
        bono_usado = 0 if aplicar_bono else 1
        cursor.execute(
            'INSERT INTO usuarios_bonificacion (usuario, bono_bienvenida_usado) VALUES (%s, %s)',
            (usuario, bono_usado)
        )
        conn.commit()
        
        # Si se solicito aplicar bono, aplicarlo ahora
        if aplicar_bono:
            from app.models.usuario import UsuarioModel
            UsuarioModel.aplicar_bono_bienvenida(usuario)
        
        # Enviar notificación por email
        if email:
            from app.services.email_service import notificar_creacion_usuario
            try:
                notificar_creacion_usuario(usuario, email, telefono, saldo, aplicar_bono)
            except Exception as e:
                LogModel.registrar(
                    tipo='error',
                    titulo='❌ Error Email Creación Usuario',
                    descripcion=str(e),
                    usuario='ADMIN'
                )
        
        # Registrar evento en log
        LogModel.registrar(
            tipo='success',
            titulo='👤 Nuevo Usuario Creado',
            descripcion=f'Usuario: {usuario}',
            usuario='ADMIN',
            detalles=f'Saldo inicial: R$ {saldo:.2f}, Email: {email or "N/A"}, Telefono: {telefono or "N/A"}, Bono aplicado: {aplicar_bono}'
        )
    except Exception as e:
        conn.rollback()
        LogModel.registrar(
            tipo='error',
            titulo='❌ Error al Crear Usuario',
            descripcion=f'Usuario: {usuario}',
            usuario='ADMIN',
            detalles=str(e)
        )
        return redirect(url_for('admin.vista_admin', error="usuario_duplicado"))
    finally:
        release_db(conn)

    return redirect(url_for('admin.vista_admin', exito="usuario_creado"))


@admin_bp.route('/eliminar_usuario/<usuario>', methods=['POST'])
@login_required
def eliminar_usuario(usuario):
    """Elimina un usuario y sus datos relacionados."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        # Eliminar de tablas relacionadas primero (por FK)
        cursor.execute('DELETE FROM usuarios_bonificacion WHERE usuario = %s', (usuario,))
        cursor.execute('DELETE FROM apuestas WHERE usuario = %s', (usuario,))
        cursor.execute('DELETE FROM historial_apuestas WHERE usuario = %s', (usuario,))
        cursor.execute('DELETE FROM usuarios WHERE usuario = %s', (usuario,))
        conn.commit()
        
        LogModel.registrar(
            tipo='usuario',
            titulo='🗑️ Usuario Eliminado',
            descripcion=f'Usuario eliminado: {usuario}',
            usuario='ADMIN',
            nivel='WARNING'
        )
        return redirect(url_for('admin.vista_admin', exito="usuario_eliminado"))
    except Exception as e:
        conn.rollback()
        LogModel.registrar(
            tipo='error',
            titulo='❌ Error al Eliminar Usuario',
            descripcion=f'Usuario: {usuario}',
            usuario='ADMIN',
            detalles=str(e)
        )
        return redirect(url_for('admin.vista_admin', error="error_eliminar_usuario"))
    finally:
        release_db(conn)


@admin_bp.route('/eliminar_usuarios_selecionados', methods=['POST'])
@login_required
def eliminar_usuarios_selecionados():
    """Elimina múltiples usuarios seleccionados via checkboxes."""
    usuarios_str = request.form.get('usuarios_selecionados', '')
    if not usuarios_str:
        return redirect(url_for('admin.vista_admin', error="no_usuarios_selecionados"))
    
    usuarios = [u.strip() for u in usuarios_str.split(',') if u.strip()]
    if not usuarios:
        return redirect(url_for('admin.vista_admin', error="no_usuarios_selecionados"))
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        for usuario in usuarios:
            # Eliminar de tablas relaciondas primero (por FK)
            cursor.execute('DELETE FROM usuarios_bonificacion WHERE usuario = %s', (usuario,))
            cursor.execute('DELETE FROM apuestas WHERE usuario = %s', (usuario,))
            cursor.execute('DELETE FROM historial_apuestas WHERE usuario = %s', (usuario,))
            cursor.execute('DELETE FROM usuarios WHERE usuario = %s', (usuario,))
        
        conn.commit()
        
        LogModel.registrar(
            tipo='usuario',
            titulo='🗑️ Usuarios Eliminados (Masivo)',
            descripcion=f'Usuarios eliminados: {", ".join(usuarios)}',
            usuario='ADMIN',
            nivel='WARNING'
        )
        return redirect(url_for('admin.vista_admin', exito=f"{len(usuarios)}_usuarios_eliminados"))
    except Exception as e:
        conn.rollback()
        LogModel.registrar(
            tipo='error',
            titulo='❌ Error al Eliminar Usuarios',
            descripcion=f'Usuarios: {usuarios_str}',
            usuario='ADMIN',
            detalles=str(e)
        )
        return redirect(url_for('admin.vista_admin', error="error_eliminar_usuarios"))
    finally:
        release_db(conn)


@admin_bp.route('/eliminar_usuarios_teste', methods=['POST'])
@login_required
def eliminar_usuarios_teste():
    """Elimina usuarios de teste (que empiezan con 'test_' o 'teste_')."""
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Buscar usuarios de teste
        cursor.execute(
            "SELECT usuario FROM usuarios WHERE usuario LIKE 'test_%' OR usuario LIKE 'teste_%'"
        )
        usuarios_teste = [row['usuario'] for row in cursor.fetchall()]
        
        if not usuarios_teste:
            return redirect(url_for('admin.vista_admin', error="no_usuarios_teste"))
        
        # Eliminar de tablas relacionadas
        for usuario in usuarios_teste:
            cursor.execute('DELETE FROM usuarios_bonificacion WHERE usuario = %s', (usuario,))
            cursor.execute('DELETE FROM apuestas WHERE usuario = %s', (usuario,))
            cursor.execute('DELETE FROM historial_apuestas WHERE usuario = %s', (usuario,))
            cursor.execute('DELETE FROM usuarios WHERE usuario = %s', (usuario,))
        
        conn.commit()
        
        LogModel.registrar(
            tipo='usuario',
            titulo='🧪 Usuarios de Teste Eliminados',
            descripcion=f'{len(usuarios_teste)} usuarios de teste eliminados',
            usuario='ADMIN',
            nivel='WARNING'
        )
        return redirect(url_for('admin.vista_admin', exito=f"{len(usuarios_teste)}_usuarios_teste_eliminados"))
    except Exception as e:
        conn.rollback()
        LogModel.registrar(
            tipo='error',
            titulo='❌ Error al Eliminar Usuarios de Teste',
            usuario='ADMIN',
            detalles=str(e)
        )
        return redirect(url_for('admin.vista_admin', error="error_eliminar_testes"))
    finally:
        release_db(conn)


@admin_bp.route('/editar_usuario', methods=['POST'])
@login_required
def editar_usuario():
    """Edita los datos de un usuario (PIN, saldo, email, telefono)."""
    usuario = request.form.get('usuario_original', '').strip().lower()
    nuevo_usuario = request.form.get('usuario_nuevo', '').strip().lower()
    pin = request.form.get('pin_nuevo', '').strip()
    saldo = request.form.get('saldo_nuevo', '')
    email = request.form.get('email_nuevo', '').strip() or None
    telefono = request.form.get('telefono_nuevo', '').strip() or None
    
    if not usuario:
        return redirect(url_for('admin.vista_admin', error="usuario_no_especificado"))
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Si cambió el nombre de usuario, validar que no exista el nuevo
        if nuevo_usuario and nuevo_usuario != usuario:
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE usuario = %s', (nuevo_usuario,))
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                return redirect(url_for('admin.vista_admin', error="usuario_duplicado"))
        
        # Validar unicidad de email si cambió
        if email:
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE email = %s AND usuario != %s', (email, usuario))
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                return redirect(url_for('admin.vista_admin', error="email_duplicado"))
        
        # Validar unicidad de telefono si cambió
        if telefono:
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE telefono = %s AND usuario != %s', (telefono, usuario))
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                return redirect(url_for('admin.vista_admin', error="telefono_duplicado"))
        
        # Actualizar datos
        update_fields = []
        params = []
        
        if nuevo_usuario and nuevo_usuario != usuario:
            update_fields.append('usuario = %s')
            params.append(nuevo_usuario)
            # Actualizar en tablas relacionadas
            cursor.execute('UPDATE usuarios_bonificacion SET usuario = %s WHERE usuario = %s', (nuevo_usuario, usuario))
            cursor.execute('UPDATE apuestas SET usuario = %s WHERE usuario = %s', (nuevo_usuario, usuario))
            cursor.execute('UPDATE historial_apuestas SET usuario = %s WHERE usuario = %s', (nuevo_usuario, usuario))
        
        if pin:
            update_fields.append('pin = %s')
            params.append(pin)
        
        if saldo != '':
            try:
                saldo_float = float(saldo)
                update_fields.append('saldo = %s')
                params.append(saldo_float)
            except ValueError:
                conn.rollback()
                return redirect(url_for('admin.vista_admin', error="saldo_invalido"))
        
        if email is not None:
            update_fields.append('email = %s')
            params.append(email)
        
        if telefono is not None:
            update_fields.append('telefono = %s')
            params.append(telefono)
        
        if update_fields:
            params.append(nuevo_usuario if nuevo_usuario and nuevo_usuario != usuario else usuario)
            cursor.execute(
                f"UPDATE usuarios SET {', '.join(update_fields)} WHERE usuario = %s",
                params
            )
            conn.commit()
            
            LogModel.registrar(
                tipo='usuario',
                titulo='✏️ Usuario Editado',
                descripcion=f'Usuario modificado: {usuario}',
                usuario='ADMIN',
                detalles={'cambios': update_fields}
            )
            return redirect(url_for('admin.vista_admin', exito="usuario_editado"))
        else:
            return redirect(url_for('admin.vista_admin', error="sin_cambios"))
    except Exception as e:
        conn.rollback()
        LogModel.registrar(
            tipo='error',
            titulo='❌ Error al Editar Usuario',
            descripcion=f'Usuario: {usuario}',
            usuario='ADMIN',
            detalles=str(e)
        )
        return redirect(url_for('admin.vista_admin', error="error_editar_usuario"))
    finally:
        release_db(conn)


@admin_bp.route('/guardar_partido', methods=['POST'])
@login_required
def guardar_partido():
    """Actualiza configuración del partido y todos los parámetros del formulario."""
    try:
        cambios = []
        campos = [
            'partido_actual', 'comision', 'min_apuesta', 'max_apuesta',
            'cuota_maxima', 'bono_registro', 'bono_primer_apostador',
            'cierre_minutos_antes', 'saldo_semilla', 'pozo_acumulado',
            'api_key'
        ]
        
        for campo in campos:
            valor_nuevo = request.form.get(campo)
            if valor_nuevo is not None and valor_nuevo.strip() != '':
                valor_anterior = get_config(campo)
                if str(valor_anterior) != valor_nuevo.strip():
                    cambios.append(f"{campo}: {valor_anterior} → {valor_nuevo.strip()}")
                    set_config(campo, valor_nuevo.strip())
        
        # Registrar evento en log
        if cambios:
            ip = request.environ.get('HTTP_X_REAL_IP', request.environ.get('REMOTE_ADDR', 'N/A'))
            user_agent = request.environ.get('HTTP_USER_AGENT', 'N/A')
            LogModel.registrar(
                tipo='config',
                titulo='⚙ Configuración Actualizada',
                descripcion=f'{len(cambios)} parámetro(s) modificado(s)',
                usuario='ADMIN',
                detalles={
                    'cambios': cambios,
                    'ip': ip,
                    'user_agent': user_agent
                }
            )
        
        return redirect(url_for('admin.vista_admin', exito="config_actualizada"))
    except Exception as e:
        LogModel.registrar(
            tipo='error',
            titulo='❌ Error al Actualizar Configuración',
            descripcion=str(e),
            usuario='ADMIN'
        )
        return redirect(url_for('admin.vista_admin', error=f"error_guardado: {e}"))


@admin_bp.route('/partidos_api', methods=['GET'])
@login_required
def partidos_api():
    """Busca partidos externos y devuelve opciones para el admin."""
    partidos = obtener_partidos_externos()
    if not partidos:
        return jsonify({
            "partidos": [],
            "error": "No se encontraron partidos programados o error en las APIs disponibles."
        }), 200

    return jsonify({"partidos": partidos}), 200


@admin_bp.route('/configurar_reglas_pro', methods=['POST'])
@login_required
def configurar_reglas_pro():
    """Actualiza los parámetros del escudo anti-pérdidas."""
    try:
        from app.services.db import transaction
        reglas = ['cuota_minima_garantizada', 'sacrificio_comision', 'bloqueo_mercado']
        with transaction() as cursor:
            for regla_id in reglas:
                activa = 1 if request.form.get(f'check_{regla_id}') else 0
                valor  = request.form.get(f'valor_{regla_id}', 0.0)
                cursor.execute(
                    'UPDATE admin_shield_rules SET activa=%s, valor_numerico=%s WHERE estrategia_id=%s',
                    (activa, valor, regla_id)
                )
        return redirect(url_for('admin.vista_admin', exito="reglas_actualizadas"))
    except Exception as e:
        return redirect(url_for('admin.vista_admin', error="error_reglas"))


@admin_bp.route('/reset_reglas', methods=['POST'])
@login_required
def reset_reglas():
    """Resetea todas las reglas del juego a valores por defecto (ceros)."""
    try:
        campos_reset = [
            ('saldo_semilla', '0.0'),
            ('pozo_acumulado', '0.0'),
            ('min_apuesta', '20.0'),
            ('max_apuesta', '200.0'),
            ('cuota_maxima', '10.0'),
            ('comision', '10.0'),
            ('bono_registro', '5.0'),
            ('bono_primer_apostador', '1.3'),
            ('cierre_minutos_antes', '5'),
        ]
        
        for campo, valor_default in campos_reset:
            set_config(campo, valor_default)
        
        return redirect(url_for('admin.vista_admin', exito="reglas_reseteadas"))
    except Exception as e:
        return redirect(url_for('admin.vista_admin', error=f"error_reset: {e}"))


@admin_bp.route('/finalizar_rodada', methods=['POST'])
@login_required
def admin_finalizar_rodada():
    """
    LIQUIDACIÓN COMPLETA: paga premios, registra ganancia de la casa y limpia apuestas.
    Usa el motor procesar_limpiar_pozo_completo() de calculos.py.
    """
    resultado_ganador = request.form.get('resultado_final', '').strip()
    if not resultado_ganador:
        return redirect(url_for('admin.vista_admin', error="debe_seleccionar_resultado"))

    ok, mensaje = procesar_limpiar_pozo_completo(resultado_ganador)
    if ok:
        # Registrar evento exitoso
        LogModel.registrar(
            tipo='success',
            titulo='✅ Rodada Finalizada',
            descripcion=f'Resultado ganador: {resultado_ganador}',
            usuario='ADMIN',
            detalles=mensaje
        )
        return redirect(url_for('admin.vista_admin', exito=mensaje))
    else:
        # Registrar evento de error
        LogModel.registrar(
            tipo='error',
            titulo='❌ Error al Finalizar Rodada',
            descripcion=f'Resultado: {resultado_ganador}',
            usuario='ADMIN',
            detalles=mensaje
        )
        return redirect(url_for('admin.vista_admin', error=mensaje))


@admin_bp.route('/limpiar_pozo', methods=['POST'])
@login_required
def admin_limpiar_pozo():
    """
    RESET PURO: borra apuestas activas SIN pagar ni registrar.
    Solo para correcciones de prueba o errores de carga.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM apuestas")
        conn.commit()
        return redirect(url_for('admin.vista_admin', exito="pozo_limpiado_sin_liquidar"))
    except Exception as e:
        conn.rollback()
        return redirect(url_for('admin.vista_admin', error="error_limpieza"))
    finally:
        release_db(conn)


@admin_bp.route('/simulador')
@login_required
def simulador():
    return render_template('simulador.html')


@admin_bp.route('/api/liquidar', methods=['POST'])
@login_required
def liquidar_partido_api():
    """Endpoint JSON para liquidar desde el panel de simulación."""
    datos = request.get_json() or {}
    pronostico_ganador = datos.get('ganador', '').strip()

    if not pronostico_ganador:
        return jsonify({"status": "error", "mensaje": "Falta el pronóstico ganador."}), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(monto) FROM apuestas")
        total_bruto = float(cursor.fetchone()[0] or 0.0)

        if total_bruto == 0:
            return jsonify({"status": "error", "mensaje": "No hay fondos en el pozo."}), 400

        cursor.execute(
            "SELECT SUM(monto) FROM apuestas WHERE pronostico = %s",
            (pronostico_ganador,)
        )
        total_ganador = float(cursor.fetchone()[0] or 0.0)

        comision_pct    = float(set_config.__module__ and __import__(
            'app.models.configuracion', fromlist=['get_config']
        ).get_config('comision') or 10)
        comision_casa   = total_bruto * (comision_pct / 100)
        monto_repartible = total_bruto - comision_casa
        cuota_maxima    = float(__import__(
            'app.models.configuracion', fromlist=['get_config']
        ).get_config('cuota_maxima') or 10.0)
        cuota_final     = min(
            (monto_repartible / total_ganador if total_ganador > 0 else 0),
            cuota_maxima
        )

        cursor.execute("DELETE FROM apuestas")
        conn.commit()

        return jsonify({
            "status": "success",
            "balance": {
                "total_recaudado":   round(total_bruto, 2),
                "comision_aplicada": round(comision_casa, 2),
                "cuota_aplicada":    round(cuota_final, 2),
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "mensaje": str(e)}), 500
    finally:
        release_db(conn)


# ===== NGROK CONTROL =====
@admin_bp.route('/ngrok/start', methods=['POST'])
@login_required
def ngrok_start():
    """Inicia el túnel ngrok."""
    global ngrok_process, ngrok_url
    
    if ngrok_process and ngrok_process.poll() is None:
        return jsonify({"status": "warning", "message": "ngrok ya está en ejecución", "url": ngrok_url})
    
    try:
        # Iniciar ngrok
        cmd = ['ngrok', 'http', '5000', '--log', 'stdout']
        
        ngrok_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )
        
        # Esperar a que ngrok inicie y obtener URL
        time.sleep(3)
        
        # Obtener URL de ngrok API
        try:
            import requests
            response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=5)
            if response.ok:
                data = response.json()
                if data.get('tunnels'):
                    ngrok_url = data['tunnels'][0]['public_url']
                    LogModel.registrar(
                        tipo='config',
                        titulo='🚀 Ngrok Iniciado',
                        descripcion=f'URL: {ngrok_url}',
                        usuario='ADMIN'
                    )
                    return jsonify({"status": "ok", "message": "ngrok iniciado", "url": ngrok_url})
        except Exception as e:
            pass
        
        return jsonify({"status": "ok", "message": "ngrok iniciado (verificando URL...)", "url": None})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/ngrok/stop', methods=['POST'])
@login_required
def ngrok_stop():
    """Detiene el túnel ngrok."""
    global ngrok_process, ngrok_url
    
    if not ngrok_process or ngrok_process.poll() is not None:
        ngrok_process = None
        ngrok_url = None
        return jsonify({"status": "warning", "message": "ngrok no está en ejecución"})
    
    try:
        # Matar el proceso y su grupo
        os.killpg(os.getpgid(ngrok_process.pid), signal.SIGTERM)
        ngrok_process.wait(timeout=5)
        ngrok_process = None
        ngrok_url = None
        
        LogModel.registrar(
            tipo='config',
            titulo='🛑 Ngrok Detenido',
            descripcion='Túnel ngrok cerrado',
            usuario='ADMIN'
        )
        return jsonify({"status": "ok", "message": "ngrok detenido"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/ngrok/status', methods=['GET'])
@login_required
def ngrok_status():
    """Verifica el estado de ngrok."""
    global ngrok_process, ngrok_url
    
    if ngrok_process and ngrok_process.poll() is None:
        # Intentar obtener URL si no la tenemos
        if not ngrok_url:
            try:
                import requests
                response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=2)
                if response.ok:
                    data = response.json()
                    if data.get('tunnels'):
                        ngrok_url = data['tunnels'][0]['public_url']
            except:
                pass
        return jsonify({"status": "running", "url": ngrok_url})
    else:
        ngrok_process = None
        ngrok_url = None
        return jsonify({"status": "stopped", "url": None})
