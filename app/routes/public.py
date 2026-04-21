from flask import render_template, request, redirect, url_for
from . import public_bp
from app.models.configuracion import get_config_batch, get_config
from app.models.apuesta import ApuestaModel
from app.models.usuario import UsuarioModel
from app.services.calculos import calcular_pozo_visible, extraer_equipos_partido
from app.services.validacion import verificar_cierre_apuestas, validar_monto_apuesta
from app.services.db import transaction


# ─── Diccionarios estáticos ───────────────────────────────────────────────────
DICCIONARIO_IDIOMAS = {
    "es": {
        "ganador_txt": "ganó",
        "cuota_txt": "Cuota",
        "pozo_txt": "Pozo Total",
        "participantes_txt": "Apostadores",
        "header_subtitle": "Hoy 16:00",
        "usuario_label": "Usuario",
        "pin_label": "PIN",
        "pin_placeholder": "••••",
        "monto_label": "Monto de Apuesta",
        "pronostico_label": "Elige Resultado",
        "victoria": "Victoria",
        "empate": "Empate",
        "premio_estimado": "Premio Estimado",
        "cotacao": "Cuota",
        "apuesta": "Apuesta",
        "lucro_puro": "Lucro neto",
        "apostar_btn": "APOSTAR AHORA",
        "solicitar_btn": "SOLICITAR REGISTRO / SALDO",
        "minimo_apuesta": "Apuesta mínima",
        "maximo_disponible": "Máximo disponible",
        "pozo_info": "Total oculto para cálculo de pago"
    },
    "pt": {
        "ganador_txt": "ganhou",
        "cuota_txt": "Cota",
        "pozo_txt": "Total Acumulado",
        "participantes_txt": "Apostadores",
        "header_subtitle": "Hoje 16:00",
        "usuario_label": "Usuário",
        "pin_label": "PIN",
        "pin_placeholder": "••••",
        "monto_label": "Valor da Aposta",
        "pronostico_label": "Escolha o Resultado",
        "victoria": "Vitória",
        "empate": "Empate",
        "premio_estimado": "Prêmio Estimado",
        "cotacao": "Cotação",
        "apuesta": "Aposta",
        "lucro_puro": "Lucro puro",
        "apostar_btn": "APOSTAR AGORA",
        "solicitar_btn": "SOLICITAR CADASTRO / SALDO",
        "minimo_apuesta": "Aposta mínima",
        "maximo_disponible": "Máximo disponível",
        "pozo_info": "Total escamoteado para cálculo de pagamento"
    }
}

DEPORTES = {
    "futbol":     {"nombre": "Fútbol",     "icono": "⚽", "liga_default": "BSA"},
    "basketball": {"nombre": "Basketball", "icono": "🏀", "liga_default": "NBA"},
    "baseball":   {"nombre": "Baseball",   "icono": "⚾", "liga_default": "MLB"}
}


# ─── Pantalla principal ───────────────────────────────────────────────────────
@public_bp.route('/')
def inicio():
    """
    Vértice de entrada principal.
    Renderiza el plano de apuestas con inyección de capital semilla.

    Elementos garantizados en pantalla (ref: PANTALLA-PRINCIPAL.jpg):
      • Título del partido + selector de idioma PT/ES
      • PRÊMIO ACUMULADO (pozo visible)
      • Contador CIERRE DE APUESTAS EN
      • Campos: usuario, PIN, monto, dropdown pronóstico
      • Bloque PRÊMIO ESTIMADO + Cotação + Aposta + Lucro puro
      • Botón APOSTAR AGORA
      • Botón SOLICITAR CADASTRO / SALDO
    """
    # 1. Carga batch de configuración (incluye semilla y acumulado)
    configs = get_config_batch([
        'comision', 'cuota_maxima', 'bono_primer_apostador',
        'min_apuesta', 'max_apuesta', 'partido_actual', 'deporte_actual',
        'saldo_semilla', 'pozo_acumulado'
    ])

    deporte_actual = configs.get('deporte_actual', 'futbol')
    deporte_info   = DEPORTES.get(deporte_actual, DEPORTES['futbol'])

    # 2. SUMA MAESTRA: pozo real + inyecciones del administrador
    pozo_real  = ApuestaModel.obtener_suma_todas(deporte_actual)
    semilla    = float(configs.get('saldo_semilla')  or 0.0)
    acumulado  = float(configs.get('pozo_acumulado') or 0.0)

    # Total que usa el sistema para cálculos matemáticos
    total_sistema = pozo_real + semilla + acumulado

    # 3. Pozo visible (descontada la comisión)
    pozo_visible = calcular_pozo_visible(total_sistema)

    lang = request.args.get('lang', 'pt')
    if lang not in DICCIONARIO_IDIOMAS:
        lang = 'pt'

    partido           = configs.get('partido_actual', 'Palmeiras vs São Paulo - Hoje 16:00')
    op1, op2          = extraer_equipos_partido(partido)
    apuestas_cerradas = verificar_cierre_apuestas(partido)

    distribucion     = ApuestaModel.obtener_distribucion(op1, op2, deporte_actual)
    primer_apostador = ApuestaModel.obtener_primer_apostador(deporte_actual) or ""

    return render_template(
        'index.html',
        pozo              = pozo_visible,
        pozo_bruto        = total_sistema,
        dist              = distribucion,
        partido           = partido,
        op1               = op1,
        op2               = op2,
        apuestas_cerradas = apuestas_cerradas,
        comision_pct      = float(configs.get('comision')              or 20.0),
        cuota_max         = float(configs.get('cuota_maxima')          or 10.0),
        min_apuesta       = float(configs.get('min_apuesta')           or 20.0),
        max_apuesta       = float(configs.get('max_apuesta')           or 200.0),
        bono_primer       = float(configs.get('bono_primer_apostador') or 1.3),
        deporte_info      = deporte_info,
        primer_apostador  = primer_apostador,
        saldo_semilla     = semilla,
        pozo_acumulado    = acumulado,
        cierre_minutos_antes = configs.get('cierre_minutos_antes') or 10,
        idiomas           = DICCIONARIO_IDIOMAS,
        idioma           = DICCIONARIO_IDIOMAS[lang],
        lang_actual      = lang
    )


