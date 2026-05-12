from app.services.db import obtener_conexion, transaction
from app.database import get_db, release_db
import psycopg2.extras
from app.models.configuracion import get_config
from app.models.apuesta import ApuestaModel
from app.models.usuario import UsuarioModel
from app.models.ganancia import GananciaModel
from app.models.log import LogModel

def calcular_pozo_visible(pozo_bruto):
    """Calcula el pozo visible descontando la comisión base proyectada."""
    comision_pct = float(get_config('comision') or 20)
    factor = (100 - comision_pct) / 100.0
    pozo_visible = pozo_bruto * factor
    
    return pozo_visible


def extraer_equipos_partido(partido_str):
    """Separa el string 'Equipo A vs Equipo B - Info' en dos equipos."""
    if not partido_str or " vs " not in partido_str:
        return "Local", "Visitante"
    partes = partido_str.split(" vs ")
    op1 = partes[0].strip()
    op2 = partes[1].split("-")[0].strip() if len(partes) > 1 else "Visitante"
    return op1, op2


def obtener_reglas_escudo():
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(
            'SELECT estrategia_id, nombre, activa, valor_numerico FROM admin_shield_rules'
        )
        reglas = {row['estrategia_id']: row for row in cursor.fetchall()}
        cursor.close()
        return reglas
    finally:
        release_db(conn)


def calcular_recomendaciones_escudo(total_bruto, distribucion):
    reglas = obtener_reglas_escudo()
    total_apostado = sum(distribucion.values())

    if total_apostado <= 0 or total_bruto <= 0:
        return {
            'summary': 'No hay apuestas activas para evaluar el escudo.',
            'situacion': 'estabilidad',
            'suggestions': [],
            'meta': {
                'total_bruto': float(total_bruto),
                'total_apostado': float(total_apostado)
            }
        }

    comision_pct = float(get_config('comision') or 20)
    comision_base = total_bruto * (comision_pct / 100)
    cuota_min = float(reglas.get('cuota_minima_garantizada', {}).get('valor_numerico', 1.0))
    sacrificio_pct = float(reglas.get('sacrificio_comision', {}).get('valor_numerico', 0.0))

    evaluaciones = []
    for pronostico, monto in distribucion.items():
        cuota = (total_bruto - comision_base) / monto if monto > 0 else float('inf')
        share = monto / total_apostado if total_apostado > 0 else 0.0
        evaluaciones.append({
            'pronostico': pronostico,
            'monto': float(monto),
            'cuota': float(cuota),
            'share': float(share)
        })

    peor = min(evaluaciones, key=lambda x: x['cuota'])
    mayor_exposicion = max(evaluaciones, key=lambda x: x['share'])

    cuotas_con_sacrificio = {
        e['pronostico']: float((total_bruto - total_bruto * (sacrificio_pct / 100)) / e['monto'])
        if e['monto'] > 0 else float('inf') for e in evaluaciones
    }

    recomendaciones = []

    recomendaciones.append({
        'type': 'sacrificio_comision',
        'label': 'Sacrificio de Comisión',
        'active': bool(reglas.get('sacrificio_comision', {}).get('activa')),
        'valor': sacrificio_pct,
        'recommended': peor['cuota'] < 1.0 and cuotas_con_sacrificio[peor['pronostico']] >= 1.0,
        'reason': f"La cuota proyectada para '{peor['pronostico']}' es {peor['cuota']:.2f}. Reduciendo la comisión al {sacrificio_pct:.1f}% la cuota sería {cuotas_con_sacrificio[peor['pronostico']]:.2f}.",
        'impact': {
            'cuota_actual': peor['cuota'],
            'cuota_con_sacrificio': cuotas_con_sacrificio[peor['pronostico']],
            'pronostico': peor['pronostico']
        }
    })

    recomendaciones.append({
        'type': 'cuota_minima_garantizada',
        'label': 'Cuota Mínima Garantizada',
        'active': bool(reglas.get('cuota_minima_garantizada', {}).get('activa')),
        'valor': cuota_min,
        'recommended': peor['cuota'] < cuota_min,
        'reason': f"La cuota para '{peor['pronostico']}' es {peor['cuota']:.2f}, por debajo del mínimo garantizado de {cuota_min:.2f}.",
        'impact': {
            'cuota_actual': peor['cuota'],
            'cuota_minima': cuota_min,
            'pronostico': peor['pronostico']
        }
    })

    bloqueo_recomendado = mayor_exposicion['share'] >= 0.65 or peor['cuota'] < 0.8
    recomendaciones.append({
        'type': 'bloqueo_mercado',
        'label': 'Bloqueo de Mercado',
        'active': bool(reglas.get('bloqueo_mercado', {}).get('activa')),
        'valor': float(reglas.get('bloqueo_mercado', {}).get('valor_numerico', 0.0)),
        'recommended': bloqueo_recomendado,
        'reason': f"El pronóstico con mayor exposición es '{mayor_exposicion['pronostico']}' con {mayor_exposicion['share']*100:.0f}% del pozo y cuota {mayor_exposicion['cuota']:.2f}.",
        'impact': {
            'share': mayor_exposicion['share'],
            'cuota': mayor_exposicion['cuota'],
            'pronostico': mayor_exposicion['pronostico']
        }
    })

    situacion = 'riesgo' if any(r['recommended'] for r in recomendaciones) else 'estabilidad'
    resumen = 'Se recomienda ajustar el escudo anti-pérdidas.' if situacion == 'riesgo' else 'El sistema no requiere intervención de escudo en este momento.'

    return {
        'summary': resumen,
        'situacion': situacion,
        'suggestions': recomendaciones,
        'meta': {
            'total_bruto': float(total_bruto),
            'total_apostado': float(total_apostado),
            'peor_cuota': peor['cuota'],
            'mayor_exposicion': mayor_exposicion
        }
    }


