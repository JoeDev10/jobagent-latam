"""
Punto de entrada del SaaS JobAgent LATAM.

Uso:
    python main_web.py                  # inicia en localhost:8000
    python main_web.py --tunnel         # abre tunel ngrok y muestra URL publica
    python main_web.py --port 9000
"""
import argparse
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def _start_tunnel(port: int):
    """Abre un tunel ngrok y muestra la URL publica."""
    try:
        from pyngrok import ngrok, conf
        # Si hay un auth token en .env, usarlo
        import os
        token = os.environ.get("NGROK_AUTHTOKEN", "")
        if token:
            conf.get_default().auth_token = token
        public_url = ngrok.connect(port, "http")
        url = str(public_url.public_url)
        print()
        print("  =========================================")
        print("   URL PUBLICA (compartila con quien quieras):")
        print(f"   {url}")
        print("  =========================================")
        print()
        return url
    except Exception as e:
        print(f"  [!] No se pudo abrir el tunel ngrok: {e}")
        print("  [!] Para usar --tunnel necesitas una cuenta gratuita en ngrok.com")
        print("  [!] y agregar NGROK_AUTHTOKEN=tu_token en el archivo .env")
        return None


def main():
    parser = argparse.ArgumentParser(description="JobAgent LATAM - Servidor Web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--tunnel", action="store_true", help="Abrir tunel ngrok para URL publica")
    args = parser.parse_args()

    import uvicorn

    local_url = f"http://{args.host}:{args.port}"
    print()
    print("  ==========================================")
    print("   JobAgent LATAM  -  Servidor Web")
    print("  ==========================================")
    print()
    print(f"  URL local: {local_url}")
    print("  Presiona Ctrl+C para detener.")
    print()

    public_url = None
    if args.tunnel:
        # host debe ser 0.0.0.0 para que ngrok pueda llegar al puerto
        args.host = "0.0.0.0"
        local_url = f"http://127.0.0.1:{args.port}"
        public_url = _start_tunnel(args.port)

    open_url = public_url or local_url
    if not args.no_browser:
        threading.Timer(1.8, lambda: webbrowser.open(open_url)).start()

    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
