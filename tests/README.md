# Estrategia de QA — JobAgent LATAM

Este directorio contiene la suite de tests del proyecto. La estrategia sigue la **pirámide de testing** clásica:

```
            ┌─────────┐
            │   E2E   │   ← Pocos, lentos, costosos. Validan flujos completos.
           ┌┴─────────┴┐
           │Integration│   ← DB, scrapers con HTML fijado, mocks de LLM.
          ┌┴───────────┴┐
          │    Unit     │  ← Muchos, rápidos, funciones puras.
         ┌┴─────────────┴┐
         │     Smoke     │  ← Base: ¿la app arranca sin explotar?
         └───────────────┘
```

## Cómo correr los tests

```powershell
# Activar el venv (si no lo tenés activo)
.\venv\Scripts\Activate.ps1

# Correr TODO
pytest

# Solo smoke tests (rápido, < 5s — usar antes de cada commit)
pytest -m smoke

# Solo unit tests (cuando existan)
pytest -m unit

# Excluir tests lentos
pytest -m "not slow"

# Con reporte de cobertura
pytest --cov=core --cov=modules --cov-report=term-missing

# Un test específico
pytest tests/test_smoke.py::test_settings_load -v

# Buscar por nombre (patrón)
pytest -k "profile"
```

## Markers (categorías de tests)

Definidos en `pytest.ini`:

| Marker | Para qué | Cuándo correr |
|---|---|---|
| `smoke` | Verifica que la app arranca | Antes de **cada cambio** |
| `unit` | Funciones puras, sin red ni DB persistente | Antes de cada commit |
| `integration` | DB + módulos enteros | Antes de cada push |
| `slow` | Tests > 5 segundos | En CI o manualmente |
| `live` | Requieren internet o API keys reales | **NUNCA en CI** — solo manual |

Aplicar un marker:
```python
@pytest.mark.smoke
def test_imports_core():
    ...
```

## Qué cubre actualmente

### `test_smoke.py` (12 tests, ~2s)

| # | Test | Qué verifica |
|---|---|---|
| 1 | `test_imports_core` | Símbolos públicos de `core` se importan |
| 2 | `test_imports_modules` | Todos los módulos (`profile`, `tracker`, `ai`, ...) cargan y `get_scraper()` devuelve algo para cada portal |
| 3 | `test_imports_agent` | `JobAgent` se instancia con sus componentes conectados |
| 4 | `test_settings_load` | `.env` se lee y `settings` tiene los campos requeridos |
| 5 | `test_job_listing_model` | Pydantic `JobListing` roundtrip (serializar/deserializar) |
| 6 | `test_user_profile_model` | Pydantic `UserProfile` con defaults sensatos |
| 7 | `test_search_config_validation` | `SearchConfig` aplica defaults seguros (`auto_apply=False`) |
| 8 | `test_tracker_init_and_integrity` | DB se crea y `PRAGMA integrity_check` == `ok` |
| 9 | `test_tracker_save_and_query` | Roundtrip de un Job: save → query → existe |
| 10 | `test_profile_manager_lists_profiles` | `list_profiles()` devuelve una lista |
| 11 | `test_profile_load_marcelo` | El perfil real "marcelo" deserializa correctamente |
| 12 | `test_critical_files_exist` | Archivos esperados (`main.py`, `run_auto.py`, etc.) existen |

## Roadmap de testing

### Próximas tandas (orden de prioridad)

1. **`test_dedup.py`** — Tests unitarios de `_title_key()` y deduplicación. Crítico porque si falla aplicás 5 veces a la misma vacante.
2. **`test_modality_detection.py`** — `_detect_modality_from_text()` con muchos casos border.
3. **`test_scrapers_offline.py`** — Snapshot tests con HTML fijado de cada portal. Cuando los selectores cambian, el test te avisa **antes** que producción.
4. **`test_tracker_full.py`** — Más integración con tracker: status updates, queries complejas.
5. **`test_login_selectors.py`** — Marker `live`: navega a las páginas de login reales y verifica que los selectores existen (sin loguearse).

### Qué NO testeamos en CI y por qué

- **Llamadas reales a Groq** → quema cuota gratis, flaky por rate limits
- **Scraping en vivo** → los portales pueden cambiar HTML y romper CI sin que sea tu culpa
- **Aplicaciones reales a vacantes** → tiene efectos secundarios irreversibles

Estos casos se testean manualmente con scripts dedicados (`check_*.py`).

## Cobertura objetivo

| Área | Coverage mínimo |
|---|---|
| `core/` (models, config, agent) | 80% |
| `modules/tracker` | 80% |
| `modules/ai` | 60% (depende de LLM, mockeado) |
| `modules/scrapers` | 50% (la mayoría es navegación de Playwright) |
| `modules/applicator` | 40% (idem) |

Generar el reporte:
```powershell
pytest --cov=core --cov=modules --cov-report=html
# Abre htmlcov/index.html en el navegador
```

## Convenciones

- **Nombre de tests**: `test_<qué_hace>` — descriptivo, no genérico (`test_dedup_ignores_case` mejor que `test_dedup_1`)
- **Un assert por concepto**: si un test verifica 3 cosas distintas, dividilo en 3
- **No dependencias entre tests**: cada test debe ser independiente. Si querés correr uno solo, debe pasar.
- **Fixtures en `conftest.py`**: para datos compartidos. No copies un `sample_job` en cada archivo.
- **Mocks para servicios externos**: usar `monkeypatch` o `unittest.mock`. Nunca pegarle al API real en un test automatizado.

## Reportar un bug encontrado

Si un test falla y descubrís un bug real:

1. Crear un issue en GitHub con template:
   ```
   ### Resumen
   <una línea>

   ### Severidad
   - [ ] Crítico (rompe el flujo principal)
   - [ ] Alto (rompe un feature secundario)
   - [ ] Medio (workaround posible)
   - [ ] Bajo (cosmético)

   ### Pasos para reproducir
   1. ...

   ### Resultado esperado
   ...

   ### Resultado obtenido
   ...

   ### Entorno
   - OS:
   - Python:
   - Commit hash:
   ```

2. Si lo arreglás, agregá un test que cubra ese caso para que **nunca vuelva a pasar** (test de regresión).
