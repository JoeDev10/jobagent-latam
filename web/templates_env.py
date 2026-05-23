"""
Instancia compartida de Jinja2Templates para todos los routers.
Usa cache_size=0 para evitar el bug de hashabilidad entre Starlette 1.0 y Jinja2 3.1.6.
"""
from pathlib import Path
import jinja2
from fastapi.templating import Jinja2Templates

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates")),
    cache_size=0,
    autoescape=jinja2.select_autoescape(["html"]),
)

templates = Jinja2Templates(env=_env)
