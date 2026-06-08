# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto sigue [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added
- Snapshot tests de scrapers con HTML fijado para Computrabajo y Bumeran
  (`tests/test_scrapers_snapshot.py`): detectan cambios de selectores/estructura
  que dejarían el parser devolviendo 0 resultados, e incluyen el caso
  "selectores rotos → lista vacía sin crashear".
- Tests de deduplicación ampliados (`tests/test_deduplication.py`): cobertura de
  normalización de acentos/ñ y de stopwords eliminadas solo como palabra completa.

### Fixed
- `_title_key` (`core/agent.py`): normaliza acentos (á→a, ñ→n) en vez de borrarlos
  y elimina stopwords como palabra completa (`\b`). Antes "Diseñador"/"Disenador"
  no se detectaban como duplicado y palabras como "Referente"/"Seminario" quedaban
  mutiladas por borrado de subcadena, pudiendo fusionar puestos distintos.
- `ApplicationTracker.get_stats` (`modules/tracker/database.py`): en modo personal
  (sin `user_id`) `total_jobs_scraped` y `avg_relevance_score` se calculan sobre la
  tabla `jobs` (no sobre `applications`), corrigiendo 5 tests que fallaban. El modo
  multi-tenant (con `user_id`) mantiene el cálculo por aplicaciones del usuario.

### Verificado
- Render de templates del SaaS: las 17 rutas públicas, de auth, de `/app/*` y de
  admin responden 200 y el flujo de registro (POST `/register` → `/app/onboarding`
  con cookie de sesión) funciona end-to-end (vía `TestClient`).

### Planeado
- Migración del front del SaaS a Next.js (hoy server-side con Jinja2)
- Verificación de Turso en producción (deploy en Render) — ver README/`render.yaml`

## [0.1.0] — 2026-05-20

Primer commit público del MVP personal.

### Added
- Scrapers asíncronos para Computrabajo, Bumeran, ZonaJobs e Indeed (este último solo lectura)
- Sistema de scoring con Groq (Llama 3.1 8B-instant) con manejo de rate limits
- Generación de cartas de presentación con Llama 3.3 70B en español rioplatense
- Login automatizado con persistencia de cookies por portal
- Bot de aplicación con Playwright y comportamiento anti-detección
- Tracker SQLite con migraciones automáticas
- Notificaciones por Telegram (búsqueda, vacantes, aplicaciones, errores, resumen)
- Dashboard Streamlit con 6 páginas:
  - Panel de control con métricas y aplicaciones recientes
  - Aplicaciones con botón "Aplicar ahora" individual
  - Vacantes filtrables por score y portal
  - Editor de perfil visual (vista, edición, importar PDF)
  - Nueva búsqueda con progreso en vivo
  - Estadísticas con gráficos Plotly (histograma, pie, bar, timeline, funnel)
- Modo CLI (`main.py`) y modo autónomo (`run_auto.py`)
- Asistente de configuración interactivo (`configurar.py`)
- Suite de smoke tests con pytest (12 tests, < 2s)
- Documentación de estrategia de QA ([tests/README.md](tests/README.md))

### Security
- Credenciales y tokens en `.env` (excluido del repo)
- Cookies de sesión en `data/sessions/` (excluido del repo)
- Datos personales y DB en `data/` (excluido del repo)
