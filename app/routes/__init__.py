from flask import Blueprint

# Importación de las rutas para registrar los endpoints en los Blueprints
# Se importan los módulos para que se ejecute el código de definición de blueprints
from . import public, admin, api, ext

# Extracción de los blueprints después de que se hayan definido
public_bp = public.public_bp
admin_bp = admin.admin_bp
api_bp = api.api_bp
ext_bp = ext.ext_bp