"""
API REST + SSE para el SaaS.
Endpoints:
  POST /api/profile        — guardar perfil
  POST /api/settings       — guardar credenciales/config
  POST /api/run            — lanzar búsqueda + aplicación
  GET  /api/progress/{rid} — SSE stream de progreso en tiempo real
  GET  /api/stats          — estadísticas JSON
  GET  /api/applications   — lista de aplicaciones JSON
  PUT  /api/applications/{id}/status — actualizar estado
"""
import asyncio
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from web.auth import get_current_user
from web import db
from modules.tracker.database import ApplicationTracker

router = APIRouter(prefix="/api")
tracker = ApplicationTracker()

FREE_RUNS_LIMIT = int(os.environ.get("FREE_RUNS_LIMIT", "3"))
RUN_COOLDOWN = 30  # segundos mínimos entre búsquedas

# Cola de eventos por run_id → asyncio.Queue
_queues: dict[str, asyncio.Queue] = {}
# Rate limiting: user_id → timestamp del último run
_run_timestamps: dict[int, float] = {}


# ─── Perfil ───────────────────────────────────────────────────────────────────

@router.post("/profile")
async def save_profile(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    data = await request.json()
    db.save_profile(user["sub"], data)
    return JSONResponse({"ok": True})


# ─── Settings ─────────────────────────────────────────────────────────────────

@router.post("/settings")
async def save_settings(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    data = await request.json()

    allowed = {
        "computrabajo_email", "computrabajo_password",
        "bumeran_email", "bumeran_password",
        "zonajobs_email", "zonajobs_password",
        "groq_api_key", "telegram_bot_token", "telegram_chat_id",
        "max_apps_per_day", "auto_apply_threshold", "min_score",
        "headless", "preferred_portals",
    }
    filtered = {k: v for k, v in data.items() if k in allowed}
    db.update_settings(user["sub"], **filtered)
    return JSONResponse({"ok": True})


# ─── Stats ────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    return JSONResponse(tracker.get_stats(user_id=user["sub"]))


# ─── Applications ─────────────────────────────────────────────────────────────

@router.get("/applications")
async def get_applications(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    apps = tracker.get_applications(user_id=user["sub"])
    for a in apps:
        for k, v in a.items():
            if isinstance(v, datetime):
                a[k] = v.isoformat()
    return JSONResponse(apps)


@router.get("/applications/export")
async def export_applications_csv(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    import csv
    import io
    apps = tracker.get_applications(user_id=user["sub"])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Empresa", "Puesto", "Portal", "Estado", "Score", "URL", "Fecha"])
    for a in apps:
        writer.writerow([
            a.get("id", ""),
            a.get("company", ""),
            a.get("title", ""),
            a.get("portal", ""),
            a.get("status", ""),
            a.get("relevance_score", ""),
            a.get("url", ""),
            a.get("applied_at") or a.get("created_at", ""),
        ])
    csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel
    from fastapi.responses import Response
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=aplicaciones.csv"},
    )


@router.put("/applications/{app_id}/status")
async def update_app_status(app_id: str, request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    data = await request.json()
    status = data.get("status")
    if not status:
        return JSONResponse({"error": "Falta status"}, status_code=400)
    from core import ApplicationStatus
    try:
        st = ApplicationStatus(status)
    except ValueError:
        return JSONResponse({"error": "Status inválido"}, status_code=400)
    tracker.update_status(app_id, st, data.get("notes"))
    return JSONResponse({"ok": True})


# ─── Run (bot) ────────────────────────────────────────────────────────────────

@router.post("/run")
async def start_run(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    user_id: int = user["sub"]

    # Rate limiting
    now = time.time()
    last = _run_timestamps.get(user_id, 0)
    if now - last < RUN_COOLDOWN:
        remaining = int(RUN_COOLDOWN - (now - last))
        return JSONResponse({
            "error": "cooldown",
            "msg": f"Esperá {remaining} segundos antes de iniciar otra búsqueda.",
        }, status_code=429)

    user_data = db.get_user_by_id(user_id)
    if user_data and user_data.get("plan", "free") == "free":
        runs_used = user_data.get("runs_used") or 0
        if runs_used >= FREE_RUNS_LIMIT:
            return JSONResponse({
                "error": "limite_alcanzado",
                "msg": f"Agotaste tus {FREE_RUNS_LIMIT} búsquedas gratuitas. Actualizá a Pro para búsquedas ilimitadas.",
                "upgrade_url": "/app/upgrade",
            }, status_code=402)

    data = await request.json()
    run_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _queues[run_id] = queue
    _run_timestamps[user_id] = now

    asyncio.create_task(_run_bot(user_id, data, queue))
    return JSONResponse({"run_id": run_id})


async def _emit(queue: asyncio.Queue, type_: str, msg: str, **extra):
    await queue.put({"type": type_, "msg": msg, "ts": datetime.now().strftime("%H:%M:%S"), **extra})


async def _run_bot(user_id: int, config: dict, queue: asyncio.Queue):
    """Ejecuta scraping + aplicación y emite eventos al queue."""
    base = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(base))

    _started = False  # True cuando el agente realmente arranca (para contabilizar el run)
    try:
        await _emit(queue, "info", "Cargando configuración...")

        settings_row = db.get_settings(user_id)
        profile_data = db.get_profile(user_id)

        # Escribir credenciales al .env temporalmente para que los módulos las lean
        _patch_env(settings_row)

        from dotenv import load_dotenv
        load_dotenv(override=True)

        # Recargar settings del módulo core
        import importlib
        import core
        importlib.reload(core)
        from core import SearchConfig, Portal, JobModality, get_logger

        # Construir perfil
        if not profile_data:
            await _emit(queue, "error", "No tenés un perfil configurado. Completá tu perfil primero.")
            await queue.put(None)
            return

        from core.models import (
            UserProfile, WorkExperience, Education,
            ExperienceLevel, JobModality as JM,
        )

        try:
            profile = UserProfile(**profile_data)
        except Exception as e:
            await _emit(queue, "error", f"Error en perfil: {e}")
            await queue.put(None)
            return

        # Construir config de búsqueda
        keywords = config.get("keywords", ["QA Analyst", "Tester"])
        portals_str = config.get("portals", settings_row.get("preferred_portals", ["computrabajo"]))
        if isinstance(portals_str, str):
            portals_str = json.loads(portals_str)

        portals = []
        portal_map = {
            "computrabajo": Portal.COMPUTRABAJO,
            "bumeran": Portal.BUMERAN,
            "zonajobs": Portal.ZONAJOBS,
            "indeed": Portal.INDEED,
        }
        for p in portals_str:
            if p in portal_map:
                portals.append(portal_map[p])
        if not portals:
            portals = [Portal.COMPUTRABAJO]

        min_score = float(config.get("min_score", settings_row.get("min_score", 0.60)))
        max_results = int(config.get("max_results", 15))

        search_config = SearchConfig(
            keywords=keywords,
            location=config.get("location", "Argentina"),
            portals=portals,
            modality=JM.ANY,
            max_results_per_portal=max_results,
            min_relevance_score=min_score,
            auto_apply=True,
        )

        await _emit(queue, "info", f"Buscando: {', '.join(keywords)} en {', '.join(p.value for p in portals)}")

        from core.agent import JobAgent
        from core import ApplicationStatus

        # Bridge: _emit is sync (calls self._progress(msg: str)), but we need async queue puts.
        # Since _run_bot is an asyncio task, ensure_future schedules on the same loop.
        def sync_callback(msg: str):
            asyncio.ensure_future(_emit(queue, "info", msg))

        _started = True
        agent = JobAgent()
        results = await agent.run(profile, search_config, interactive=False, progress_callback=sync_callback)

        applied_count = sum(1 for a in results if a.status == ApplicationStatus.APPLIED)
        pending_count = sum(1 for a in results if a.status == ApplicationStatus.PENDING)
        # Stamp all result applications with this user_id so they appear in their dashboard
        tracker.stamp_user_id(user_id, [a.id for a in results])
        await _emit(queue, "success", f"¡Listo! {applied_count} aplicaciones enviadas, {pending_count} pendientes de revisión.")

    except Exception as e:
        await _emit(queue, "error", f"Error inesperado: {str(e)[:300]}")
    finally:
        if _started:
            db.increment_run_count(user_id)
        await queue.put(None)  # señal de fin


def _patch_env(settings_row: dict):
    """Inyecta las credenciales del usuario en os.environ para que los módulos las lean."""
    mapping = {
        "computrabajo_email":    "COMPUTRABAJO_EMAIL",
        "computrabajo_password": "COMPUTRABAJO_PASSWORD",
        "bumeran_email":         "BUMERAN_EMAIL",
        "bumeran_password":      "BUMERAN_PASSWORD",
        "zonajobs_email":        "ZONAJOBS_EMAIL",
        "zonajobs_password":     "ZONAJOBS_PASSWORD",
        "groq_api_key":          "GROQ_API_KEY",
        "telegram_bot_token":    "TELEGRAM_BOT_TOKEN",
        "telegram_chat_id":      "TELEGRAM_CHAT_ID",
    }
    for k, env_k in mapping.items():
        v = settings_row.get(k, "")
        if v:
            os.environ[env_k] = v


# ─── SSE stream de progreso ───────────────────────────────────────────────────

@router.get("/progress/{run_id}")
async def progress_stream(run_id: str, request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    queue = _queues.get(run_id)
    if not queue:
        return JSONResponse({"error": "Run no encontrado"}, status_code=404)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue

                if event is None:
                    yield "event: done\ndata: {}\n\n"
                    break
                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            _queues.pop(run_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Admin ───────────────────────────────────────────────────────────────────

@router.post("/admin/upgrade")
async def admin_upgrade(request: Request):
    """Actualiza el plan de un usuario. Requiere X-Admin-Secret header."""
    admin_secret = os.environ.get("ADMIN_SECRET", "")
    if not admin_secret:
        return JSONResponse({"error": "Admin no configurado en el servidor"}, status_code=503)
    provided = request.headers.get("X-Admin-Secret", "")
    if not hmac.compare_digest(provided.encode(), admin_secret.encode()):
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    data = await request.json()
    email = data.get("email", "").lower().strip()
    plan = data.get("plan", "pro")

    if plan not in ("free", "pro"):
        return JSONResponse({"error": "Plan invalido. Usar 'free' o 'pro'"}, status_code=400)
    if not email:
        return JSONResponse({"error": "Falta email"}, status_code=400)

    user = db.get_user_by_email(email)
    if not user:
        return JSONResponse({"error": f"Usuario '{email}' no encontrado"}, status_code=404)

    db.set_user_plan(user["id"], plan)
    return JSONResponse({"ok": True, "email": email, "plan": plan, "user_id": user["id"]})
