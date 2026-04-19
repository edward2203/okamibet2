import requests
from datetime import datetime, timedelta
from app.models.configuracion import get_config

def obtener_partidos_externos():
    """Adaptador que conecta con la API externa y normaliza el vector de respuesta."""
    api_key = get_config('api_key')
    url = "https://api.football-data.org/v4/competitions/BSA/matches"
    querystring = {"status": "SCHEDULED"}
    headers = {'X-Auth-Token': api_key}
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        data = response.json()
        
        if response.status_code != 200:
            return []
        
        lista = []
        for partido in data.get('matches', []):
            fecha_raw = partido.get('utcDate', '')
            
            if fecha_raw:
                dt_utc = datetime.strptime(fecha_raw, "%Y-%m-%dT%H:%M:%SZ")
                dt_local = dt_utc - timedelta(hours=4)
                formato = dt_local.strftime("%d/%m às %H:%M")
            else:
                formato = "Data a definir"
            
            local = partido['homeTeam']['shortName'] or partido['homeTeam']['name']
            visitante = partido['awayTeam']['shortName'] or partido['awayTeam']['name']
            
            lista.append(f"{local} vs {visitante} - {formato}")
            
            if len(lista) >= 15:
                break
        
        return lista
    except Exception:
        return []