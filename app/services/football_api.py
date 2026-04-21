import requests
from datetime import datetime, timedelta
from app.models.configuracion import get_config

def obtener_partidos_externos():
    """Adaptador que conecta con la API externa y normaliza el vector de respuesta."""
    api_key = get_config('api_key')

    if not api_key or api_key.strip() == '':
        return obtener_partidos_gratis()  # Usar API gratuita si no hay API key

    return obtener_partidos_football_data(api_key)

    url = "https://api.football-data.org/v4/competitions/BSA/matches"
    querystring = {"status": "SCHEDULED"}
    headers = {'X-Auth-Token': api_key}

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)

        if response.status_code == 401:
            return []  # API key inválida
        elif response.status_code == 403:
            return []  # Plan insuficiente o límite alcanzado
        elif response.status_code != 200:
            return []  # Otro error de API

        data = response.json()

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


def obtener_partidos_football_data(api_key):
    """Obtiene partidos usando football-data.org API."""
    url = "https://api.football-data.org/v4/competitions/BSA/matches"
    querystring = {"status": "SCHEDULED"}
    headers = {'X-Auth-Token': api_key}

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)

        if response.status_code == 401:
            return []  # API key inválida
        elif response.status_code == 403:
            return []  # Plan insuficiente o límite alcanzado
        elif response.status_code != 200:
            return []  # Otro error de API

        data = response.json()

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


def obtener_partidos_gratis():
    """Obtiene partidos brasileños y venezolanos de APIs gratuitas."""
    lista = []
    
    # Intentar obtener partidos del Brasileirão
    lista.extend(obtener_partidos_brasileirao())
    
    # Intentar obtener partidos de ligas venezolanas
    lista.extend(obtener_partidos_venezuela())
    
    return lista[:15]  # Limitar a 15 partidos


def obtener_partidos_brasileirao():
    """Partidos de demostración del Brasileirão."""
    from datetime import datetime, timedelta
    
    partidos_demo = [
        "Palmeiras vs São Paulo - 21/04 às 16:00",
        "Flamengo vs Botafogo - 21/04 às 18:30",
        "Corinthians vs Santos - 22/04 às 21:00",
        "Atlético Mineiro vs Cruzeiro - 22/04 às 19:00",
        "Vasco da Gama vs Vitória - 23/04 às 19:00",
        "Grêmio vs Inter - 23/04 às 20:30",
        "Fortaleza vs Cebolinha - 24/04 às 20:00",
        "Red Bull Bragantino vs Bahia - 24/04 às 21:30",
    ]
    return partidos_demo


def obtener_partidos_venezuela():
    """Partidos de demostración de la Liga Profesional Venezolana."""
    partidos_demo = [
        "Deportivo Táchira vs Caracas FC - 20/04 às 18:00",
        "Mineros de Guayana vs Estudiantes de Mérida - 21/04 às 19:00",
        "Real Sporting Club vs Atlético Venezuela - 22/04 às 20:00",
        "Carabobo FC vs Llaneros - 23/04 às 15:00",
        "Monagas SC vs Academia Puerto Cabello - 24/04 às 19:30",
    ]
    return partidos_demo