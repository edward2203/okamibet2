# app/services/apuestas_service.py
from app.services.db import transaction


class ApuestasService:
    """
    Servicio para gestionar apuestas en PostgreSQL.
    Funciones obtener_total_por_deporte, obtener_historial_usuario y
    obtener_estadisticas_generales eliminadas: 0 referencias en el código.
    """

    @staticmethod
    def registrar_apuesta(usuario_id, evento_id, monto, deporte, pronostico, usuario=''):
        """Registra una nueva apuesta en la tabla activa."""
        with transaction() as cursor:
            cursor.execute(
                """INSERT INTO apuestas (usuario_id, usuario, evento_id, monto, deporte, pronostico)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (usuario_id, usuario, evento_id, monto, deporte, pronostico)
            )
            return True
