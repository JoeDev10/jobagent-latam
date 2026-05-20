"""
Clase base para todos los scrapers de portales de empleo.
Incluye:
  - Anti-detección mejorada (stealth headers, fingerprint spoofing)
  - Retry automático con backoff exponencial
  - Scroll y movimientos de ratón realistas
  - Rotación de user-agents
"""
import asyncio
import random
from abc import ABC, abstractmethod
from typing import AsyncGenerator

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from core import JobListing, SearchConfig, get_logger, settings

logger = get_logger(__name__)

# Pool de user-agents realistas (Chrome en Windows, varios builds)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Resoluciones de pantalla comunes
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 1536, "height": 864},
]

# Script stealth: oculta huellas de automatización
STEALTH_SCRIPT = """
// Ocultar webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Plugins reales
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
        ];
        plugins.length = 3;
        return plugins;
    }
});

// Languages
Object.defineProperty(navigator, 'languages', { get: () => ['es-AR', 'es', 'en-US', 'en'] });

// Hardware concurrency realista
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// DeviceMemory
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// Chrome runtime
if (!window.chrome) {
    window.chrome = { runtime: {} };
}

// Permissions
const originalQuery = window.navigator.permissions?.query;
if (originalQuery) {
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
}

// WebGL vendor/renderer
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};
"""


class BaseScraper(ABC):
    """Scraper base con anti-detección, retry y comportamiento humano integrados."""

    portal_name: str = "base"

    def __init__(self):
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self._user_agent = random.choice(USER_AGENTS)
        self._viewport = random.choice(VIEWPORTS)

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=settings.headless,
            slow_mo=settings.slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-notifications",
                "--disable-popup-blocking",
                "--start-maximized",
                "--disable-gpu",
                "--ignore-certificate-errors",
            ],
        )
        self.context = await self.browser.new_context(
            user_agent=self._user_agent,
            viewport=self._viewport,
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            extra_http_headers={
                "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "max-age=0",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        await self.context.add_init_script(STEALTH_SCRIPT)
        return self

    async def __aexit__(self, *args):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        await self._playwright.stop()

    async def new_page(self) -> Page:
        return await self.context.new_page()

    # ─── Navegación con retry ─────────────────────────────────────────────────

    async def safe_goto(
        self,
        page: Page,
        url: str,
        retries: int = 3,
        wait: str = "domcontentloaded",
        timeout: int = 25000,
    ) -> bool:
        """
        Navega a una URL con reintentos automáticos y backoff exponencial.
        Retorna True si tuvo éxito, False si agotó los reintentos.
        """
        for attempt in range(1, retries + 1):
            try:
                await page.goto(url, wait_until=wait, timeout=timeout)
                return True
            except Exception as exc:
                if attempt < retries:
                    wait_s = attempt * random.uniform(3.0, 6.0)
                    logger.warning(
                        f"[{self.portal_name}] Reintento {attempt}/{retries} "
                        f"({wait_s:.1f}s) → {url[:80]} — {exc}"
                    )
                    await asyncio.sleep(wait_s)
                else:
                    logger.error(f"[{self.portal_name}] Falló tras {retries} intentos: {url[:80]}")
                    raise
        return False

    # ─── Comportamiento humano ────────────────────────────────────────────────

    async def human_delay(self, min_s: float = None, max_s: float = None):
        """Pausa aleatoria para simular usuario humano."""
        lo = min_s if min_s is not None else settings.min_delay_between_actions
        hi = max_s if max_s is not None else settings.max_delay_between_actions
        await asyncio.sleep(random.uniform(lo, hi))

    async def human_type(self, page: Page, selector: str, text: str):
        """Tipea carácter por carácter con delays variables."""
        await page.click(selector)
        await asyncio.sleep(random.uniform(0.2, 0.5))
        for char in text:
            await page.keyboard.type(char)
            await asyncio.sleep(random.uniform(0.04, 0.15))

    async def random_scroll(self, page: Page, min_px: int = 100, max_px: int = 600):
        """Simula scroll humano hasta un punto aleatorio de la página."""
        try:
            total_height = await page.evaluate("document.body.scrollHeight")
            if total_height > max_px:
                target = random.randint(min_px, min(max_px, total_height // 2))
                await page.evaluate(
                    f"window.scrollTo({{top: {target}, behavior: 'smooth'}})"
                )
                await asyncio.sleep(random.uniform(0.3, 0.9))
        except Exception:
            pass

    async def random_mouse_move(self, page: Page):
        """Mueve el ratón a una posición aleatoria de la ventana."""
        try:
            w = self._viewport["width"]
            h = self._viewport["height"]
            x = random.randint(100, w - 100)
            y = random.randint(100, h - 100)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.1, 0.4))
        except Exception:
            pass

    # ─── Métodos abstractos ───────────────────────────────────────────────────

    @abstractmethod
    async def search(self, config: SearchConfig) -> AsyncGenerator[JobListing, None]:
        """Busca vacantes y las devuelve una a una."""
        ...

    @abstractmethod
    async def get_job_detail(self, url: str) -> JobListing:
        """Obtiene el detalle completo de una vacante."""
        ...

    # ─── Utilitarios ─────────────────────────────────────────────────────────

    @staticmethod
    def _text(el) -> str | None:
        return el.get_text(strip=True) if el else None

    @staticmethod
    def _detect_modality_from_text(text: str):
        """Detecta modalidad a partir de texto libre."""
        from core import JobModality
        t = text.lower()
        if any(w in t for w in ("100% remoto", "full remote", "fully remote", "trabajo remoto", "teletrabajo")):
            return JobModality.REMOTE
        if any(w in t for w in ("remoto", "remote", "home office")):
            return JobModality.REMOTE
        if any(w in t for w in ("híbrido", "hibrido", "hybrid", "modalidad mixta")):
            return JobModality.HYBRID
        if any(w in t for w in ("presencial", "on-site", "onsite", "oficina")):
            return JobModality.ONSITE
        return JobModality.ANY
