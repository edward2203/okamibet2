from flask import render_template, request, redirect, url_for, Blueprint
from datetime import datetime, timedelta

public_bp = Blueprint('public', __name__)
from app.models.configuracion import get_config_batch, get_config
from app.models.apuesta import ApuestaModel
from app.models.usuario import UsuarioModel
from app.models.log import LogModel
from app.services.calculos import calcular_pozo_visible, extraer_equipos_partido
from app.services.validacion import verificar_cierre_apuestas, validar_monto_apuesta
from app.services.db import transaction
from app.services.ticket_service import procesar_envio_ticket


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

    # 3. Pozo visible: aplicar comisión SOLO a apuestas reales + acumulado (sin semilla)
    pozo_sin_semilla = pozo_real + acumulado
    pozo_visible_sin_semilla = calcular_pozo_visible(pozo_sin_semilla)
    pozo_visible = pozo_visible_sin_semilla + semilla

    lang = request.args.get('lang', 'pt')
    if lang not in DICCIONARIO_IDIOMAS:
        lang = 'pt'

    partido           = configs.get('partido_actual', 'Palmeiras vs São Paulo - Hoje 16:00')
    op1, op2          = extraer_equipos_partido(partido)
    apuestas_cerradas = verificar_cierre_apuestas(partido)

    # Calcular timestamp de cierre para el contador regresivo
    cierre_timestamp = None
    try:
        partes = partido.split(' - ')
        if len(partes) >= 2:
            hora_str = partes[-1].strip().split()[-1]
            if ':' in hora_str:
                horas, minutos = map(int, hora_str.split(':'))
                ahora = datetime.now()
                hora_partido = ahora.replace(hour=horas, minute=minutos, second=0, microsecond=0)
                minutos_cierre = int(configs.get('cierre_minutos_antes') or 10)
                hora_cierre = hora_partido - timedelta(minutes=minutos_cierre)
                cierre_timestamp = int(hora_cierre.timestamp())
    except Exception:
        pass

    distribucion     = ApuestaModel.obtener_distribucion(op1, op2, deporte_actual)
    primer_apostador = ApuestaModel.obtener_primer_apostador(deporte_actual) or ""

    # LOG: Visualización de pantalla de apuestas
    LogModel.registrar(
        tipo='info',
        titulo='📱 Pantalla de Apuestas Visualizada',
        descripcion=f'Usuario accedió a pantalla principal (lang={lang})',
        usuario='ANONIMO',
        detalles={
            'lang': lang,
            'partido': partido,
            'pozo_visible': round(pozo_visible, 2),
            'pozo_bruto': round(total_sistema, 2),
            'semilla': semilla,
            'acumulado': acumulado,
            'pozo_real': pozo_real,
            'deporte': deporte_actual,
            'distribucion': distribucion,
            'apuestas_cerradas': apuestas_cerradas,
            'cierre_timestamp': cierre_timestamp
        }
    )

    return render_template(
        'index.html',
        pozo              = pozo_visible,
        pozo_bruto        = total_sistema,
        dist              = distribucion,
        partido           = partido,
        op1               = op1,
        op2               = op2,
        apuestas_cerradas = apuestas_cerradas,
        cierre_timestamp  = cierre_timestamp,
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
        lang_actual      = lang,
        error_param      = request.args.get('error'),
        exito_param      = request.args.get('exito')
    )


# ─── Simulador ────────────────────────────────────────────────────────────────
@public_bp.route('/simulador.html')
def simulador():
    return render_template('simulador.html')


