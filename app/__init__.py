from flask import Flask
from app.services.db import init_db, aplicar_migraciones

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

    return app