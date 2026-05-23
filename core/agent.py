"""
Agente central: orquesta scraping, scoring, generación de cartas y aplicación.
"""
import asyncio
import uuid
from datetime import datetime
from typing import AsyncGenerator, Callable, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from core import (
    Application, ApplicationStatus, JobListing,
    Portal, SearchConfig, UserProfile, get_logger,
)
from modules.ai import CoverLetterGenerator, JobScorer
from modules.applicator import ApplicationBot
from modules.notifier import TelegramNotifier
from modules.scrapers import get_scraper
from modules.tracker import ApplicationTracker

logger = get_logger(__name__)
console = Console(legacy_windows=False)


class JobAgent:
    """
    Agente principal que coordina todo el flujo:
    Buscar → Evaluar → Generar carta → (Aprobar) → Aplicar → Trackear → Notificar
    """

    def __init__(self):
        self.scorer = JobScorer()
        self.cover_letter_gen = CoverLetterGenerator()
        self.tracker = ApplicationTracker()
        self.notifier = TelegramNotifier()
        self._progress: Optional[Callable[[str], None]] = None

    def _emit(self, msg: str):
        if self._progress:
            try:
                self._progress(msg)
            except Exception as e:
                logger.warning(f"progress_callback falló: {e}")

    async def run(
        self,
        profile: UserProfile,
        config: SearchConfig,
        interactive: bool = True,
        progress_callback: Optional[Callable[[str], None]] = None,
        skip_cover_letters: bool = False,
    ) -> list[Application]:
        self._progress = progress_callback
        console.rule("[bold blue]JobAgent LATAM — Iniciando búsqueda[/bold blue]")
        console.print(f"Portales: {[p.value for p in config.portals]}")
        console.print(f"Keywords: {config.keywords}")
        console.print(f"Score mínimo: {config.min_relevance_score}")
        console.print()
        self._emit(f"Iniciando búsqueda en {len(config.portals)} portal(es)...")

        await self.notifier.notify_search_started(
            [p.value for p in config.portals], config.keywords
        )

        # 1. Scraping
        all_jobs = await self._scrape_all_portals(config, profile)
        console.print(f"\n[green]✓ Vacantes encontradas: {len(all_jobs)}[/green]")
        self._emit(f"Scraping completo: {len(all_jobs)} vacantes encontradas")

        if not all_jobs:
            console.print("[yellow]No se encontraron vacantes. Intentá con otras keywords.[/yellow]")
            self._emit("No se encontraron vacantes con esas keywords")
            await self.notifier.notify_vacantes_found(0, 0, config.min_relevance_score)
            return []

        # 2. Scoring con IA (en lotes para respetar rate limit)
        console.print("\n[blue]Evaluando relevancia con IA...[/blue]")
        self._emit(f"Evaluando relevancia de {len(all_jobs)} vacantes con IA...")
        relevant_jobs = await self._score_and_filter(all_jobs, profile, config.min_relevance_score)
        console.print(f"[green]✓ Vacantes relevantes: {len(relevant_jobs)}[/green]")
        self._emit(f"Scoring completo: {len(relevant_jobs)} vacantes superaron el score mínimo")

        await self.notifier.notify_vacantes_found(
            len(all_jobs), len(relevant_jobs), config.min_relevance_score
        )

        if not relevant_jobs:
            console.print(f"[yellow]Ninguna vacante superó el score mínimo de {config.min_relevance_score}.[/yellow]")
            return []

        self._print_jobs_table(relevant_jobs)
        await self.notifier.notify_top_jobs(relevant_jobs, max_show=5)

        # 3. Preparación de aplicaciones (cartas opcionales)
        applications = await self._prepare_applications(
            relevant_jobs, profile, generate_letters=not skip_cover_letters
        )

        # 4. Guardar en tracker
        for app in applications:
            self.tracker.save_application(app)

        # 5. Aplicar
        if config.auto_apply:
            applied = await self._apply_all(applications)
        elif interactive:
            applied = await self._apply_interactive(applications)
        else:
            console.print("\n[yellow]Modo no interactivo: aplicaciones guardadas como pendientes.[/yellow]")
            applied = []

        # 6. Resumen
        self._print_summary(applications, applied)
        await self.notifier.notify_daily_summary(self.tracker.get_stats())
        return applications

    # ─── Pasos internos ───────────────────────────────────────────────────────

    @staticmethod
    def _title_key(title: str, company: str) -> str:
        import re
        t = re.sub(r"[^a-z0-9 ]", "", (title + " " + company).lower())
        for stop in ("ref", "remoto", "argentina", "ssr", "sr", "jr", "semi", "senior", "junior"):
            t = t.replace(stop, "")
        return re.sub(r"\s+", " ", t).strip()

    @staticmethod
    def _is_blacklisted(job: JobListing, profile: UserProfile) -> bool:
        if not profile.exclude_companies:
            return False
        company_lower = job.company.lower()
        return any(exc.lower() in company_lower for exc in profile.exclude_companies)

    async def _scrape_all_portals(self, config: SearchConfig, profile: UserProfile) -> list[JobListing]:
        all_jobs = []
        seen_urls: set[str] = set()
        seen_keys: set[str] = set()
        max_retries = 2

        for portal in config.portals:
            console.print(f"\n[cyan]Scrapeando {portal.value}...[/cyan]")
            self._emit(f"Scrapeando {portal.value}...")
            for attempt in range(max_retries + 1):
                try:
                    scraper = get_scraper(portal)
                    async with scraper as s:
                        async for job in s.search(config):
                            if job.url in seen_urls or self.tracker.job_exists(job.url):
                                logger.debug(f"Duplicada (URL): {job.url}")
                                continue
                            key = self._title_key(job.title, job.company)
                            if key in seen_keys:
                                logger.debug(f"Duplicada (título): {job.title} @ {job.company}")
                                continue
                            if self._is_blacklisted(job, profile):
                                logger.info(f"Empresa en blacklist, ignorada: {job.company}")
                                continue
                            seen_urls.add(job.url)
                            seen_keys.add(key)
                            all_jobs.append(job)
                            console.print(f"  + {job.title} @ {job.company}")
                    break  # éxito
                except Exception as e:
                    if attempt < max_retries:
                        wait = 5 * (attempt + 1)
                        console.print(f"  [yellow]Error en {portal.value} (intento {attempt + 1}/{max_retries + 1}), reintentando en {wait}s...[/yellow]")
                        logger.warning(f"Error en {portal.value} intento {attempt + 1}: {e}")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Error scrapeando {portal.value} después de {max_retries + 1} intentos: {e}")
                        await self.notifier.notify_error(f"Error en scraping de {portal.value}: {e}")

        return all_jobs

    async def _score_and_filter(
        self, jobs: list[JobListing], profile: UserProfile, min_score: float
    ) -> list[JobListing]:
        # Lotes de 3 para respetar el límite de TPM del free tier de Groq (6000 TPM)
        batch_size = 3
        pause_between_batches = 12
        relevant = []

        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            total_batches = (len(jobs) + batch_size - 1) // batch_size
            batch_num = i // batch_size + 1
            console.print(f"  Lote {batch_num}/{total_batches} ({len(batch)} vacantes)...")
            self._emit(f"Evaluando lote {batch_num}/{total_batches} con IA...")

            results = await asyncio.gather(
                *[self.scorer.score(job, profile) for job in batch],
                return_exceptions=True,
            )

            for job, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.warning(f"Error evaluando {job.title}: {result}")
                    continue
                self.tracker.save_job(result)
                if result.relevance_score >= min_score:
                    relevant.append(result)

            if i + batch_size < len(jobs):
                console.print(f"  [dim]Pausa {pause_between_batches}s (rate limit Groq)...[/dim]")
                await asyncio.sleep(pause_between_batches)

        relevant.sort(key=lambda j: j.relevance_score or 0, reverse=True)
        return relevant

    async def _prepare_applications(
        self, jobs: list[JobListing], profile: UserProfile, generate_letters: bool = True
    ) -> list[Application]:
        if generate_letters:
            console.print(f"\n[blue]Generando {len(jobs)} cartas de presentación...[/blue]")
            self._emit(f"Generando {len(jobs)} cartas de presentación...")

        applications = []
        for i, job in enumerate(jobs, 1):
            app = Application(
                id=str(uuid.uuid4()),
                job=job,
                profile=profile,
                status=ApplicationStatus.PENDING,
            )
            if generate_letters:
                try:
                    app = await self.cover_letter_gen.generate_for_application(app)
                    console.print(f"  [{i}/{len(jobs)}] Carta lista: {job.title[:40]}")
                    self._emit(f"Carta {i}/{len(jobs)}: {job.title[:50]}")
                except Exception as e:
                    logger.warning(f"Error generando carta para {job.title}: {e}")
                if i < len(jobs):
                    await asyncio.sleep(4)
            applications.append(app)

        if generate_letters:
            console.print(f"[green]✓ {len(applications)} aplicaciones preparadas[/green]")
        else:
            self._emit(f"Guardando {len(applications)} vacantes en tu panel...")

        return applications

    async def _apply_all(self, applications: list[Application]) -> list[Application]:
        applied = []
        async with ApplicationBot() as bot:
            for app in applications:
                if app.status != ApplicationStatus.PENDING:
                    continue
                app = await bot.apply(app)
                self.tracker.update_status(app.id, app.status, app.notes)
                if app.status == ApplicationStatus.APPLIED:
                    applied.append(app)
                    await self.notifier.notify_applied(app)
                else:
                    await self.notifier.notify_apply_failed(app, app.notes or "Sin detalle")
                await asyncio.sleep(3)
        return applied

    async def _apply_interactive(self, applications: list[Application]) -> list[Application]:
        applied = []
        console.print("\n[bold]Revisión manual de aplicaciones:[/bold]")
        console.print("(s = aplicar, n = saltar, v = ver carta, q = terminar)\n")

        async with ApplicationBot() as bot:
            for i, app in enumerate(applications, 1):
                job = app.job
                console.print(f"\n[bold cyan]── Vacante {i}/{len(applications)} ──[/bold cyan]")
                console.print(f"Título:   [white]{job.title}[/white]")
                console.print(f"Empresa:  [white]{job.company}[/white]")
                score = job.relevance_score or 0
                color = 'green' if score >= 0.8 else 'yellow'
                console.print(f"Score:    [{color}]{score:.0%}[/{color}]")
                console.print(f"Motivo:   {job.relevance_reason}")
                console.print(f"Salario:  {job.salary_range or 'No especificado'}")
                console.print(f"URL:      {job.url}")

                choice = console.input("\n¿Qué hacemos? [s/n/v/q]: ").strip().lower()

                if choice == "q":
                    break
                elif choice == "v":
                    console.print(f"\n[italic]{app.cover_letter or 'Sin carta generada'}[/italic]")
                    choice = console.input("\n¿Aplicamos? [s/n]: ").strip().lower()

                if choice == "s":
                    console.print("Aplicando...", end=" ")
                    app = await bot.apply(app)
                    self.tracker.update_status(app.id, app.status, app.notes)
                    if app.status == ApplicationStatus.APPLIED:
                        applied.append(app)
                        console.print("[green]✓ Aplicado![/green]")
                        await self.notifier.notify_applied(app)
                    else:
                        console.print(f"[yellow]Pendiente: {app.notes}[/yellow]")
                        await self.notifier.notify_apply_failed(app, app.notes or "Sin detalle")
                    await asyncio.sleep(2)
                elif choice == "n":
                    self.tracker.update_status(app.id, ApplicationStatus.DISCARDED)
                    console.print("[dim]Descartada[/dim]")

        return applied

    # ─── Display ──────────────────────────────────────────────────────────────

    def _print_jobs_table(self, jobs: list[JobListing]):
        table = Table(title="Vacantes Relevantes", show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Título", style="cyan", max_width=35)
        table.add_column("Empresa", max_width=20)
        table.add_column("Score", justify="center", width=8)
        table.add_column("Portal", width=12)
        table.add_column("Modalidad", width=10)

        for i, job in enumerate(jobs, 1):
            score = job.relevance_score or 0
            color = "green" if score >= 0.8 else "yellow" if score >= 0.65 else "red"
            table.add_row(
                str(i),
                job.title[:35],
                job.company[:20],
                f"[{color}]{score:.0%}[/{color}]",
                job.portal.value,
                job.modality.value if job.modality else "-",
            )
        console.print(table)

    def _print_summary(self, applications: list[Application], applied: list[Application]):
        console.rule("[bold green]Resumen[/bold green]")
        stats = self.tracker.get_stats()
        console.print(f"Vacantes evaluadas:    {len(applications)}")
        console.print(f"Aplicaciones enviadas: {len(applied)}")
        console.print(f"Total histórico:       {stats['total_applications']}")
        console.print(f"Score promedio:        {stats['avg_relevance_score']:.2f}")
        by_status = stats.get("by_status", {})
        if by_status:
            console.print("\nPor estado:")
            for status, count in by_status.items():
                console.print(f"  {status}: {count}")
