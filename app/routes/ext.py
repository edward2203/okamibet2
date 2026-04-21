from flask import Blueprint, request, jsonify
from app.models.configuracion import get_config
from app.services.db import obtener_conexion
from app.services.bot_bridge import notificar_admin_telegram, responder_cliente_whatsapp
import requests

ext_bp = Blueprint('ext', __name__)

# ─── Configuración ───────────────────────────────────────────────────────────
TOKEN_WHATSAPP     = get_config('whatsapp_token')   or "TU_TOKEN_AQUÍ"
ID_TELEFONO        = get_config('whatsapp_phone_id') or "TU_ID_AQUÍ"
TOKEN_VERIFICACION = "okamibet_2026"

TOKEN_TELEGRAM  = get_config('telegram_token')  or "TU_TOKEN_BOT"
CHAT_ADMIN_ID   = get_config('telegram_chat_id') or "TU_CHAT_ID"


# ─── Webhook GET: Verificación Meta ──────────────────────────────────────────
@ext_bp.route('/whatsapp', methods=['GET'])
def verificar_webhook():
    """Meta llama este endpoint para validar el servidor."""
    token     = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if token == TOKEN_VERIFICACION:
        return challenge
    return "Error de verificación", 403


# ─── Webhook POST: Mensajes entrantes (fusionado completo) ───────────────────
@ext_bp.route('/whatsapp', methods=['POST'])
def recibir_mensaje():
    """
    Procesa todos los mensajes entrantes de WhatsApp.
    Flujos soportados:
      • apuesta [usuario] [pin] [monto] [pronostico]  → registra apuesta directa
      • saldo [usuario]                               → consulta saldo
      • registro / registrar                         → notifica admin por Telegram
      • recarga / recargar / deposito / depositar /
        reca / depósito                              → notifica admin por Telegram
      • cualquier otro texto                         → menú de bienvenida
    """
    data = request.get_json()

    try:
        entry = data['entry'][0]['changes'][0]['value']

        if 'messages' not in entry:
            # Notificación de estado (leído, entregado) — ignorar
            return jsonify({"status": "ok"}), 200

        msg      = entry['messages'][0]
        telefono = msg['from']
        texto    = msg.get('text', {}).get('body', '').strip()
        nombre   = entry.get('contacts', [{}])[0].get('profile', {}).get('name', telefono)
        cmd      = texto.lower()

        # ── ESCENARIO 1: Apuesta directa ──────────────────────────────────────
        if cmd.startswith("apuesta"):
            respuesta = procesar_apuesta_whatsapp(texto, telefono)
            enviar_whatsapp(telefono, respuesta)

        # ── ESCENARIO 2: Consulta de saldo ────────────────────────────────────
        elif cmd.startswith("saldo"):
            partes = cmd.split()
            if len(partes) >= 2:
                usuario = partes[1]
                saldo   = consultar_saldo_db(usuario)
                enviar_whatsapp(telefono, f"💰 Saldo de *{usuario}*: R$ {saldo:.2f}")
            else:
                enviar_whatsapp(telefono, "Envía: saldo [usuario]")

        # ── ESCENARIO 3: Solicitud de registro ────────────────────────────────
        elif "registro" in cmd or "registrar" in cmd:
            notificar_admin_telegram(
                f"🆕 *NUEVO REGISTRO*\n\n"
                f"👤 Cliente: {nombre}\n"
                f"📱 Tel: {telefono}\n"
                f"📝 Datos: {texto}\n\n"
                f"Para dar de alta usa: `/alta {telefono} {nombre.replace(' ', '_')}`"
            )
            responder_cliente_whatsapp(
                telefono,
                f"Hola {nombre} 👋, tus datos fueron enviados al administrador. "
                f"Te avisamos en breve."
            )

        # ── ESCENARIO 4: Solicitud de recarga / depósito ──────────────────────
        elif any(x in cmd for x in ["recarga", "recargar", "reca", "deposito", "depositar", "depósito"]):
            monto = "".join(filter(str.isdigit, texto))
            if not monto:
                monto = "Monto no especificado"
            notificar_admin_telegram(
                f"💰 *SOLICITUD DE RECARGA*\n\n"
                f"👤 {nombre} ({telefono})\n"
                f"💵 Monto: R$ {monto}\n\n"
                f"Para validar usa: `/recarga {telefono} {monto}`"
            )
            responder_cliente_whatsapp(
                telefono,
                f"Recibido ✅. El admin está validando tu recarga de R$ {monto}. "
                f"Te confirmamos en breve."
            )

        # ── Sin comando reconocido: menú de bienvenida ────────────────────────
        else:
            responder_cliente_whatsapp(
                telefono,
                f"Hola {nombre} 👋, bienvenido a OkamiBet.\n\n"
                f"Comandos disponibles:\n"
                f"• *apuesta* [usuario] [pin] [monto] [pronostico]\n"
                f"• *saldo* [usuario]\n"
                f"• *registro* [tus datos]\n"
                f"• *recarga* [monto]"
            )

    except Exception as e:
        print(f"[ERROR Webhook] {e}")

    return jsonify({"status": "recibido"}), 200


