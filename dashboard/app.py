"""
Dashboard web con Streamlit para visualizar y gestionar aplicaciones.
Ejecutar con: streamlit run dashboard/app.py
"""
import io
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from core import (
    ApplicationStatus,
    Education,
    ExperienceLevel,
    JobModality,
    Portal,
    SearchConfig,
    UserProfile,
    WorkExperience,
)
from modules.profile import ProfileManager
from modules.tracker import ApplicationTracker
from dashboard.runner import apply_one, run_search

# ─── Configuración ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="JobAgent LATAM",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

tracker = ApplicationTracker()
profile_manager = ProfileManager()

# ─── Helpers de sesión ────────────────────────────────────────────────────────

if "selected_profile" not in st.session_state:
    profiles = profile_manager.list_profiles()
    st.session_state.selected_profile = profiles[0] if profiles else None

if "search_log" not in st.session_state:
    st.session_state.search_log = []

if "last_search_summary" not in st.session_state:
    st.session_state.last_search_summary = None


def _current_profile() -> UserProfile | None:
    name = st.session_state.get("selected_profile")
    if not name:
        return None
    return profile_manager.load(name)


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🎯 JobAgent LATAM")
    st.markdown("---")

    page = st.radio(
        "Navegación",
        [
            "📊 Dashboard",
            "📋 Aplicaciones",
            "🔍 Vacantes",
            "👤 Mi Perfil",
            "⚙️ Nueva Búsqueda",
            "📈 Estadísticas",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    profiles = profile_manager.list_profiles()
    if profiles:
        st.session_state.selected_profile = st.selectbox(
            "Perfil activo",
            profiles,
            index=profiles.index(st.session_state.selected_profile) if st.session_state.selected_profile in profiles else 0,
        )

    st.markdown("---")
    stats = tracker.get_stats()
    st.metric("Vacantes analizadas", stats["total_jobs_scraped"])
    st.metric("Aplicaciones totales", stats["total_applications"])
    st.metric("Score promedio", f"{stats['avg_relevance_score']:.0%}")


# ─── Dashboard ────────────────────────────────────────────────────────────────

if page == "📊 Dashboard":
    st.title("📊 Dashboard")

    by_status = stats.get("by_status", {})
    cols = st.columns(5)

    status_config = [
        ("pendiente", "⏳ Pendientes"),
        ("aplicada", "✅ Aplicadas"),
        ("entrevista", "🤝 Entrevistas"),
        ("oferta", "🎉 Ofertas"),
        ("descartada", "❌ Descartadas"),
    ]

    for col, (key, label) in zip(cols, status_config):
        col.metric(label, by_status.get(key, 0))

    st.markdown("---")
    st.subheader("Aplicaciones recientes")
    applications = tracker.get_applications()

    if applications:
        df = pd.DataFrame(applications)
        df = df[["title", "company", "portal", "status", "relevance_score", "created_at", "salary_range"]].copy()
        df.columns = ["Puesto", "Empresa", "Portal", "Estado", "Score", "Fecha", "Salario"]
        df["Score"] = df["Score"].apply(lambda x: f"{x:.0%}" if x else "-")
        df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.strftime("%d/%m %H:%M")

        status_colors = {
            "pendiente": "🟡",
            "aplicada": "🟢",
            "entrevista": "🔵",
            "oferta": "🌟",
            "descartada": "🔴",
            "rechazada": "🔴",
        }
        df["Estado"] = df["Estado"].apply(lambda s: f"{status_colors.get(s, '')} {s}")
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Todavía no hay aplicaciones. ¡Iniciá una búsqueda!")


# ─── Aplicaciones ─────────────────────────────────────────────────────────────

elif page == "📋 Aplicaciones":
    st.title("📋 Mis Aplicaciones")

    col_filter, col_count, col_export = st.columns([3, 1, 1])
    status_filter = col_filter.selectbox(
        "Filtrar por estado",
        ["Todas"] + [s.value for s in ApplicationStatus],
    )

    status_enum = None if status_filter == "Todas" else ApplicationStatus(status_filter)
    applications = tracker.get_applications(status_enum)
    col_count.metric("Resultados", len(applications))

    if applications:
        export_cols = ["title", "company", "portal", "status", "relevance_score", "salary_range", "location", "url", "created_at", "notes"]
        df_export = pd.DataFrame(applications)[[c for c in export_cols if c in pd.DataFrame(applications).columns]]
        df_export.columns = [c.replace("_", " ").title() for c in df_export.columns]
        csv_bytes = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        col_export.download_button("⬇️ CSV", csv_bytes, "aplicaciones.csv", "text/csv", use_container_width=True)

    if not applications:
        st.info("No hay aplicaciones con ese filtro.")
    else:
        profile = _current_profile()

        for app in applications:
            score = app.get("relevance_score") or 0
            score_color = "🟢" if score >= 0.8 else "🟡" if score >= 0.65 else "🔴"
            status = app["status"]

            with st.expander(f"{score_color} {app['title']} @ {app['company']} — {status.upper()}"):
                col1, col2, col3 = st.columns(3)
                col1.markdown(f"**Portal:** {app['portal']}")
                col2.markdown(f"**Score:** {score:.0%}")
                col3.markdown(f"**Fecha:** {app['created_at'][:10]}")

                if app.get("salary_range"):
                    st.markdown(f"**Salario:** {app['salary_range']}")
                if app.get("location"):
                    st.markdown(f"**Ubicación:** {app['location']}")

                st.markdown(f"**URL:** [{app['url']}]({app['url']})")

                if app.get("cover_letter"):
                    with st.expander("📝 Ver carta de presentación"):
                        st.markdown(app["cover_letter"])

                # Acciones
                action_col1, action_col2 = st.columns(2)

                with action_col1:
                    new_status = st.selectbox(
                        "Cambiar estado",
                        [s.value for s in ApplicationStatus],
                        index=[s.value for s in ApplicationStatus].index(status),
                        key=f"status_{app['id']}",
                    )
                    notes = st.text_input("Notas", value=app.get("notes") or "", key=f"notes_{app['id']}")
                    if st.button("💾 Guardar cambios", key=f"save_{app['id']}"):
                        tracker.update_status(app["id"], ApplicationStatus(new_status), notes or None)
                        st.success("Estado actualizado")
                        st.rerun()

                with action_col2:
                    if status == "pendiente" and app.get("cover_letter"):
                        st.markdown("**Aplicar automáticamente:**")
                        st.caption("Abre Playwright (visible si HEADLESS=false en .env) y aplica con la carta generada.")
                        if st.button("🚀 Aplicar ahora", key=f"apply_{app['id']}", type="primary"):
                            with st.spinner(f"Aplicando a {app['title'][:40]}..."):
                                try:
                                    result = apply_one(app["id"], profile=profile)
                                    if result.status == ApplicationStatus.APPLIED:
                                        st.success(f"✅ Aplicado a {app['title']}")
                                    else:
                                        st.warning(f"⏸️ Pendiente: {result.notes or 'Sin detalle'}")
                                except Exception as e:
                                    st.error(f"Error al aplicar: {e}")
                            st.rerun()
                    elif status == "pendiente":
                        st.warning("Sin carta de presentación generada — no se puede aplicar todavía.")
                    else:
                        st.info(f"Esta aplicación ya está en estado **{status}**")

                    # Blacklist rápida
                    company = app["company"]
                    current_profile = _current_profile()
                    if current_profile and company.lower() not in [e.lower() for e in current_profile.exclude_companies]:
                        if st.button(f"🚫 Bloquear {company[:25]}", key=f"bl_{app['id']}"):
                            updated = current_profile.model_copy(
                                update={"exclude_companies": current_profile.exclude_companies + [company]}
                            )
                            profile_manager.save(updated, st.session_state.selected_profile)
                            st.success(f"'{company}' agregada a la blacklist")
                            st.rerun()


# ─── Vacantes ─────────────────────────────────────────────────────────────────

elif page == "🔍 Vacantes":
    st.title("🔍 Vacantes Encontradas")

    col1, col2, col3 = st.columns(3)
    min_score = col1.slider("Score mínimo", 0.0, 1.0, 0.65, 0.05)
    portal_filter = col2.selectbox("Portal", ["Todos"] + [p.value for p in Portal])
    limit = col3.number_input("Máximo de resultados", 10, 200, 50)

    portal_enum = None if portal_filter == "Todos" else Portal(portal_filter)
    jobs = tracker.get_jobs(min_score=min_score, portal=portal_enum, limit=int(limit))

    st.markdown(f"**{len(jobs)} vacantes encontradas**")

    for job in jobs:
        score = job.relevance_score or 0
        score_color = "🟢" if score >= 0.8 else "🟡" if score >= 0.65 else "🔴"

        with st.expander(f"{score_color} [{score:.0%}] {job.title} @ {job.company}"):
            col1, col2 = st.columns(2)
            col1.markdown(f"**Portal:** {job.portal.value}")
            col2.markdown(f"**Modalidad:** {job.modality.value if job.modality else '-'}")

            if job.relevance_reason:
                st.info(job.relevance_reason)

            if job.match_strengths:
                st.markdown("**Puntos fuertes:**")
                for s in job.match_strengths:
                    st.markdown(f"  ✅ {s}")

            if job.match_gaps:
                st.markdown("**Brechas:**")
                for g in job.match_gaps:
                    st.markdown(f"  ⚠️ {g}")

            st.markdown(f"[Ver vacante completa]({job.url})")


# ─── Perfil ───────────────────────────────────────────────────────────────────

elif page == "👤 Mi Perfil":
    st.title("👤 Mi Perfil")

    profiles = profile_manager.list_profiles()
    profile = _current_profile()

    tab_view, tab_edit, tab_import = st.tabs(["👁️ Ver", "✏️ Editar", "📄 Importar CV"])

    # ── Tab 1: Vista ──────────────────────────────────────────────────────────
    with tab_view:
        if not profile:
            st.warning("No tenés ningún perfil creado todavía. Usá la pestaña 'Importar CV' o 'Editar'.")
        else:
            st.subheader(f"{profile.full_name}")
            st.markdown(f"*{profile.headline}*")
            col1, col2, col3 = st.columns(3)
            col1.markdown(f"📧 {profile.email}")
            col2.markdown(f"📱 {profile.phone}")
            col3.markdown(f"📍 {profile.location}")

            if profile.linkedin_url:
                st.markdown(f"🔗 [LinkedIn]({profile.linkedin_url})")

            st.markdown("**Resumen:**")
            st.write(profile.summary)

            col_a, col_b = st.columns(2)
            col_a.markdown(f"**Nivel:** {profile.experience_level.value}")
            col_a.markdown(f"**Modalidad preferida:** {profile.preferred_modality.value}")
            col_b.markdown(f"**Roles buscados:** {', '.join(profile.target_roles)}")

            if profile.work_experience:
                st.markdown("### Experiencia")
                for exp in profile.work_experience:
                    with st.expander(f"{exp.role} @ {exp.company} ({exp.start_date} – {exp.end_date})"):
                        st.write(exp.description)
                        if exp.achievements:
                            st.markdown("**Logros:**")
                            for a in exp.achievements:
                                st.markdown(f"- {a}")

            if profile.education:
                st.markdown("### Educación")
                for edu in profile.education:
                    st.markdown(f"- **{edu.degree}** en {edu.field} — *{edu.institution}* ({edu.start_year}–{edu.end_year or 'actual'})")

            col_s1, col_s2 = st.columns(2)
            col_s1.markdown("**Skills técnicas:**")
            col_s1.markdown(", ".join(profile.hard_skills) or "—")
            col_s2.markdown("**Skills blandas:**")
            col_s2.markdown(", ".join(profile.soft_skills) or "—")

            if profile.languages:
                st.markdown("**Idiomas:**")
                for lang, level in profile.languages.items():
                    st.markdown(f"- {lang}: {level}")

    # ── Tab 2: Editar ─────────────────────────────────────────────────────────
    with tab_edit:
        if not profile:
            st.info("Creá el perfil desde 'Importar CV' o llenándolo manualmente acá.")
            profile = UserProfile(
                full_name="", email="", phone="", location="",
                headline="", summary="",
                experience_level=ExperienceLevel.JUNIOR,
                target_roles=[],
            )

        with st.form("edit_profile"):
            st.markdown("### Datos básicos")
            c1, c2 = st.columns(2)
            full_name = c1.text_input("Nombre completo", value=profile.full_name)
            email = c2.text_input("Email", value=profile.email)
            c3, c4 = st.columns(2)
            phone = c3.text_input("Teléfono", value=profile.phone)
            location = c4.text_input("Ubicación", value=profile.location)
            linkedin = st.text_input("LinkedIn URL", value=profile.linkedin_url or "")
            portfolio = st.text_input("Portfolio URL", value=profile.portfolio_url or "")

            st.markdown("### Perfil profesional")
            headline = st.text_input("Headline (título profesional corto)", value=profile.headline)
            summary = st.text_area("Resumen profesional", value=profile.summary, height=150)

            c5, c6 = st.columns(2)
            level_options = [e.value for e in ExperienceLevel]
            level_idx = level_options.index(profile.experience_level.value) if profile.experience_level else 0
            experience_level = c5.selectbox("Nivel", level_options, index=level_idx)
            modality_options = [m.value for m in JobModality]
            modality_idx = modality_options.index(profile.preferred_modality.value) if profile.preferred_modality else 0
            preferred_modality = c6.selectbox("Modalidad preferida", modality_options, index=modality_idx)

            target_roles = st.text_input(
                "Roles buscados (separados por coma)",
                value=", ".join(profile.target_roles),
            )
            target_industries = st.text_input(
                "Industrias preferidas (separadas por coma)",
                value=", ".join(profile.target_industries),
            )

            st.markdown("### Experiencia laboral")
            st.caption("Editá, agregá o eliminá filas. Las fechas pueden ser 'AAAA-MM' o texto libre como 'Actual'.")
            exp_data = pd.DataFrame([
                {
                    "Empresa": e.company,
                    "Rol": e.role,
                    "Desde": e.start_date,
                    "Hasta": e.end_date or "Actual",
                    "Descripción": e.description,
                    "Logros (separados por ; )": "; ".join(e.achievements),
                }
                for e in profile.work_experience
            ])
            if exp_data.empty:
                exp_data = pd.DataFrame(columns=["Empresa", "Rol", "Desde", "Hasta", "Descripción", "Logros (separados por ; )"])
            edited_exp = st.data_editor(exp_data, use_container_width=True, num_rows="dynamic", key="exp_editor")

            st.markdown("### Educación")
            edu_data = pd.DataFrame([
                {
                    "Institución": e.institution,
                    "Título": e.degree,
                    "Área": e.field,
                    "Desde": e.start_year,
                    "Hasta": e.end_year or "",
                    "Completado": e.completed,
                }
                for e in profile.education
            ])
            if edu_data.empty:
                edu_data = pd.DataFrame(columns=["Institución", "Título", "Área", "Desde", "Hasta", "Completado"])
            edited_edu = st.data_editor(edu_data, use_container_width=True, num_rows="dynamic", key="edu_editor")

            st.markdown("### Skills e idiomas")
            hard_skills = st.text_input(
                "Skills técnicas (separadas por coma)",
                value=", ".join(profile.hard_skills),
            )
            soft_skills = st.text_input(
                "Skills blandas (separadas por coma)",
                value=", ".join(profile.soft_skills),
            )
            languages_text = st.text_input(
                "Idiomas (formato 'Idioma:Nivel, ...')",
                value=", ".join(f"{k}:{v}" for k, v in profile.languages.items()),
            )
            min_salary = st.number_input(
                "Salario mínimo (opcional)",
                min_value=0,
                value=profile.min_salary or 0,
            )
            exclude_companies = st.text_input(
                "Empresas a ignorar / blacklist (separadas por coma)",
                value=", ".join(profile.exclude_companies),
                help="El agente ignorará vacantes de estas empresas. Útil para agencias de RRHH o empresas que ya te rechazaron.",
            )

            profile_name = st.text_input(
                "Nombre del perfil (para guardar)",
                value=st.session_state.get("selected_profile") or "default",
            )

            submitted = st.form_submit_button("💾 Guardar perfil", type="primary")
            if submitted:
                try:
                    # Reconstruir listas
                    work_experience = []
                    for _, row in edited_exp.iterrows():
                        if not row.get("Empresa") or not row.get("Rol"):
                            continue
                        achievements_raw = row.get("Logros (separados por ; )") or ""
                        work_experience.append(WorkExperience(
                            company=str(row["Empresa"]),
                            role=str(row["Rol"]),
                            start_date=str(row.get("Desde") or ""),
                            end_date=str(row.get("Hasta") or "Actual"),
                            description=str(row.get("Descripción") or ""),
                            achievements=[a.strip() for a in str(achievements_raw).split(";") if a.strip()],
                        ))

                    education = []
                    for _, row in edited_edu.iterrows():
                        if not row.get("Institución") or not row.get("Título"):
                            continue
                        try:
                            start = int(row.get("Desde") or 0)
                        except Exception:
                            continue
                        end_raw = row.get("Hasta")
                        try:
                            end = int(end_raw) if end_raw and str(end_raw).strip() else None
                        except Exception:
                            end = None
                        education.append(Education(
                            institution=str(row["Institución"]),
                            degree=str(row["Título"]),
                            field=str(row.get("Área") or ""),
                            start_year=start,
                            end_year=end,
                            completed=bool(row.get("Completado", True)),
                        ))

                    languages_dict = {}
                    for chunk in languages_text.split(","):
                        if ":" in chunk:
                            k, v = chunk.split(":", 1)
                            languages_dict[k.strip()] = v.strip()

                    new_profile = UserProfile(
                        full_name=full_name,
                        email=email,
                        phone=phone,
                        location=location,
                        linkedin_url=linkedin or None,
                        portfolio_url=portfolio or None,
                        headline=headline,
                        summary=summary,
                        experience_level=ExperienceLevel(experience_level),
                        work_experience=work_experience,
                        education=education,
                        hard_skills=[s.strip() for s in hard_skills.split(",") if s.strip()],
                        soft_skills=[s.strip() for s in soft_skills.split(",") if s.strip()],
                        languages=languages_dict,
                        target_roles=[r.strip() for r in target_roles.split(",") if r.strip()],
                        target_industries=[i.strip() for i in target_industries.split(",") if i.strip()],
                        min_salary=int(min_salary) if min_salary else None,
                        preferred_modality=JobModality(preferred_modality),
                        exclude_companies=[c.strip() for c in exclude_companies.split(",") if c.strip()],
                    )

                    profile_manager.save(new_profile, profile_name)
                    st.session_state.selected_profile = profile_name
                    st.success(f"Perfil '{profile_name}' guardado ✓")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error guardando el perfil: {e}")

    # ── Tab 3: Importar CV ────────────────────────────────────────────────────
    with tab_import:
        st.markdown("Subí tu CV en PDF y la IA va a extraer todos los campos automáticamente.")
        uploaded = st.file_uploader("Archivo PDF", type=["pdf"])
        new_profile_name = st.text_input(
            "Nombre para este perfil",
            value=st.session_state.get("selected_profile") or "default",
        )
        improve_with_ai = st.checkbox("Mejorar/completar con IA después de extraer", value=True)

        if uploaded and st.button("🔍 Extraer perfil del CV", type="primary"):
            with st.spinner("Extrayendo datos del CV con IA..."):
                try:
                    tmp_dir = Path(tempfile.gettempdir())
                    tmp_pdf = tmp_dir / f"jobagent_cv_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    tmp_pdf.write_bytes(uploaded.getvalue())

                    extracted = profile_manager.extract_from_pdf(str(tmp_pdf))
                    if improve_with_ai:
                        extracted = profile_manager.complete_profile_with_ai(extracted)
                    profile_manager.save(extracted, new_profile_name)
                    st.session_state.selected_profile = new_profile_name
                    st.success(f"Perfil extraído y guardado como '{new_profile_name}' ✓")
                    st.markdown(f"**Nombre:** {extracted.full_name}")
                    st.markdown(f"**Roles inferidos:** {', '.join(extracted.target_roles)}")
                    st.markdown(f"**Skills:** {', '.join(extracted.hard_skills[:10])}")
                    st.info("Andá a la pestaña 'Editar' para revisar y ajustar.")
                except Exception as e:
                    st.error(f"Error procesando el CV: {e}")


# ─── Nueva Búsqueda ───────────────────────────────────────────────────────────

elif page == "⚙️ Nueva Búsqueda":
    st.title("⚙️ Nueva Búsqueda")

    profile = _current_profile()
    if not profile:
        st.error("No hay perfil activo. Creá uno desde la sección 'Mi Perfil'.")
        st.stop()

    st.markdown(f"Buscando para: **{profile.full_name}** ({profile.headline})")
    st.markdown("---")

    # Cargar última config si existe
    last_config_path = Path("data/last_search_config.json")
    last = {}
    if last_config_path.exists():
        try:
            last = json.loads(last_config_path.read_text(encoding="utf-8"))
        except Exception:
            last = {}

    with st.form("search_config"):
        keywords_default = ", ".join(last.get("keywords") or profile.target_roles[:3])
        keywords = st.text_input("Keywords (separadas por coma)", value=keywords_default)
        location = st.text_input("Ubicación", value=last.get("location", "Argentina"))
        portals = st.multiselect(
            "Portales",
            [p.value for p in Portal],
            default=last.get("portals") or ["computrabajo"],
        )
        col_a, col_b = st.columns(2)
        min_score = col_a.slider("Score mínimo", 0.0, 1.0, float(last.get("min_relevance_score", 0.65)), 0.05)
        max_results = col_b.number_input(
            "Máximo de resultados por portal",
            5, 100,
            int(last.get("max_results_per_portal", 10)),
        )

        st.caption("La búsqueda nunca aplica automáticamente desde el dashboard. Todo queda como 'pendiente' para que puedas revisar y aplicar manualmente.")

        submitted = st.form_submit_button("🚀 Iniciar búsqueda", type="primary")

    if submitted:
        if not portals:
            st.error("Tenés que elegir al menos un portal.")
            st.stop()

        # Guardar config para la próxima
        config_data = {
            "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
            "location": location,
            "portals": portals,
            "min_relevance_score": min_score,
            "max_results_per_portal": int(max_results),
            "auto_apply": False,
        }
        last_config_path.write_text(json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8")

        config = SearchConfig(
            keywords=config_data["keywords"],
            location=config_data["location"],
            portals=[Portal(p) for p in config_data["portals"]],
            min_relevance_score=config_data["min_relevance_score"],
            max_results_per_portal=config_data["max_results_per_portal"],
            auto_apply=False,
        )

        st.session_state.search_log = []
        log_placeholder = st.empty()

        def _on_progress(msg: str):
            st.session_state.search_log.append(msg)

        with st.status("Buscando vacantes...", expanded=True) as status:
            try:
                applications, log = run_search(profile, config, on_progress=_on_progress)
                for line in log:
                    st.write(f"• {line}")
                status.update(label=f"Búsqueda completa: {len(applications)} aplicaciones preparadas", state="complete")
                st.session_state.last_search_summary = {
                    "applications": len(applications),
                    "log": log,
                    "ts": datetime.now().isoformat(),
                }
            except Exception as e:
                status.update(label=f"Error: {e}", state="error")
                st.exception(e)

        if st.session_state.last_search_summary:
            st.success(f"✓ Listo. {st.session_state.last_search_summary['applications']} vacantes guardadas como pendientes.")
            st.markdown("Andá a **📋 Aplicaciones** para revisar y aplicar.")


# ─── Estadísticas ─────────────────────────────────────────────────────────────

elif page == "📈 Estadísticas":
    st.title("📈 Estadísticas")

    applications = tracker.get_applications()
    jobs = tracker.get_jobs(min_score=0.0, limit=500)

    if not jobs and not applications:
        st.info("Todavía no hay datos suficientes. Iniciá una búsqueda primero.")
        st.stop()

    # KPIs arriba
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Vacantes scrapeadas", len(jobs))
    col2.metric("Vacantes con score ≥ 0.65", sum(1 for j in jobs if (j.relevance_score or 0) >= 0.65))
    col3.metric("Aplicaciones totales", len(applications))
    col4.metric(
        "Aplicadas (estado)",
        sum(1 for a in applications if a["status"] == "aplicada"),
    )

    st.markdown("---")

    # Histograma de scores
    st.subheader("Distribución de scores de relevancia")
    if jobs:
        score_df = pd.DataFrame([
            {"score": (j.relevance_score or 0), "portal": j.portal.value}
            for j in jobs
        ])
        fig_hist = px.histogram(
            score_df, x="score", nbins=20, color="portal",
            labels={"score": "Score de relevancia", "count": "Vacantes"},
        )
        fig_hist.update_layout(bargap=0.05, height=350)
        st.plotly_chart(fig_hist, use_container_width=True)

    # Por estado y por portal
    col_status, col_portal = st.columns(2)

    with col_status:
        st.subheader("Aplicaciones por estado")
        if applications:
            status_counts = pd.DataFrame(applications)["status"].value_counts().reset_index()
            status_counts.columns = ["Estado", "Cantidad"]
            fig_status = px.pie(status_counts, names="Estado", values="Cantidad", hole=0.4)
            fig_status.update_layout(height=350)
            st.plotly_chart(fig_status, use_container_width=True)

    with col_portal:
        st.subheader("Aplicaciones por portal")
        if applications:
            portal_counts = pd.DataFrame(applications)["portal"].value_counts().reset_index()
            portal_counts.columns = ["Portal", "Cantidad"]
            fig_portal = px.bar(portal_counts, x="Portal", y="Cantidad", color="Portal")
            fig_portal.update_layout(height=350, showlegend=False)
            st.plotly_chart(fig_portal, use_container_width=True)

    # Timeline
    st.subheader("Aplicaciones por día")
    if applications:
        df_t = pd.DataFrame(applications)
        df_t["created_at"] = pd.to_datetime(df_t["created_at"])
        df_t["fecha"] = df_t["created_at"].dt.date
        timeline = df_t.groupby(["fecha", "status"]).size().reset_index(name="cantidad")
        fig_time = px.bar(
            timeline, x="fecha", y="cantidad", color="status",
            labels={"fecha": "Día", "cantidad": "Aplicaciones"},
        )
        fig_time.update_layout(height=350)
        st.plotly_chart(fig_time, use_container_width=True)

    # Embudo
    st.subheader("Embudo de conversión")
    if jobs:
        total_scraped = len(jobs)
        relevant_065 = sum(1 for j in jobs if (j.relevance_score or 0) >= 0.65)
        relevant_080 = sum(1 for j in jobs if (j.relevance_score or 0) >= 0.80)
        total_apps = len(applications)
        applied = sum(1 for a in applications if a["status"] == "aplicada")
        interviews = sum(1 for a in applications if a["status"] == "entrevista")
        offers = sum(1 for a in applications if a["status"] == "oferta")

        funnel_df = pd.DataFrame({
            "Etapa": [
                "1. Scrapeadas",
                "2. Score ≥ 0.65",
                "3. Score ≥ 0.80",
                "4. En tracker",
                "5. Aplicadas",
                "6. Entrevistas",
                "7. Ofertas",
            ],
            "Cantidad": [total_scraped, relevant_065, relevant_080, total_apps, applied, interviews, offers],
        })
        fig_funnel = px.funnel(funnel_df, x="Cantidad", y="Etapa")
        fig_funnel.update_layout(height=400)
        st.plotly_chart(fig_funnel, use_container_width=True)
