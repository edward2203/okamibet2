import requests
from app.models.configuracion import get_config

def notificar_admin_telegram(mensaje):
    """Envía una alerta a tu Telegram para que decidas qué hacer."""
    token = get_config('telegram_token')
    admin_id = get_config('telegram_admin_id')
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": admin_id, "text": mensaje, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def responder_cliente_whatsapp(telefono, texto):
    """Envía la respuesta final al cliente en WhatsApp."""
    token = get_config('whatsapp_token')
    phone_id = get_config('whatsapp_phone_id')
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": texto}
    }
    requests.post(url, json=payload, headers=headers)