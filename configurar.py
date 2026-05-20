"""
Asistente de configuracion de JobAgent LATAM.
Pide credenciales de forma segura (sin mostrarlas en pantalla)
y las escribe al archivo .env.

Uso:
    python configurar.py
"""
import getpass
import os
import sys
from pathlib import Path

ENV_PATH = Path(".env")


def leer_env() -> dict:
    """Lee el .env actual y devuelve un dict clave=valor."""
    if not ENV_PATH.exists():
        return {}
    data = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    return data


def escribir_env(data: dict):
    """Escribe el .env manteniendo los comentarios del archivo original."""
    if not ENV_PATH.exists():
        # Crear desde cero
        lines = []
        for k, v in data.items():
            lines.append(f"{k}={v}")
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    # Actualizar conservando comentarios y orden original
    original = ENV_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    keys_written = set()

    for line in original:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in data:
                new_lines.append(f"{k}={data[k]}")
                keys_written.add(k)
                continue
        new_lines.append(line)

    # Agregar claves nuevas que no estaban en el archivo
    for k, v in data.items():
        if k not in keys_written:
            new_lines.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def pedir(prompt: str, actual: str = "", secreto: bool = False) -> str:
    """Pide un valor al usuario. Si es secreto, usa getpass."""
    if actual:
        display = "****" if secreto else actual
        hint = f" [actual: {display}]"
    else:
        hint = ""

    full_prompt = f"  {prompt}{hint}: "

    if secreto:
        valor = getpass.getpass(full_prompt)
    else:
        valor = input(full_prompt).strip()

    # Si el usuario no escribe nada, mantiene el valor actual
    return valor if valor else actual


def seccion(titulo: str):
    print(f"\n{'='*50}")
    print(f"  {titulo}")
    print(f"{'='*50}")


def main():
    print()
    print("  ============================================")
    print("    JobAgent LATAM - Configuracion")
    print("  ============================================")
    print()
    print("  Este asistente configura tus credenciales.")
    print("  Las contrasenas NO se muestran al escribirlas.")
    print("  Presiona Enter para mantener el valor actual.")
    print()

    env = leer_env()

    # ── Computrabajo ──────────────────────────────────────────────────────────
    seccion("COMPUTRABAJO (ar.computrabajo.com)")
    print("  Necesitas una cuenta en ar.computrabajo.com")
    print("  Si no tenes, creala en: https://ar.computrabajo.com/candidato/registro")
    print()
    ct_email = pedir("Email de Computrabajo", env.get("COMPUTRABAJO_EMAIL", ""))
    ct_pass  = pedir("Contrasena de Computrabajo", env.get("COMPUTRABAJO_PASSWORD", ""), secreto=True)

    # ── Bumeran (opcional) ────────────────────────────────────────────────────
    seccion("BUMERAN (bumeran.com.ar) - opcional")
    print("  Si no tenes cuenta, deja en blanco (el scraping igual funciona)")
    print()
    bm_email = pedir("Email de Bumeran", env.get("BUMERAN_EMAIL", ""))
    bm_pass  = pedir("Contrasena de Bumeran", env.get("BUMERAN_PASSWORD", ""), secreto=True)

    # ── Telegram ──────────────────────────────────────────────────────────────
    seccion("TELEGRAM (notificaciones)")
    print("  Para obtener tu token y chat_id:")
    print("  1. Abri Telegram y busca @BotFather")
    print("  2. Escribi /newbot y segui las instrucciones")
    print("  3. Copia el TOKEN que te da")
    print("  4. Mandaste un mensaje a tu nuevo bot")
    print("  5. Abre en el navegador:")
    print("     https://api.telegram.org/bot<TOKEN>/getUpdates")
    print("  6. Copia el numero en 'id' dentro de 'chat'")
    print()
    tg_token   = pedir("Token del bot de Telegram", env.get("TELEGRAM_BOT_TOKEN", ""), secreto=True)
    tg_chat_id = pedir("Chat ID de Telegram", env.get("TELEGRAM_CHAT_ID", ""))

    # ── Configuracion de busqueda ─────────────────────────────────────────────
    seccion("CONFIGURACION DEL AGENTE")
    headless_actual = env.get("HEADLESS", "true")
    print(f"  Modo headless (sin ventana del navegador):")
    print(f"  - 'true'  = el navegador corre en segundo plano (recomendado)")
    print(f"  - 'false' = podes ver el navegador mientras trabaja")
    headless = pedir("Headless (true/false)", headless_actual)
    if headless.lower() not in ("true", "false"):
        headless = "true"

    max_apps = pedir("Max aplicaciones por dia", env.get("MAX_APPLICATIONS_PER_DAY", "30"))

    # ── Guardar ───────────────────────────────────────────────────────────────
    print()
    print("  Guardando configuracion...")

    updates = {
        "COMPUTRABAJO_EMAIL":       ct_email,
        "COMPUTRABAJO_PASSWORD":    ct_pass,
        "BUMERAN_EMAIL":            bm_email,
        "BUMERAN_PASSWORD":         bm_pass,
        "TELEGRAM_BOT_TOKEN":       tg_token,
        "TELEGRAM_CHAT_ID":         tg_chat_id,
        "HEADLESS":                 headless,
        "MAX_APPLICATIONS_PER_DAY": max_apps,
    }
    escribir_env(updates)

    print()
    print("  ============================================")
    print("    Configuracion guardada en .env")
    print("  ============================================")
    print()

    # Verificar que la GROQ_API_KEY esta
    env_final = leer_env()
    if not env_final.get("GROQ_API_KEY"):
        print("  AVISO: No hay GROQ_API_KEY en el .env!")
        print("  Conseguila gratis en: https://console.groq.com")
        print("  Agregala al .env como: GROQ_API_KEY=gsk_...")
        print()
    else:
        print("  OK - GROQ_API_KEY detectada")

    if env_final.get("COMPUTRABAJO_EMAIL"):
        print("  OK - Computrabajo configurado")
    else:
        print("  AVISO: Computrabajo sin credenciales (solo scraping, sin aplicar)")

    if env_final.get("TELEGRAM_BOT_TOKEN"):
        print("  OK - Telegram configurado")
    else:
        print("  INFO: Telegram no configurado (no habra notificaciones)")

    print()
    print("  Listo! Podes ejecutar:")
    print("    python main.py search   -> buscar y aplicar")
    print("    python main.py stats    -> ver estadisticas")
    print("    python main.py dashboard -> abrir panel web")
    print()


if __name__ == "__main__":
    # Asegurarse de correr desde el directorio del proyecto
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    main()
