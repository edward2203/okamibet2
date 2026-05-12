from flask import Flask, request, jsonify
from app.services.db import init_db, aplicar_migraciones
from app.models.log import LogModel
import traceback
import threading

def create_app():
    """Fábrica de Aplicaciones: Construye la topología base de Flask."""
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.secret_key = 'okamibet_2026_key'
    
    # 1. Inicialización de la Infraestructura de Datos
    with app.app_context():
        init_db()
        aplicar_migraciones()
    
    # 2. Importación y Registro de los Vectores de Enrutamiento (Blueprints)
    from app.routes import public_bp, admin_bp, api_bp, ext_bp
    
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(ext_bp)
    
    # 3. Iniciar Bot de Telegram en hilo separado
    try:
        from app.services.telegram_bot import start_bot
        bot_thread = threading.Thread(target=start_bot, daemon=True)
        bot_thread.start()
        print("✅ Bot de Telegram iniciado en hilo separado.")
    except Exception as e:
        print(f"❌ Error iniciando bot de Telegram: {e}")
    
    # 4. Manejadores de Errores Centralizados
    @app.errorhandler(404)
    def not_found(error):
        try:
            LogModel.registrar(
                tipo='error',
                titulo='404 - Página no encontrada',
                descripcion=str(error),
                usuario=request.args.get('usuario', 'ANONIMO'),
                nivel='WARNING',
                detalles={
                    'url': request.url,
                    'method': request.method,
                    'referer': request.referrer
                }
            )
        except:
            pass
        return jsonify({'error': 'Not Found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        try:
            tb = traceback.format_exc()
            LogModel.registrar(
                tipo='error',
                titulo='500 - Error Interno del Servidor',
                descripcion=str(error),
                usuario=request.args.get('usuario', 'ANONIMO'),
                nivel='ERROR',
                detalles={
                    'stack_trace': tb,
                    'url': request.url,
                    'method': request.method,
                    'form': dict(request.form) if request.form else None,
                    'args': dict(request.args) if request.args else None
                }
            )
        except:
            pass
        return jsonify({'error': 'Internal Server Error'}), 500
    
    return app