from flask import Blueprint

# Declaración de los espacios matriciales (Blueprints)
public_bp = Blueprint('public', __name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
api_bp = Blueprint('api', __name__, url_prefix='/api')
ext_bp = Blueprint('ext', __name__, url_prefix='/ext')

# Importación de las rutas para registrar los endpoints en los Blueprints
from . import public, admin, api, ext