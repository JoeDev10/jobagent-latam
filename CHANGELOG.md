# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto sigue [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Planeado
- Snapshot tests de scrapers con HTML fijado
- Tests unitarios de deduplicación (`_title_key`)
- CI con GitHub Actions
- Migración a SaaS multi-tenant (FastAPI + Next.js)

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