# ─── Procesar apuesta (acepta ambas rutas) ────────────────────────────
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
        # LOG: Monto inválido
        LogModel.registrar(
            tipo='warning',
            titulo='⚠️ Intento de Apuesta - Monto Inválido',
            descripcion=f'Usuario {usuario} intentó apostar con monto no numérico',
            usuario=usuario,
            detalles={'monto_raw': request.form.get('monto'), 'error': 'ValueError'}
        )
        return redirect(url_for('public.inicio', error="monto_invalido"))

    # LOG: Intento de apuesta (antes de validaciones)
    LogModel.registrar(
        tipo='apuesta',
        titulo='🎲 Intento de Apuesta Registrado',
        descripcion=f'Usuario {usuario} intenta apostar R$ {monto:.2f} a {pronostico}',
        usuario=usuario,
        detalles={
            'usuario': usuario,
            'monto': monto,
            'pronostico': pronostico,
            'pin_length': len(pin),
            'ip': request.environ.get('HTTP_X_REAL_IP', request.environ.get('REMOTE_ADDR', 'N/A')),
            'user_agent': request.environ.get('HTTP_USER_AGENT', 'N/A')
        }
    )

    # Validación 1: Límites escalares
    valido, mensaje_monto = validar_monto_apuesta(monto)
    if not valido:
        LogModel.registrar(
            tipo='warning',
            titulo='⚠️ Apuesta Rechazada - Límite Escalar',
            descripcion=f'Usuario {usuario}: {mensaje_monto}',
            usuario=usuario,
            detalles={'monto': monto, 'valido': valido, 'mensaje': mensaje_monto}
        )
        return redirect(url_for('public.inicio', error=mensaje_monto))

    # Validación 2: Vector de tiempo
    if verificar_cierre_apuestas(get_config('partido_actual')):
        LogModel.registrar(
            tipo='warning',
            titulo='⚠️ Apuesta Rechazada - Apuestas Cerradas',
            descripcion=f'Usuario {usuario} intentó apostar después del cierre',
            usuario=usuario,
            detalles={'monto': monto, 'pronostico': pronostico}
        )
        return redirect(url_for('public.inicio', error="apuestas_cerradas"))

    es_usuario_nuevo = False
    saldo_anterior = 0

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

        saldo_anterior = float(row[1] or 0)

        # Validaciones 3-6 dentro de la transacción
        if row[1] is None:
            LogModel.registrar(
                tipo='warning',
                titulo='⚠️ Apuesta Rechazada - Usuario No Existe',
                descripcion=f'Usuario {usuario} no encontrado en BD',
                usuario=usuario,
                detalles={'usuario': usuario}
            )
            return redirect(url_for('public.inicio', error="usuario_no_existe"))

        if str(row[2]) != str(pin):
            LogModel.registrar(
                tipo='warning',
                titulo='⚠️ Apuesta Rechazada - PIN Incorrecto',
                descripcion=f'Usuario {usuario}: PIN incorrecto',
                usuario=usuario,
                detalles={'usuario': usuario, 'pin_length': len(pin)}
            )
            return redirect(url_for('public.inicio', error="pin_incorrecto"))

        if float(row[1]) < monto:
            LogModel.registrar(
                tipo='warning',
                titulo='⚠️ Apuesta Rechazada - Saldo Insuficiente',
                descripcion=f'Usuario {usuario}: saldo R$ {row[1]:.2f} < apuesta R$ {monto:.2f}',
                usuario=usuario,
                detalles={'saldo': float(row[1]), 'monto': monto, 'faltante': monto - float(row[1])}
            )
            return redirect(url_for('public.inicio', error="saldo_insuficiente"))

        if row[0] > 0:
            LogModel.registrar(
                tipo='warning',
                titulo='⚠️ Apuesta Rechazada - Apuesta Duplicada',
                descripcion=f'Usuario {usuario} ya tiene apuesta activa',
                usuario=usuario,
                detalles={'usuario': usuario, 'monto': monto, 'pronostico': pronostico}
            )
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
            'INSERT INTO apuestas (usuario, monto, pronostico) VALUES (%s, %s, %s) RETURNING id',
            (usuario, monto, pronostico)
        )
        apuesta_id = cursor.fetchone()[0]

    saldo_nuevo = saldo_anterior - monto

    # LOG: Apuesta exitosa
    LogModel.registrar(
        tipo='success',
        titulo='✅ Apuesta Registrada Exitosamente',
        descripcion=f'Usuario {usuario} apostó R$ {monto:.2f} a {pronostico}',
        usuario=usuario,
        detalles={
            'usuario': usuario,
            'monto': monto,
            'pronostico': pronostico,
            'saldo_anterior': saldo_anterior,
            'saldo_nuevo': saldo_nuevo,
            'es_usuario_nuevo': es_usuario_nuevo,
            'bono_aplicado': es_usuario_nuevo
        }
    )

    # Bono de bienvenida fuera de la transacción para evitar deadlock
    if es_usuario_nuevo:
        UsuarioModel.aplicar_bono_bienvenida(usuario)
        LogModel.registrar(
            tipo='success',
            titulo='🎁 Bono de Bienvenida Aplicado',
            descripcion=f'Bono aplicado a nuevo usuario {usuario}',
            usuario=usuario,
            detalles={'usuario': usuario, 'bono': float(get_config('bono_registro') or 5.0)}
        )
    
    # Enviar ticket de comprobación
    try:
        ticket_ok, ticket_msg = procesar_envio_ticket(usuario, apuesta_id)
        if ticket_ok:
            LogModel.registrar(
                tipo='ticket',
                titulo='📱 Ticket Enviado',
                descripcion=ticket_msg,
                usuario=usuario
            )
    except Exception as e:
        LogModel.registrar(
            tipo='error',
            titulo='Error Envío Ticket',
            descripcion=str(e),
            usuario=usuario
        )
    
    return redirect(url_for('public.inicio', exito="apuesta_registrada"))