# ─── Helper WhatsApp directo (fallback si bot_bridge no está disponible) ──────
def enviar_whatsapp(numero: str, texto: str):
    """Envía un mensaje de texto vía Cloud API directamente."""
    url     = f"https://graph.facebook.com/v18.0/{ID_TELEFONO}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN_WHATSAPP}",
        "Content-Type":  "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":   numero,
        "type": "text",
        "text": {"body": texto}
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR enviar_whatsapp] {e}")


# ─── Lógica de negocio ────────────────────────────────────────────────────────
def procesar_apuesta_whatsapp(comando: str, telefono: str) -> str:
    """
    Parsea y registra una apuesta.
    Formato esperado: apuesta [usuario] [pin] [monto] [pronostico]
    """
    from app.database import get_db, release_db

    partes = comando.split()
    if len(partes) < 5:
        return (
            "❌ Formato incorrecto.\n"
            "Usa: apuesta [usuario] [pin] [monto] [pronostico]\n"
            "Ejemplo: apuesta edward 1234 50 palmeiras"
        )

    _, usuario, pin, monto_str, pronostico = partes[0], partes[1], partes[2], partes[3], partes[4]

    try:
        monto = float(monto_str.replace(",", "."))
    except ValueError:
        return "❌ El monto debe ser un número. Ej: 50 o 50.50"

    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()

        # 1. Validar usuario y PIN (tabla corregida: usuarios)
        cur.execute(
            "SELECT id, saldo FROM usuarios WHERE usuario = %s AND pin = %s",
            (usuario, pin)
        )
        row = cur.fetchone()
        if not row:
            return "❌ Usuario o PIN incorrecto."

        usuario_id, saldo = row[0], float(row[1])

        # 2. Verificar saldo suficiente
        if saldo < monto:
            return f"❌ Saldo insuficiente. Tienes R$ {saldo:.2f}, apuesta es R$ {monto:.2f}."

        # 3. Registrar apuesta y descontar saldo
        cur.execute(
            "INSERT INTO apuestas (usuario_id, usuario, monto, pronostico, deporte) VALUES (%s, %s, %s, %s, 'whatsapp')",
            (usuario_id, usuario, monto, pronostico)
        )
        cur.execute(
            "UPDATE usuarios SET saldo = saldo - %s WHERE id = %s",
            (monto, usuario_id)
        )
        conn.commit()

        nuevo_saldo = saldo - monto
        return (
            f"✅ ¡Apuesta registrada, {usuario}!\n"
            f"🏆 Pronóstico: {pronostico}\n"
            f"💵 Monto: R$ {monto:.2f}\n"
            f"💰 Saldo restante: R$ {nuevo_saldo:.2f}"
        )

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[ERROR procesar_apuesta] {e}")
        return "⚠️ Error interno al registrar la apuesta. Intenta nuevamente."
    finally:
        if conn:
            release_db(conn)


def consultar_saldo_db(usuario: str) -> float:
    """Devuelve el saldo del usuario desde la DB."""
    from app.database import get_db, release_db

    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        # Tabla corregida: usuarios (antes era 'apostadores')
        cur.execute("SELECT saldo FROM usuarios WHERE usuario = %s", (usuario,))
        row = cur.fetchone()
        return float(row[0]) if row else 0.0
    except Exception as e:
        print(f"[ERROR consultar_saldo] {e}")
        return 0.0
    finally:
        if conn:
            release_db(conn)