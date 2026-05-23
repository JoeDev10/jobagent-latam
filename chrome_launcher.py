"""
Abre tu Chrome real con remote-debugging-port para que el bot pueda
conectarse vía CDP (Chrome DevTools Protocol).

- Usa tu Chrome instalado y tu perfil real (con todas tus sesiones)
- Mantiene tu sesión de Computrabajo / Bumeran / Google / etc.
- El bot se conecta sin abrir un browser nuevo

Uso:
  python chrome_launcher.py        # arranca Chrome en modo debug
  python chrome_launcher.py --stop # detiene el Chrome de debug
"""
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

DEBUG_PORT = 9223
PROFILE_DIR = Path(__file__).parent / "data" / "chrome_debug_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def find_chrome_exe() -> str | None:
    """Busca chrome.exe en las ubicaciones típicas de Windows."""
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidates:
        if Path(p).is_file():
            return p
    return None


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start():
    if port_in_use(DEBUG_PORT):
        print(f"Ya hay un Chrome escuchando en el puerto {DEBUG_PORT}.")
        print(f"  CDP URL: http://localhost:{DEBUG_PORT}")
        return

    chrome = find_chrome_exe()
    if not chrome:
        print("ERROR: no encontré chrome.exe.")
        print("Instalá Chrome o ajustá find_chrome_exe() con la ruta correcta.")
        sys.exit(1)

    args = [
        chrome,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://ar.computrabajo.com/",
    ]
    print(f"Arrancando Chrome en modo debug (puerto {DEBUG_PORT})...")
    print(f"Perfil: {PROFILE_DIR}")
    print()
    print("Pasos:")
    print("  1. Va a abrirse una ventana de Chrome con Computrabajo.")
    print("  2. Logueate normalmente (la primera vez te toca hacerlo a mano).")
    print("  3. Tu sesión queda guardada en este perfil para siempre.")
    print("  4. Cuando estés logueado, DEJÁ Chrome abierto y corré:")
    print("     python aplicar_pendientes.py")
    print()
    print("  Para detener: python chrome_launcher.py --stop  (o cerrá Chrome)")
    print()

    # Lanzar en background
    subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)

    # Esperar a que arranque
    for _ in range(20):
        if port_in_use(DEBUG_PORT):
            print(f"✓ Chrome arrancó. CDP en http://localhost:{DEBUG_PORT}")
            return
        time.sleep(0.5)
    print("⚠ Chrome tardó en arrancar, verificá manualmente.")


def stop():
    if not port_in_use(DEBUG_PORT):
        print(f"No hay Chrome de debug corriendo (puerto {DEBUG_PORT} libre).")
        return
    # Buscar y matar el proceso de Chrome con la flag de debug
    import psutil
    killed = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] and "chrome" in proc.info["name"].lower():
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if f"--remote-debugging-port={DEBUG_PORT}" in cmdline:
                    proc.kill()
                    killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    print(f"Maté {killed} procesos de Chrome de debug.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true", help="Detener Chrome de debug")
    args = parser.parse_args()
    if args.stop:
        stop()
    else:
        start()
