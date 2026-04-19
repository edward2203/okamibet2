from app.services.db import obtener_conexion, transaction
from app.models.configuracion import get_config
from app.database import get_db, release_db
from datetime import datetime

class UsuarioModel:
    
    @staticmethod
    def aplicar_bono_bienvenida(usuario):
        """Aplica bono de bienvenida garantizando atomicidad mediante transacción."""
        try:
            bono_cantidad = float(get_config('bono_registro') or 5.0)

            with transaction() as cursor:
                cursor.execute(
                    'SELECT bono_bienvenida_usado FROM usuarios_bonificacion WHERE usuario = %s',
                    (usuario,)
                )
                bono_row = cursor.fetchone()

                if bono_row and bono_row[0] == 0:
                    cursor.execute(
                        'UPDATE usuarios SET saldo = saldo + %s WHERE usuario = %s',
                        (bono_cantidad, usuario)
                    )
                    cursor.execute(
                        'UPDATE usuarios_bonificacion SET bono_bienvenida_usado = 1 WHERE usuario = %s',
                        (usuario,)
                    )
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def registrar_acierto_consecutivo(usuario, premio_obtenido):
        """Registra aciertos y verifica la matriz de bonificación VIP."""
        try:
            multi_vip = float(get_config('multi_vip') or 1.2)

            with transaction() as cursor:
                cursor.execute(
                    'SELECT aciertos_consecutivos FROM usuarios_bonificacion WHERE usuario = %s',
                    (usuario,)
                )
                row = cursor.fetchone()
                aciertos_actuales = row[0] if row else 0

                nuevos_aciertos = aciertos_actuales + 1
                cursor.execute(
                    '''INSERT INTO usuarios_bonificacion
                       (usuario, aciertos_consecutivos, monto_total_ganado, ultima_apuesta_ganada)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (usuario) DO UPDATE SET
                           aciertos_consecutivos  = EXCLUDED.aciertos_consecutivos,
                           monto_total_ganado     = EXCLUDED.monto_total_ganado,
                           ultima_apuesta_ganada  = EXCLUDED.ultima_apuesta_ganada''',
                    (usuario, nuevos_aciertos, premio_obtenido, datetime.now())
                )

                bono_extra = 0.0
                if nuevos_aciertos % 3 == 0:
                    bono_extra = premio_obtenido * (multi_vip - 1.0)
                    cursor.execute(
                        'UPDATE usuarios SET saldo = saldo + %s WHERE usuario = %s',
                        (bono_extra, usuario)
                    )

                return nuevos_aciertos, bono_extra
        except Exception:
            return 0, 0.0