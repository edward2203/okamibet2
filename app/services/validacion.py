from datetime import datetime, timedelta
from app.models.configuracion import get_config

def validar_acceso_admin(admin_pass):
    """Valida si la contraseña admin es correcta geométricamente."""
    clave_maestra = get_config('admin_pass')
    return admin_pass == clave_maestra

def validar_monto_apuesta(monto):
    """Valida que el monto escalar esté dentro de los límites permitidos."""
    try:
        min_apuesta = float(get_config('min_apuesta') or 20.0)
        max_apuesta = float(get_config('max_apuesta') or 200.0)
        
        if monto < min_apuesta:
            return False, f"Apuesta mínima: R${min_apuesta:.2f}"
        if monto > max_apuesta:
            return False, f"Apuesta máxima: R${max_apuesta:.2f}"
        
        return True, "OK"
    except Exception:
        return False, "Error en validación matricial del monto"

def verificar_cierre_apuestas(partido_actual):
    """Verifica el vector de tiempo si las apuestas están cerradas (N min antes del inicio)."""
    try:
        partes = partido_actual.split(' - ')
        if len(partes) >= 2:
            hora_str = partes[-1].strip().split()[-1]  # Extrae la coordenada temporal ej. "16:00"
            if ':' in hora_str:
                horas, minutos = map(int, hora_str.split(':'))
                ahora = datetime.now()
                hora_partido = ahora.replace(hour=horas, minute=minutos, second=0, microsecond=0)
                
                minutos_cierre = int(get_config('cierre_minutos_antes') or 10)
                hora_cierre = hora_partido - timedelta(minutes=minutos_cierre)
                
                return ahora >= hora_cierre
    except Exception:
        pass
    return False