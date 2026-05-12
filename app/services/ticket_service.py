from app.services.bot_bridge import responder_cliente_whatsapp
from app.services.email_service import send_email
from app.models.configuracion import get_config
from app.database import get_db, release_db
import psycopg2.extras
import datetime

def generar_ticket(apuesta_id):
    """Genera el texto del ticket de apuesta."""
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM apuestas WHERE id = %s", (apuesta_id,))
        apuesta = cursor.fetchone()
        if not apuesta:
            return None, "Apuesta no encontrada"
        
        ticket_num = f"TICKET-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{apuesta_id}"
        comision = float(get_config('comision') or 10)
        cuota_maxima = float(get_config('cuota_maxima') or 10.0)
        expected_profit = apuesta['monto'] * cuota_maxima * (1 - comision/100)
        
        ticket = f"🎟️ TICKET DE APUESTA\n"
        ticket += f"Número: {ticket_num}\n"
        ticket += f"Fecha: {apuesta['fecha']}\n"
        ticket += f"Usuario: {apuesta['usuario']}\n"
        ticket += f"Apostó a: {apuesta['pronostico']}\n"
        ticket += f"Monto apostado: R$ {apuesta['monto']:.2f}\n"
        ticket += f"Ganancia prevista: R$ {expected_profit:.2f}\n"
        ticket += f"--- Okami Bet v4 ---"
        
        return ticket, None
    except Exception as e:
        return None, str(e)
    finally:
        release_db(conn)

def enviar_ticket_whatsapp(telefono, ticket_text):
    """Envía el ticket vía WhatsApp."""
    try:
        responder_cliente_whatsapp(telefono, ticket_text)
        return True, "Ticket enviado via WhatsApp"
    except Exception as e:
        return False, str(e)

def enviar_ticket_email(email, ticket_text, platform_email):
    """Envía el ticket vía email con copia a la plataforma."""
    try:
        subject = "Ticket de Apuesta - Okami Bet"
        send_email(email, subject, ticket_text, cc_email=platform_email)
        return True, "Ticket enviado via Email"
    except Exception as e:
        return False, str(e)

def procesar_envio_ticket(usuario, apuesta_id):
    """Procesa el envío del ticket vía WhatsApp y Email."""
    from app.models.log import LogModel
    
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT telefono, email FROM usuarios WHERE usuario = %s", (usuario,))
        user_info = cursor.fetchone()
        if not user_info:
            return False, "Usuario no encontrado"
        
        ticket_text, error = generar_ticket(apuesta_id)
        if error:
            return False, error
        
        resultados = []
        # Enviar via WhatsApp
        if user_info['telefono']:
            ok, msg = enviar_ticket_whatsapp(user_info['telefono'], ticket_text)
            resultados.append(f"WhatsApp: {msg}")
            LogModel.registrar(
                tipo='ticket',
                titulo='📱 Ticket Enviado via WhatsApp',
                descripcion=f'Usuario: {usuario}, Ticket: {ticket_text.split("Número: ")[1].split()[0] if "Número: " in ticket_text else "N/A"}',
                usuario=usuario,
                detalles={'canal': 'whatsapp', 'telefono': user_info['telefono']}
            )
        
        # Enviar via Email
        platform_email = get_config('platform_email')
        if user_info['email'] and platform_email:
            ok, msg = enviar_ticket_email(user_info['email'], ticket_text, platform_email)
            resultados.append(f"Email: {msg}")
            LogModel.registrar(
                tipo='ticket',
                titulo='✉️ Ticket Enviado via Email',
                descripcion=f'Usuario: {usuario}, Email: {user_info["email"]}',
                usuario=usuario,
                detalles={'canal': 'email', 'email': user_info['email'], 'cc': platform_email}
            )
        
        return True, "; ".join(resultados)
    except Exception as e:
        return False, str(e)
    finally:
        release_db(conn)