# ─── Simulador ────────────────────────────────────────────────────────────────
@public_bp.route('/simulador.html')
def simulador():
    return render_template('simulador.html')


# ─── Procesar apuesta (acepta ambas rutas) ────────────────────────────────────
@public_bp.route('/procesar_apuesta', methods=['POST'])
@public_bp.route('/apostar',          methods=['POST'])
def procesar_apuesta():
    """
    Vector de procesamiento para inserción de nuevas apuestas.

    Validaciones en orden:
      1. Monto dentro de límites escalares (min/max)
      2. Ventana de tiempo no cerrada
      3. Usuario existe en DB
      4. PIN correcto
      5. Saldo suficiente
      6. Sin apuesta duplicada en la ronda activa
    """
    usuario    = request.form.get('usuario',    '').strip().lower()
    pin        = request.form.get('pin',        '').strip()
    pronostico = request.form.get('pronostico')

    try:
        monto = float(request.form.get('monto', 0))
    except ValueError:
        return redirect(url_for('public.inicio', error="monto_invalido"))

    # Validación 1: Límites escalares
    valido, mensaje_monto = validar_monto_apuesta(monto)
    if not valido:
        return redirect(url_for('public.inicio', error=mensaje_monto))

    # Validación 2: Vector de tiempo
    if verificar_cierre_apuestas(get_config('partido_actual')):
        return redirect(url_for('public.inicio', error="apuestas_cerradas"))

    es_usuario_nuevo = False

    # Transacción atómica
    with transaction() as cursor:
        cursor.execute('''
            SELECT
                COUNT(*)                                              AS tiene_apuesta,
                (SELECT saldo FROM usuarios WHERE usuario = %s)      AS saldo,
                (SELECT pin   FROM usuarios WHERE usuario = %s)      AS pin_guardado
            FROM apuestas
            WHERE usuario = %s
        ''', (usuario, usuario, usuario))
        row = cursor.fetchone()

        # Validaciones 3-6 dentro de la transacción
        if row[1] is None:
            return redirect(url_for('public.inicio', error="usuario_no_existe"))
        if str(row[2]) != str(pin):
            return redirect(url_for('public.inicio', error="pin_incorrecto"))
        if float(row[1]) < monto:
            return redirect(url_for('public.inicio', error="saldo_insuficiente"))
        if row[0] > 0:
            return redirect(url_for('public.inicio', error="apuesta_duplicada"))

        # Bono de bienvenida (solo primera vez)
        cursor.execute(
            'SELECT COUNT(*) FROM usuarios_bonificacion WHERE usuario = %s',
            (usuario,)
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                'INSERT INTO usuarios_bonificacion (usuario) VALUES (%s)',
                (usuario,)
            )
            es_usuario_nuevo = True

        # Descontar saldo y registrar apuesta
        cursor.execute(
            'UPDATE usuarios SET saldo = saldo - %s WHERE usuario = %s',
            (monto, usuario)
        )
        cursor.execute(
            'INSERT INTO apuestas (usuario, monto, pronostico) VALUES (%s, %s, %s)',
            (usuario, monto, pronostico)
        )

    # Bono de bienvenida fuera de la transacción para evitar deadlock
    if es_usuario_nuevo:
        UsuarioModel.aplicar_bono_bienvenida(usuario)

    return redirect(url_for('public.inicio', exito="apuesta_registrada"))