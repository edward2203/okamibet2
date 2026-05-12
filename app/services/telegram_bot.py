import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from app.models.configuracion import get_config, set_config
from app.database import get_db, release_db
from app.models.log import LogModel
from app.models.usuario import UsuarioModel
from app.models.apuesta import ApuestaModel
from app.models.ganancia import GananciaModel
from app.services.calculos import procesar_limpiar_pozo_completo
from app.services.db import transaction
from app.services.bot_bridge import notificar_admin_telegram, responder_cliente_whatsapp
import psycopg2.extras
import datetime
import subprocess
import os
import signal
import time
import requests

logger = logging.getLogger(__name__)

# Variable global para el proceso ngrok
ngrok_process = None
ngrok_url = None


def is_admin(user_id):
    admin_id = get_config('telegram_admin_id')
    return str(user_id) == str(admin_id)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    
    # Mostrar teclado con botones
    keyboard = [
        [KeyboardButton("👤 Crear Usuario"), KeyboardButton("💰 Recargar Saldo")],
        [KeyboardButton("🎁 Bono Bienvenida"), KeyboardButton("⚙️ Configurar")],
        [KeyboardButton("✅ Cerrar Partido"), KeyboardButton("🗑️ Reset")],
        [KeyboardButton("🎟️ Ticket"), KeyboardButton("📋 Ver Usuarios")],
        [KeyboardButton("🚀 Ngrok"), KeyboardButton("📊 Estado")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_text(
        "🤖 Bot Okami Bet v4\n\nUsa los botones de abajo 👇",
        reply_markup=reply_markup
    )


async def crear_usuario_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Uso: /crear_usuario <usuario> <pin> <saldo> [email] [telefono]")
        return
    usuario = args[0]
    pin = args[1]
    try:
        saldo = float(args[2])
    except ValueError:
        await update.message.reply_text("Saldo debe ser numérico.")
        return
    email = args[3] if len(args) > 3 else None
    telefono = args[4] if len(args) > 4 else None
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Validar unicidad de usuario
        cursor.execute('SELECT COUNT(*) FROM usuarios WHERE usuario = %s', (usuario,))
        if cursor.fetchone()[0] > 0:
            conn.rollback()
            await update.message.reply_text("❌ Usuario ya existe.")
            return
        
        # Validar unicidad de email (si se proporcionó)
        if email:
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE email = %s', (email,))
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                await update.message.reply_text("❌ Email ya registrado.")
                return
        
        # Validar unicidad de telefono (si se proporcionó)
        if telefono:
            cursor.execute('SELECT COUNT(*) FROM usuarios WHERE telefono = %s', (telefono,))
            if cursor.fetchone()[0] > 0:
                conn.rollback()
                await update.message.reply_text("❌ Teléfono ya registrado.")
                return
        
        cursor.execute(
            "INSERT INTO usuarios (usuario, pin, saldo, email, telefono) VALUES (%s, %s, %s, %s, %s)",
            (usuario, pin, saldo, email, telefono)
        )
        
        # Insertar en tabla de bonificaciones
        cursor.execute(
            "INSERT INTO usuarios_bonificacion (usuario) VALUES (%s) ON CONFLICT DO NOTHING",
            (usuario,)
        )
        conn.commit()
        
        # Enviar notificación por email
        if email:
            from app.services.email_service import notificar_creacion_usuario
            try:
                notificar_creacion_usuario(usuario, email, telefono, saldo, False)
            except Exception as e:
                LogModel.registrar(
                    tipo='error',
                    titulo='❌ Error Email Creación Usuario',
                    descripcion=str(e),
                    usuario='ADMIN_TELEGRAM'
                )
        
        LogModel.registrar(
            tipo='usuario',
            titulo='👤 Usuario Creado via Telegram',
            descripcion=f'Usuario: {usuario}, Saldo: {saldo}',
            usuario='ADMIN_TELEGRAM',
            detalles={'usuario': usuario, 'saldo': saldo, 'email': email, 'telefono': telefono}
        )
        await update.message.reply_text(f"✅ Usuario {usuario} creado con saldo R$ {saldo:.2f}.")
    except Exception as e:
        conn.rollback()
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        release_db(conn)


async def recargar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Uso: /recargar <usuario> <monto>")
        return
    usuario = args[0]
    try:
        monto = float(args[1])
    except ValueError:
        await update.message.reply_text("Monto inválido.")
        return
    
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT saldo, email FROM usuarios WHERE usuario = %s", (usuario,))
        user_data = cursor.fetchone()
        if not user_data:
            await update.message.reply_text(f"❌ Usuario {usuario} no existe.")
            return
        saldo_anterior = float(user_data['saldo'])
        
        cursor.execute("UPDATE usuarios SET saldo = saldo + %s WHERE usuario = %s", (monto, usuario,))
        conn.commit()
        
        # Obtener saldo nuevo y email
        cursor.execute("SELECT saldo, email FROM usuarios WHERE usuario = %s", (usuario,))
        user_data_new = cursor.fetchone()
        saldo_nuevo = float(user_data_new['saldo'])
        email = user_data_new['email']
        
        # Enviar notificación por email
        if email:
            from app.services.email_service import notificar_recarga
            try:
                notificar_recarga(usuario, email, monto, saldo_anterior, saldo_nuevo)
            except Exception as e:
                LogModel.registrar(
                    tipo='error',
                    titulo='❌ Error Email Recarga',
                    descripcion=str(e),
                    usuario='ADMIN_TELEGRAM'
                )
        
        LogModel.registrar(
            tipo='recarga',
            titulo='💰 Saldo Recargado via Telegram',
            descripcion=f'Usuario: {usuario}, Monto: {monto}',
            usuario='ADMIN_TELEGRAM',
            detalles={'usuario': usuario, 'monto': monto}
        )
        await update.message.reply_text(f"✅ Recarga de R$ {monto:.2f} para {usuario} exitosa.")
    except Exception as e:
        conn.rollback()
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        release_db(conn)


async def bono_bienvenida_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Uso: /bono_bienvenida <usuario>")
        return
    usuario = args[0]
    ok = UsuarioModel.aplicar_bono_bienvenida(usuario)
    if ok:
        LogModel.registrar(tipo='bono', titulo='🎁 Bono Bienvenida via Telegram', descripcion=f'Usuario: {usuario}', usuario='ADMIN_TELEGRAM')
        await update.message.reply_text(f"✅ Bono de bienvenida aplicado a {usuario}.")
    else:
        await update.message.reply_text(f"❌ No se pudo aplicar bono a {usuario} (ya usado o usuario no existe).")


async def bono_referido_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Uso: /bono_referido <referidor> <referido>")
        return
    referidor = args[0]
    referido = args[1]
    conn = get_db()
    try:
        cursor = conn.cursor()
        bono = float(get_config('bono_registro') or 5.0)
        cursor.execute("UPDATE usuarios SET saldo = saldo + %s WHERE usuario = %s", (bono, referidor,))
        conn.commit()
        LogModel.registrar(
            tipo='bono',
            titulo='🤝 Bono Referido via Telegram',
            descripcion=f'Referidor: {referidor}, Referido: {referido}',
            usuario='ADMIN_TELEGRAM',
            detalles={'bono': bono}
        )
        await update.message.reply_text(f"✅ Bono de R$ {bono:.2f} otorgado a {referidor} por referir a {referido}.")
    except Exception as e:
        conn.rollback()
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        release_db(conn)


async def semilla_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Uso: /semilla <monto>")
        return
    try:
        monto = float(args[0])
    except ValueError:
        await update.message.reply_text("Monto inválido.")
        return
    set_config('saldo_semilla', str(monto))
    LogModel.registrar(
        tipo='config',
        titulo='🌱 Saldo Semilla Actualizado via Telegram',
        descripcion=f'Nuevo saldo semilla: {monto}',
        usuario='ADMIN_TELEGRAM',
        detalles={'monto': monto}
    )
    await update.message.reply_text(f"✅ Saldo semilla actualizado a R$ {monto:.2f}.")


async def reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM apuestas")
        default_configs = [
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
        for clave, valor in default_configs:
            cursor.execute("UPDATE configuraciones SET valor = %s WHERE clave = %s", (valor, clave,))
        conn.commit()
        LogModel.registrar(
            tipo='reset',
            titulo='🔄 Reset via Telegram',
            descripcion='Reset de reglas y apuestas',
            usuario='ADMIN_TELEGRAM'
        )
        await update.message.reply_text("✅ Reset completado: apuestas eliminadas, configuraciones restablecidas.")
    except Exception as e:
        conn.rollback()
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        release_db(conn)


async def cerrar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Uso: /cerrar <resultado_ganador>")
        return
    resultado_ganador = args[0]
    ok, mensaje = procesar_limpiar_pozo_completo(resultado_ganador)
    if ok:
        LogModel.registrar(
            tipo='cierre',
            titulo='🔒 Partido Cerrado via Telegram',
            descripcion=f'Resultado: {resultado_ganador}',
            usuario='ADMIN_TELEGRAM',
            detalles=mensaje
        )
        await update.message.reply_text(f"✅ Partido cerrado. {mensaje}")
    else:
        await update.message.reply_text(f"❌ Error: {mensaje}")


async def ticket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Uso: /ticket <usuario> [apuesta_id]")
        return
    usuario = args[0]
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if len(args) > 1:
            cursor.execute("SELECT * FROM apuestas WHERE id = %s AND usuario = %s", (args[1], usuario,))
        else:
            cursor.execute("SELECT * FROM apuestas WHERE usuario = %s ORDER BY fecha DESC LIMIT 1", (usuario,))
        apuesta = cursor.fetchone()
        if not apuesta:
            await update.message.reply_text("❌ Apuesta no encontrada.")
            return
        ticket_num = f"TICKET-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{apuesta['id']}"
        ticket = "🎟️ TICKET DE APUESTA\n"
        ticket += f"Número: {ticket_num}\n"
        ticket += f"Fecha: {apuesta['fecha']}\n"
        ticket += f"Usuario: {apuesta['usuario']}\n"
        ticket += f"Apostó a: {apuesta['pronostico']}\n"
        ticket += f"Monto apostado: R$ {apuesta['monto']:.2f}\n"
        cursor.execute("SELECT comision FROM configuraciones WHERE clave = 'comision'")
        comision = float(cursor.fetchone()[0] or 10)
        cuota_maxima = float(get_config('cuota_maxima') or 10.0)
        expected_profit = apuesta['monto'] * cuota_maxima * (1 - comision/100)
        ticket += f"Ganancia Prevista: R$ {expected_profit:.2f}\n"
        ticket += "--- Okami Bet v4 ---"
        await update.message.reply_text(ticket)
        
        cursor.execute("SELECT telefono, email FROM usuarios WHERE usuario = %s", (usuario,))
        user_info = cursor.fetchone()
        if user_info and user_info[0]:
            responder_cliente_whatsapp(user_info[0], ticket)
            await update.message.reply_text("✉️ Ticket enviado via WhatsApp.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        release_db(conn)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    
    text = update.message.text
    
    if text == "👤 Crear Usuario":
        await update.message.reply_text("Uso: /crear_usuario <usuario> <pin> <saldo> [email] [telefono]")
    elif text == "💰 Recargar Saldo":
        await update.message.reply_text("Uso: /recargar <usuario> <monto>")
    elif text == "🎁 Bono Bienvenida":
        await update.message.reply_text("Uso: /bono_bienvenida <usuario>")
    elif text == "⚙️ Configurar":
        await update.message.reply_text(
            "⚙️ Configuraciones:\n"
            "Usa los comandos normales para cambiar configuraciones.\n"
            "Ej: /semilla 1000"
        )
    elif text == "✅ Cerrar Partido":
        await update.message.reply_text("Uso: /cerrar <resultado_ganador>")
    elif text == "🗑️ Reset":
        await update.message.reply_text("Uso: /reset")
    elif text == "🎟️ Ticket":
        await update.message.reply_text("Uso: /ticket <usuario> [apuesta_id]")
    elif text == "📋 Ver Usuarios":
        conn = get_db()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute('SELECT usuario, email, saldo FROM usuarios ORDER BY usuario')
            usuarios = cursor.fetchall()
            if usuarios:
                msg = "📋 Usuarios Registrados:\n"
                for u in usuarios:
                    msg += f"- {u['usuario']} | {u['email'] or 'N/A'} | R$ {float(u['saldo']):.2f}\n"
                await update.message.reply_text(msg)
            else:
                await update.message.reply_text("No hay usuarios registrados.")
        finally:
            release_db(conn)
    elif text == "🚀 Ngrok":
        await update.message.reply_text("Uso: /ngrok_start o /ngrok_stop")
    elif text == "📊 Estado":
        await estado_handler(update, context)
    else:
        # Si no es un botón, mostrar el teclado nuevamente
        keyboard = [
            [KeyboardButton("👤 Crear Usuario"), KeyboardButton("💰 Recargar Saldo")],
            [KeyboardButton("🎁 Bono Bienvenida"), KeyboardButton("⚙️ Configurar")],
            [KeyboardButton("✅ Cerrar Partido"), KeyboardButton("🗑️ Reset")],
            [KeyboardButton("🎟️ Ticket"), KeyboardButton("📋 Ver Usuarios")],
            [KeyboardButton("🚀 Ngrok"), KeyboardButton("📊 Estado")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text(
            "Opción no reconocida. Usa los botones de abajo 👇",
            reply_markup=reply_markup
        )


async def ngrok_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el túnel ngrok."""
    global ngrok_process, ngrok_url
    
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    
    if ngrok_process and ngrok_process.poll() is None:
        await update.message.reply_text("⚠️ ngrok ya está en ejecución.")
        return
    
    try:
        cmd = ['ngrok', 'http', '5000', '--log', 'stdout']
        ngrok_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )
        time.sleep(3)
        
        # Obtener URL
        try:
            response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=5)
            if response.ok:
                data = response.json()
                if data.get('tunnels'):
                    ngrok_url = data['tunnels'][0]['public_url']
                    await update.message.reply_text(f"✅ ngrok iniciado.\nURL: {ngrok_url}")
                    return
        except:
            pass
        
        await update.message.reply_text("✅ ngrok iniciado (verificando URL...)")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def ngrok_stop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detiene el túnel ngrok."""
    global ngrok_process, ngrok_url
    
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    
    if not ngrok_process or ngrok_process.poll() is not None:
        ngrok_process = None
        ngrok_url = None
        await update.message.reply_text("⚠️ ngrok no está en ejecución.")
        return
    
    try:
        os.killpg(os.getpgid(ngrok_process.pid), signal.SIGTERM)
        ngrok_process.wait(timeout=5)
        ngrok_process = None
        ngrok_url = None
        await update.message.reply_text("✅ ngrok detenido.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def estado_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado del sistema."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return
    
    msg = "📊 Estado del Sistema:\n\n"
    
    # Estado de ngrok
    global ngrok_process, ngrok_url
    if ngrok_process and ngrok_process.poll() is None:
        msg += "🚀 ngrok: 🟢 En ejecución\n"
        if ngrok_url:
            msg += f"   URL: {ngrok_url}\n"
    else:
        msg += "🚀 ngrok: ⚫ Detenido\n"
    
    # Estado de la base de datos
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM usuarios')
        num_usuarios = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM apuestas')
        num_apuestas = cursor.fetchone()[0]
        release_db(conn)
        msg += f"\n👥 Usuarios: {num_usuarios}\n"
        msg += f"🎮 Apostas activas: {num_apuestas}\n"
    except:
        msg += "\n❌ Error consultando base de datos\n"
    
    await update.message.reply_text(msg)


async def main():
    token = get_config('telegram_token')
    if not token:
        logger.error("Telegram token not configured.")
        return
    
    app = ApplicationBuilder().token(token).build()
    
    # Manejadores de comandos (texto)
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("crear_usuario", crear_usuario_handler))
    app.add_handler(CommandHandler("recargar", recargar_handler))
    app.add_handler(CommandHandler("bono_bienvenida", bono_bienvenida_handler))
    app.add_handler(CommandHandler("bono_referido", bono_referido_handler))
    app.add_handler(CommandHandler("semilla", semilla_handler))
    app.add_handler(CommandHandler("reset", reset_handler))
    app.add_handler(CommandHandler("cerrar", cerrar_handler))
    app.add_handler(CommandHandler("ticket", ticket_handler))
    app.add_handler(CommandHandler("ngrok_start", ngrok_start_handler))
    app.add_handler(CommandHandler("ngrok_stop", ngrok_stop_handler))
    app.add_handler(CommandHandler("estado", estado_handler))
    
    # Manejador de botones del teclado
    admin_id = get_config('telegram_admin_id')
    app.add_handler(MessageHandler(filters.TEXT & filters.User(int(admin_id)), button_handler))
    
    logger.info("Bot de Telegram iniciado.")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    # Mantener el bot corriendo
    import asyncio
    await asyncio.Event().wait()


def start_bot():
    import asyncio
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Error iniciando bot de Telegram: {e}")
