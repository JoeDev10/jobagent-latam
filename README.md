# 🎯 JobAgent LATAM

> Agente de IA que busca, evalúa y aplica automáticamente a vacantes laborales en portales de empleo de Latinoamérica (Computrabajo, Bumeran, ZonaJobs).

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
[![Tests](https://github.com/JoeDev10/jobagent-latam/actions/workflows/tests.yml/badge.svg)](https://github.com/JoeDev10/jobagent-latam/actions/workflows/tests.yml)
![Status](https://img.shields.io/badge/status-MVP-orange.svg)

## 📋 Qué hace

JobAgent LATAM automatiza el proceso completo de búsqueda y aplicación a empleos:

1. **Scrapea** vacantes de Computrabajo, Bumeran y ZonaJobs según tus keywords
2. **Evalúa** la relevancia de cada vacante con IA (Groq + Llama 3.1) contra tu CV
3. **Genera** cartas de presentación personalizadas en español rioplatense
4. **Aplica** automáticamente a las vacantes que superen un score mínimo
5. **Notifica** por Telegram cada paso y resumen diario
6. **Trackea** todo en una DB local + dashboard web (Streamlit)

Pensado para el mercado **LATAM** (especialmente Argentina), donde no existen herramientas como esta a diferencia del mercado anglosajón saturado de soluciones tipo LazyApply.

## 🏗️ Arquitectura

```
jobagent/
├── core/                    # Agente central, modelos Pydantic, config
│   ├── agent.py            # Orquestador (scraping → scoring → cartas → apply)
│   ├── models.py           # JobListing, Application, UserProfile, etc.
│   └── config.py           # Settings desde .env
├── modules/
│   ├── scrapers/           # Computrabajo, Bumeran, ZonaJobs, Indeed
│   ├── ai/                 # Scoring + generación de cartas con Groq
│   ├── auth/               # Login y persistencia de cookies
│   ├── applicator/         # Bot de aplicación con Playwright
│   ├── tracker/            # SQLite + queries
│   ├── notifier/           # Telegram bot
│   └── profile/            # Extracción de perfil desde PDF
├── dashboard/              # Streamlit (run/apply/perfil/stats)
├── tests/                  # Pytest (smoke tests)
├── main.py                 # CLI principal
├── run_auto.py             # Modo autónomo (Task Scheduler / cron)
└── configurar.py           # Asistente de configuración
```

### Stack

| Capa | Tecnología |
|---|---|
| **Lenguaje** | Python 3.12 |
| **Web automation** | Playwright (Chromium async) |
| **LLM** | Groq (Llama 3.3 70B + Llama 3.1 8B-instant) |
| **Validación de datos** | Pydantic v2 |
| **Persistencia** | SQLite (modo WAL) |
| **CLI** | Rich + Typer-style |
| **Dashboard** | Streamlit + Plotly |
| **HTTP** | httpx + BeautifulSoup4 |
| **Notificaciones** | Telegram Bot API |
| **Testing** | pytest + pytest-cov |
| **Anti-detección** | UA rotation, stealth scripts, retries con backoff |

## 🚀 Instalación

```powershell
# 1. Clonar
git clone https://github.com/JoeDev10/jobagent-latam.git
cd jobagent-latam

# 2. Crear venv
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt
playwright install chromium

# 4. Configurar credenciales
copy .env.example .env
python configurar.py     # asistente interactivo
```

Necesitás:
- Una **GROQ_API_KEY** gratis en [console.groq.com](https://console.groq.com)
- Una cuenta de **Computrabajo** (opcionalmente Bumeran)
- (Opcional) **Telegram bot** para notificaciones

## 💻 Uso

```powershell
# Configurar perfil desde un CV PDF
python main.py setup

# Buscar y aplicar (modo interactivo, te pide confirmación)
python main.py search

# Modo autónomo (sin confirmación, para Task Scheduler)
python run_auto.py

# Dashboard web
python main.py dashboard      # → http://localhost:8501

# Ver estadísticas
python main.py stats
```

## 🧪 Testing y proceso de QA

Este proyecto incluye un **proceso de QA propio** con:

- ✅ Smoke tests (12 tests, < 2s) que verifican que la app arranca
- ✅ Estrategia de testing documentada en [tests/README.md](tests/README.md)
- ✅ Markers para categorizar (smoke, unit, integration, slow, live)
- ✅ Fixtures compartidas en `conftest.py`
- ✅ Plan de cobertura por módulo

```powershell
# Smoke (rápido, antes de cada cambio)
pytest -m smoke

# Todos los tests
pytest

# Con cobertura
pytest --cov=core --cov=modules --cov-report=term-missing
```

## 📊 Dashboard

El dashboard incluye:

- **Panel de control** con métricas por estado
- **Aplicaciones** con botón "Aplicar ahora" individual
- **Vacantes** filtrables por score y portal
- **Editor de perfil** visual con upload de CV PDF
- **Nueva búsqueda** con progreso en vivo
- **Estadísticas** con histograma de scores, embudo de conversión, timeline

## 🛣️ Roadmap

### v0.1 (actual) — MVP personal
- [x] Scraping Computrabajo, Bumeran, ZonaJobs
- [x] Scoring IA con Groq
- [x] Cartas de presentación
- [x] Bot de aplicación (Playwright)
- [x] Login con persistencia de cookies
- [x] Notificaciones Telegram
- [x] Dashboard Streamlit
- [x] Smoke tests

### v0.2 — Pulir el MVP
- [ ] Snapshot tests de scrapers (HTML fijado)
- [ ] Tests unitarios de funciones de deduplicación
- [ ] CI con GitHub Actions
- [ ] Manejo de captchas (modo manual)
- [ ] Métricas: tasa de respuesta por portal

### v1.0 — SaaS multi-tenant
- [ ] Backend FastAPI + PostgreSQL
- [ ] Auth (Clerk/Supabase)
- [ ] Encriptación de credenciales de portales
- [ ] Frontend Next.js
- [ ] Cola de jobs (Celery + Redis)
- [ ] Hosting en VPS con Playwright

### v2.0 — Apps móviles
- [ ] React Native (iOS + Android)

## 🤝 Contribuir

Este proyecto está en MVP personal pero acepto:

- Reports de bugs (ver template en [tests/README.md](tests/README.md))
- Sugerencias de mejoras vía Issues
- PRs para nuevos portales (LinkedIn, Indeed avanzado)

## 📜 Licencia

MIT — ver [LICENSE](LICENSE)

## 👤 Autor

**Marcelo Joel Rodriguez** — QA Analyst Junior
- GitHub: [@JoeDev10](https://github.com/JoeDev10)

---

> ⚠️ **Disclaimer**: Esta herramienta automatiza acciones en portales de empleo. El uso es bajo responsabilidad del usuario. Respetá los términos y condiciones de cada portal. Diseñada para uso personal en LATAM.
