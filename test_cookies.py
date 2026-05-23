"""Test rápido: leer cookies de Computrabajo desde Chrome del usuario."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from modules.auth.cookie_loader import load_cookies_for_portal, has_auth_cookies

for portal in ["computrabajo", "bumeran"]:
    print(f"\n=== {portal.upper()} ===")
    cookies = load_cookies_for_portal(portal)
    if not cookies:
        print(f"  (sin cookies) — andá a {portal} en Chrome y logueate")
        continue

    print(f"  Total: {len(cookies)} cookies")
    auth = has_auth_cookies(cookies, portal)
    print(f"  ¿Tiene cookies de auth? {'SÍ ✓' if auth else 'NO'}")

    # Listar los nombres más relevantes
    print("  Cookies destacadas:")
    for c in cookies[:15]:
        name = c['name']
        marker = ""
        n_lower = name.lower()
        if any(k in n_lower for k in ["auth", "identity", "idsrv", "aspxauth", "token"]):
            marker = "  🔑"
        print(f"    {name:50s} @ {c['domain'][:40]}{marker}")
