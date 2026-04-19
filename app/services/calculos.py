from app.services.db import obtener_conexion, transaction
from app.models.configuracion import get_config
from app.models.apuesta import ApuestaModel
from app.models.usuario import UsuarioModel
from app.models.ganancia import GananciaModel


def calcular_pozo_visible(pozo_bruto):
    """Calcula el pozo visible descontando la comisión base proyectada."""
    comision_pct = float(get_config('comision') or 20)
    factor = (100 - comision_pct) / 100.0
    return pozo_bruto * factor


def extraer_equipos_partido(partido_str):
    """Separa el string 'Equipo A vs Equipo B - Info' en dos equipos."""
    if not partido_str or " vs " not in partido_str:
        return "Local", "Visitante"
    partes = partido_str.split(" vs ")
    op1 = partes[0].strip()
    op2 = partes[1].split("-")[0].strip() if len(partes) > 1 else "Visitante"
    return op1, op2


def aplicar_escudo_anti_perdidas(pozo_bruto, total_apostado_ganador, comision_casa):
    """
    Aplica las estrategias del escudo anti-pérdidas antes de repartir premios.
    Retorna (cuota_final, comision_final).
    """
    from app.database import get_db, release_db
    import psycopg2.extras

    conn = get_db()
    rules = {}
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(
            'SELECT estrategia_id, activa, valor_numerico FROM admin_shield_rules'
        )
        for row in cursor.fetchall():
            rules[row['estrategia_id']] = row
        cursor.close()
    finally:
        release_db(conn)

    cuota_sin_escudo = (
        (pozo_bruto - comision_casa) / total_apostado_ganador
        if total_apostado_ganador > 0 else 0.0
    )
    comision_final = comision_casa

    # Estrategia 1: Sacrificio de Comisión
    rule_sac = rules.get('sacrificio_comision', {})
    if rule_sac.get('activa') and cuota_sin_escudo < 1.0:
        comision_final = pozo_bruto * (float(rule_sac['valor_numerico']) / 100)
        cuota_sin_escudo = (pozo_bruto - comision_final) / total_apostado_ganador

    # Estrategia 2: Cuota Mínima Garantizada
    cuota_final = cuota_sin_escudo
    rule_min = rules.get('cuota_minima_garantizada', {})
    if rule_min.get('activa') and cuota_sin_escudo < float(rule_min.get('valor_numerico', 0)):
        cuota_final = float(rule_min['valor_numerico'])

    return cuota_final, comision_final


def procesar_limpiar_pozo_completo(resultado_ganador):
    """
    Servicio de Dominio principal: orquesta la matemática de pagos,
    aplica el escudo anti-pérdidas, calcula excedentes y limpia
    el estado operativo bajo un Unit of Work.
    """
    try:
        total_bruto = ApuestaModel.obtener_suma_todas()
        partido_str = get_config('partido_actual')

        # 1. Variables base
        comision_porcentaje = float(get_config('comision') or 20)
        comision_casa = total_bruto * (comision_porcentaje / 100)
        monto_repartible = total_bruto - comision_casa

        # 2. Transacción Atómica (Unit of Work)
        with transaction() as cursor:

            cursor.execute(
                'SELECT SUM(monto) FROM apuestas WHERE pronostico = %s',
                (resultado_ganador,)
            )
            total_apostado_ganador = cursor.fetchone()[0] or 0.0

            # Cuota con escudo y tope máximo
            cuota_maxima = float(get_config('cuota_maxima') or 10.0)
            if total_apostado_ganador > 0:
                cuota_calculada, comision_casa = aplicar_escudo_anti_perdidas(
                    total_bruto, total_apostado_ganador, comision_casa
                )
                monto_repartible = total_bruto - comision_casa
                cuota_final = min(cuota_calculada, cuota_maxima)
            else:
                cuota_final = 0.0

            # Bono al primer apostador
            primer_apostador = ApuestaModel.obtener_primer_apostador()
            multiplicador_primer_ap = float(get_config('bono_primer_apostador') or 1.3)

            total_pagado_a_usuarios = 0.0
            cursor.execute('SELECT * FROM apuestas')
            apuestas_actuales = cursor.fetchall()

            for apuesta in apuestas_actuales:
                premio_final = 0.0
                # apuesta es tupla: (id, usuario_id, usuario, evento_id, monto, pronostico, deporte, fecha)
                ap_usuario    = apuesta[2]
                ap_monto      = float(apuesta[4])
                ap_pronostico = apuesta[5]

                if ap_pronostico == resultado_ganador:
                    premio_base = ap_monto * cuota_final

                    if ap_usuario == primer_apostador:
                        premio_final = premio_base * multiplicador_primer_ap
                    else:
                        premio_final = premio_base

                    total_pagado_a_usuarios += premio_final

                    cursor.execute(
                        'UPDATE usuarios SET saldo = saldo + %s WHERE usuario = %s',
                        (premio_final, ap_usuario)
                    )

                    # Aciertos consecutivos y bonos VIP
                    aciertos, bono_extra = UsuarioModel.registrar_acierto_consecutivo(
                        ap_usuario, premio_final
                    )
                    if bono_extra > 0:
                        cursor.execute(
                            'UPDATE usuarios SET saldo = saldo + %s WHERE usuario = %s',
                            (bono_extra, ap_usuario)
                        )

                # Historial individual (ganadores y perdedores)
                cursor.execute(
                    '''INSERT INTO historial_apuestas
                       (usuario, monto, pronostico, resultado, premio)
                       VALUES (%s, %s, %s, %s, %s)''',
                    (ap_usuario, ap_monto, ap_pronostico,
                     f"{resultado_ganador} ({cuota_final:.2f}x)", premio_final)
                )

            # Limpiar tabla de apuestas activas (nueva ronda)
            cursor.execute('DELETE FROM apuestas')

        # 3. Fuera de la transacción: registrar ganancias de la casa
        excedente = max(monto_repartible - total_pagado_a_usuarios, 0.0)
        ganancia_total_admin = comision_casa + excedente

        GananciaModel.registrar_ganancia(
            ganancia_total_admin,
            f"Liquidación: {partido_str} | Bruto: R${total_bruto:.2f} | "
            f"Comisión: R${comision_casa:.2f} | Excedente: R${excedente:.2f}"
        )

        return True, f"Pozo finalizado. Ganancia Casa: R${ganancia_total_admin:.2f}"

    except Exception as e:
        return False, f"Error en procesamiento: {str(e)}"