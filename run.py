#!/usr/bin/env python3
"""
Punto de entrada de la aplicación Okami Bet v4
"""
from app import create_app

if __name__ == '__main__':
    app = create_app()
    
    print("\n" + "=" * 60)
    print("🚀 Iniciando Okami Bet v4")
    print("=" * 60)
    print("📍 http://localhost:5000")
    print("=" * 60 + "\n")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=True
    )