def aplicar_escudo_anti_perdidas(pozo_bruto, total_apostado_ganador, comision_casa):
    """
    Aplica las estrategias del escudo anti-pérdidas antes de repartir premios.
    Retorna (cuota_final, comision_final).
    """
    from app.database import get_db, release_db
    import psycopg2.extras
    
    # Convertir a float para evitar errores con Decimal
    pozo_bruto = float(pozo_bruto)
    total_apostado_ganador = float(total_apostado_ganador)
    comision_casa = float(comision_casa)
    
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
        total_bruto = float(ApuestaModel.obtener_suma_todas())
        partido_str = get_config('partido_actual')
        
        # 1. Variables base
        comision_porcentaje = float(get_config('comision') or 20)
        comision_casa = total_bruto * (comision_porcentaje / 100.0)
        monto_repartible = total_bruto - comision_casa
        
        # 2. Transacción Atómica (Unit of Work)
        with transaction() as cursor:
            
            cursor.execute(
                'SELECT SUM(monto) FROM apuestas WHERE pronostico = %s',
                (resultado_ganador,)
            )
            total_apostado_ganador = float(cursor.fetchone()[0] or 0.0)
            
            # Variables para calcular pagos
            cuota_final = 0.0
            comision_final = comision_casa
            
            # Cuota con escudo y tope máximo
            cuota_maxima = float(get_config('cuota_maxima') or 10.0)
            
            if total_apostado_ganador > 0:
                # Aplicar escudo anti-pérdidas
                cuota_calculada, comision_final = aplicar_escudo_anti_perdidas(
                    total_bruto, total_apostado_ganador, comision_casa
                )
                # monto_repartible se recalcula según comisión final del escudo
                monto_repartible = total_bruto - comision_final
                cuota_final = min(cuota_calculada, cuota_maxima)
            else:
                # Nadie apostó al ganador: casa se queda con TODO
                cuota_final = 0.0
                monto_repartible = 0.0  # No se reparte nada
            
            # Bono al primer apostador
            primer_apostador = ApuestaModel.obtener_primer_apostador()
            multiplicador_primer_ap = float(get_config('bono_primer_apostador') or 1.3)
            
            total_pagado_a_usuarios = 0.0
            cursor.execute('SELECT usuario, monto, pronostico FROM apuestas')
            apuestas_actuales = cursor.fetchall()
            
            
            for apuesta in apuestas_actuales:
                premio_final = 0.0
                ap_usuario    = apuesta[0]
                ap_monto      = float(apuesta[1])
                ap_pronostico = apuesta[2]
                
                
                if ap_pronostico == resultado_ganador and cuota_final > 0:
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
        # Ganancia = comisión + excedente (lo que sobró después de pagar a ganadores)
        excedente = max(total_bruto - comision_final - total_pagado_a_usuarios, 0.0)
        ganancia_total_admin = comision_final + excedente
        
        GananciaModel.registrar_ganancia(
            ganancia_total_admin,
            f"Liquidación: {partido_str} | Bruto: R${total_bruto:.2f} | "
            f"Comisión: R${comision_casa:.2f} | Excedente: R${excedente:.2f}"
        )
        
        # 4. Enviar notificaciones por email a todos los usuarios
        try:
            from app.services.email_service import notificar_cierre_partido
            
            # Nueva conexión para notificaciones (el cursor de la transacción se cerró)
            conn_notif = get_db()
            try:
                cursor_notif = conn_notif.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                cursor_notif.execute(
                    "SELECT usuario, pronostico, monto, premio, resultado FROM historial_apuestas "
                    "WHERE fecha_registro >= (SELECT MAX(fecha_registro) FROM historial_apuestas) - interval '1 hour'"
                )
                usuarios_notificar = cursor_notif.fetchall()
                
                for row in usuarios_notificar:
                    usuario_notif = row[0]
                    pronostico_notif = row[1]
                    monto_notif = float(row[2] or 0)
                    premio_notif = float(row[3] or 0)
                    resultado_notif = row[4]
                    
                    # Obtener email y saldo actual
                    cursor_notif.execute("SELECT email, saldo FROM usuarios WHERE usuario = %s", (usuario_notif,))
                    user_info = cursor_notif.fetchone()
                    if user_info and user_info[0]:
                        email_notif = user_info[0]
                        saldo_notif = float(user_info[1] or 0)
                        saldo_anterior = saldo_notif - premio_notif if premio_notif > 0 else saldo_notif
                        notificar_cierre_partido(
                            usuario_notif, email_notif,
                            pronostico_notif, resultado_notif,
                            premio_notif, saldo_anterior, saldo_notif
                        )
                
                cursor_notif.close()
            finally:
                release_db(conn_notif)
                
        except Exception as e:
            LogModel.registrar(
                tipo='error',
                titulo='❌ Error Notificaciones Email',
                descripcion=str(e),
                usuario='SISTEMA'
            )
        
        return True, f"Pozo finalizado. Ganancia Casa: R${ganancia_total_admin:.2f}"

    except Exception as e:
        LogModel.log_exception(e, tipo='error', titulo='❌ Error en procesamiento de liquidación', nivel='CRITICAL')
        return False, f"Error en procesamiento: {str(e)}"