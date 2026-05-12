import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
from app.models.configuracion import get_config
from app.models.log import LogModel
from datetime import datetime

def send_email(to_email, subject, body, cc_email=None):
    """
    Envía un email usando SMTP configurado.
    Requiere configuraciones: smtp_server, smtp_port, smtp_user, smtp_password, platform_email
    """
    try:
        smtp_server = get_config('smtp_server')
        smtp_port = int(get_config('smtp_port') or 587)
        smtp_user = get_config('smtp_user')
        smtp_password = get_config('smtp_password')
        platform_email = get_config('platform_email')
        
        if not all([smtp_server, smtp_user, smtp_password]):
            LogModel.registrar(
                tipo='error',
                titulo='❌ Configuración SMTP Incompleta',
                descripcion='Faltan configuraciones SMTP para envío de emails',
                usuario='SISTEMA'
            )
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = to_email
        msg['Date'] = formatdate(localtime=True)
        if cc_email:
            msg['Cc'] = cc_email
        
        text_part = MIMEText(body, 'plain', 'utf-8')
        msg.attach(text_part)
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        LogModel.registrar(
            tipo='email',
            titulo='✉️ Email Enviado',
            descripcion=f'Email enviado a {to_email}',
            usuario='SISTEMA',
            detalles={'to': to_email, 'cc': cc_email, 'subject': subject}
        )
        return True
    except Exception as e:
        LogModel.registrar(
            tipo='error',
            titulo='❌ Error Envío Email',
            descripcion=str(e),
            usuario='SISTEMA'
        )
        return False

def notificar_creacion_usuario(usuario, email, telefono=None, saldo_inicial=0, bono_aplicado=False):
    """Envía notificación de creación de usuario."""
    if not email:
        return False
    
    platform_email = get_config('platform_email') or 'okamibet@gmail.com'
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    
    subject = "✅ Cuenta Creada - Okami Bet"
    body = f"""
{'='*60}
OKAMI BET - NOTIFICACIÓN DE CUENTA
{'='*60}

Tipo de Operación: CREACIÓN DE USUARIO
Fecha y Hora: {timestamp}

DETALLES DE LA CUENTA:
- Usuario: {usuario}
- Email: {email}
- Teléfono: {telefono or 'No proporcionado'}
- Saldo Inicial: R$ {saldo_inicial:.2f}
- Bono de Bienvenida: {'Aplicado (+R$ ' + str(get_config('bono_registro') or '5.0') + ')' if bono_aplicado else 'No aplicado'}

{'='*60}
Este es un correo automático de confirmación.
Si no solicitaste esta cuenta, por favor contacta a soporte.

Okami Bet v4 - Todos los derechos reservados.
{'='*60}
"""
    
    return send_email(email, subject, body, cc_email=platform_email)

def notificar_recarga(usuario, email, monto, saldo_anterior, saldo_nuevo):
    """Envía notificación de recarga de saldo."""
    if not email:
        return False
    
    platform_email = get_config('platform_email') or 'okamibet@gmail.com'
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    
    subject = "💰 Saldo Recargado - Okami Bet"
    body = f"""
{'='*60}
OKAMI BET - NOTIFICACIÓN DE RECARGA
{'='*60}

Tipo de Operación: RECARGA DE SALDO
Fecha y Hora: {timestamp}

DETALLES DE LA OPERACIÓN:
- Usuario: {usuario}
- Monto Recargado: R$ {monto:.2f}
- Saldo Anterior: R$ {saldo_anterior:.2f}
- Saldo Nuevo: R$ {saldo_nuevo:.2f}

{'='*60}
Este es un correo automático de confirmación de transacción.

Okami Bet v4 - Todos los derechos reservados.
{'='*60}
"""
    
    return send_email(email, subject, body, cc_email=platform_email)

def notificar_cierre_partido(usuario, email, pronostico, resultado, premio=0, saldo_anterior=0, saldo_nuevo=0):
    """Envía notificación de cierre de partido (apuesta ganada o perdida)."""
    if not email:
        return False
    
    platform_email = get_config('platform_email') or 'okamibet@gmail.com'
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    estado = "GANADA ✅" if premio > 0 else "PERDIDA ❌"
    
    subject = f"{estado} - Resultado de Apuesta - Okami Bet"
    body = f"""
{'='*60}
OKAMI BET - NOTIFICACIÓN DE RESULTADO
{'='*60}

Tipo de Operación: CIERRE DE PARTIDO
Fecha y Hora: {timestamp}

DETALLES DE LA APUESTA:
- Usuario: {usuario}
- Pronóstico: {pronostico}
- Resultado del Partido: {resultado}
- Estado: {estado}

DETALLES ECONÓMICOS:
- Premio Obtenido: R$ {premio:.2f}
- Saldo Anterior: R$ {saldo_anterior:.2f}
- Saldo Nuevo: R$ {saldo_nuevo:.2f}

{'='*60}
Este es un correo automático informando el resultado de tu apuesta.

Okami Bet v4 - Todos los derechos reservados.
{'='*60}
"""
    
    return send_email(email, subject, body, cc_email=platform_email)

def notificar_cambio_parametros(usuario, email, cambios):
    """Envía notificación de cambios en parámetros de usuario."""
    if not email:
        return False
    
    platform_email = get_config('platform_email') or 'okamibet@gmail.com'
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    
    cambios_texto = "\n".join([f"- {k}: {v}" for k, v in cambios.items()])
    
    subject = "⚙️ Parámetros Actualizados - Okami Bet"
    body = f"""
{'='*60}
OKAMI BET - NOTIFICACIÓN DE CAMBIOS
{'='*60}

Tipo de Operación: MODIFICACIÓN DE PARÁMETROS
Fecha y Hora: {timestamp}

DETALLES DE LA MODIFICACIÓN:
- Usuario Afectado: {usuario}
{cambios_texto}

{'='*60}
Este es un correo automático informando cambios en tu cuenta.

Okami Bet v4 - Todos los derechos reservados.
{'='*60}
"""
    
    return send_email(email, subject, body, cc_email=platform_email)
