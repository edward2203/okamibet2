# app/routes/admin.py
from flask import render_template, request, redirect, url_for, jsonify
from . import admin_bp
from app.services.validacion import validar_acceso_admin
from app.services.calculos import extraer_equipos_partido, procesar_limpiar_pozo_completo
from app.services.football_api import obtener_partidos_externos
from app.models.configuracion import get_config_batch, set_config, get_config
from app.models.log import LogModel
from app.database import get_db, release_db
from app.models.ganancia import GananciaModel
from app.models.apuesta import ApuestaModel
import psycopg2.extras


@admin_bp.route('/')
def vista_admin():
    """Panel de control completo — PostgreSQL con DictCursor."""
    configs = get_config_batch([
        'partido_actual', 'api_key', 'gemini_api_key', 'cuota_maxima',
        'min_apuesta', 'max_apuesta', 'comision', 'bono_registro',
        'cierre_minutos_antes', 'bono_primer_apostador',
        'pozo_acumulado', 'saldo_semilla'
    ])

    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # 1. Usuarios + apuesta activa del mismo usuario en la ronda
        cursor.execute('''
            SELECT u.id, u.usuario, u.pin, u.saldo,
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

    return render_template(
        'admin.html',
        usuarios=usuarios,
        resumen_bolsa=resumen_bolsa,
        op1=op1, op2=op2,
        ganancias_admin=GananciaModel.obtener_historial_admin(),
        historial=historial,
        logs_sistema=LogModel.obtener_ultimos(100),
        configs=configs,
        primer_apostador=ApuestaModel.obtener_primer_apostador() or ''
    )


@admin_bp.route('/crear_usuario', methods=['POST'])
def admin_crear_usuario():
    if not validar_acceso_admin(request.form.get('admin_pass')):
        return redirect(url_for('admin.vista_admin', error="clave_incorrecta"))

    usuario = request.form.get('usuario', '').strip().lower()
    pin     = request.form.get('pin', '').strip()
    try:
        saldo = float(request.form.get('saldo', 0))
    except ValueError:
        return redirect(url_for('admin.vista_admin', error="saldo_invalido"))

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO usuarios (usuario, pin, saldo) VALUES (%s, %s, %s)',
            (usuario, pin, saldo)
        )
        cursor.execute(
            'INSERT INTO usuarios_bonificacion (usuario, bono_bienvenida_usado) VALUES (%s, 1)',
            (usuario,)
        )
        conn.commit()
        
        # Registrar evento en log
        LogModel.registrar(
            tipo='success',
            titulo='👤 Nuevo Usuario Creado',
            descripcion=f'Usuario: {usuario}',
            usuario='ADMIN',
            detalles=f'Saldo inicial: R$ {saldo:.2f}'
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


@admin_bp.route('/guardar_partido', methods=['POST'])
def guardar_partido():
    """Actualiza configuración del partido y todos los parámetros del formulario."""
    # Validar contraseña antes de actualizar
    if not validar_acceso_admin(request.form.get('admin_pass')):
        return redirect(url_for('admin.vista_admin', error="admin_pass_incorrecto"))
    
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
            LogModel.registrar(
                tipo='config',
                titulo='⚙️ Configuración Actualizada',
                descripcion=f'{len(cambios)} parámetro(s) modificado(s)',
                usuario='ADMIN',
                detalles=' | '.join(cambios)
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
def reset_reglas():
    """Resetea todas las reglas del juego a valores por defecto (ceros)."""
    if not validar_acceso_admin(request.form.get('admin_pass')):
        return redirect(url_for('admin.vista_admin', error="clave_incorrecta"))
    
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
        
        return redirect(url_for('admin.vista_admin', exito="reglas_resetadas"))
    except Exception as e:
        return redirect(url_for('admin.vista_admin', error=f"error_reset: {e}"))


@admin_bp.route('/finalizar_rodada', methods=['POST'])
def admin_finalizar_rodada():
    """
    LIQUIDACIÓN COMPLETA: paga premios, registra ganancia de la casa y limpia apuestas.
    Usa el motor procesar_limpiar_pozo_completo() de calculos.py.
    """
    if not validar_acceso_admin(request.form.get('admin_pass')):
        return redirect(url_for('admin.vista_admin', error="clave_incorrecta"))

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
def admin_limpiar_pozo():
    """
    RESET PURO: borra apuestas activas SIN pagar ni registrar.
    Solo para correcciones de prueba o errores de carga.
    """
    if not validar_acceso_admin(request.form.get('admin_pass')):
        return redirect(url_for('admin.vista_admin', error="clave_incorrecta"))

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
def simulador():
    return render_template('simulador.html')


@admin_bp.route('/api/liquidar', methods=['POST'])
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
