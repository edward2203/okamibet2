# app/routes/api.py
from flask import request, jsonify
from . import api_bp
from app.database import get_db, release_db
from app.models.configuracion import get_config
from app.models.apuesta import ApuestaModel
from app.services.calculos import extraer_equipos_partido, calcular_recomendaciones_escudo
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

    if not usuario:
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
        return jsonify({
            "existe":       True,
            "saldo":        float(usuario_data['saldo']),
            "pin_correcto": pin_correcto,
        })
    return jsonify({"existe": False})


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
