# Post Reddit — r/devsarg

**Subreddit:** r/devsarg
**Flair sugerido:** Proyecto / Recurso / Discusión
**Horario óptimo para postear:** martes a jueves, 10-13hs o 19-22hs (hora Argentina)

---

## OPCIÓN A (recomendada — historia + producto)

**Título:**
> Apliqué a 200+ vacantes en 4 meses sin respuesta. Me cansé y construí un bot que filtra Computrabajo/Bumeran/ZonaJobs por mí.

**Cuerpo:**

Buenas gente. Soy QA Analyst junior, hace 4 meses que estoy buscando laburo y vengo a contarles algo que arranqué medio por bronca y terminó siendo un proyecto que ya usan otros.

**El problema** (que probablemente conocen):

Buscar trabajo junior en Argentina es un trabajo full-time sin sueldo. Abrís Computrabajo, scrolleas 80 ofertas, 70 piden "5 años de experiencia" para un puesto junior, las otras 10 las querés aplicar y tenés que rellenar el mismo formulario por enésima vez. Bumeran te pide registrarte de nuevo. ZonaJobs idem. Al final del día aplicaste a 5 ofertas y te quedaste sin energía.

Hice la cuenta y en 4 meses apliqué a 200+ vacantes. Respuestas: como 3.

**Lo que armé:**

Un agente que:
1. Lee tu perfil (CV + skills + preferencias) una sola vez
2. Scrapea Computrabajo, Bumeran y ZonaJobs con tus keywords
3. Filtra por score de compatibilidad (usa Groq + Llama 3.3 para matchear el JD con tu perfil)
4. Te genera carta de presentación personalizada por cada oferta
5. Te muestra todo en un panel para que VOS decidas a qué aplicar

**Stack:**
- Backend: FastAPI + SQLite + Playwright (scrapers anti-detect)
- IA: Groq (Llama 3.3 70B) para matching y cartas
- Frontend: Jinja2 + Tailwind + Alpine.js (nada de SPAs gigantes, carga en 200ms)
- Deploy: Render + Turso (SQLite distribuida)

**Lo importante:** ya no aplica automático (lo cambié después de feedback). El usuario tiene el control. La herramienta busca, filtra y te ahorra las 4hs diarias de scrolleo.

**Lo pueden probar gratis:**
👉 https://jobagent-latam.onrender.com/?utm_source=reddit&utm_medium=post&utm_campaign=devsarg_launch

3 búsquedas gratis sin tarjeta. Después si les sirve hay plan de $14.990/mes (lo necesito para pagar el hosting + API de Groq).

**Lo que más necesito ahora es feedback técnico y de UX.** Si lo prueban y algo es confuso, está roto o falta, díganme acá o por DM. Estoy a full mejorándolo.

Gracias por leer. Cualquier consulta del stack o cómo armé los scrapers la respondo abajo.

---

## OPCIÓN B (más corta, si la A se siente muy larga)

**Título:**
> [Side project] Bot que scrapea Computrabajo/Bumeran/ZonaJobs y filtra ofertas según tu perfil — Feedback wanted

**Cuerpo:**

Soy QA junior, llevo 4 meses buscando laburo, apliqué a 200+ vacantes y obtuve 3 respuestas. Me harté y armé esto:

**VacantIA** — un agente que scrapea los 3 portales más grandes de Argentina, filtra por compatibilidad con tu CV usando IA (Groq + Llama 3.3) y te muestra solo las que valen la pena. También te genera carta de presentación personalizada.

Stack: FastAPI + Playwright + Jinja2/Tailwind. Deploy en Render.

Link: https://jobagent-latam.onrender.com/?utm_source=reddit&utm_medium=post&utm_campaign=devsarg_launch (3 búsquedas gratis, sin tarjeta).

Si lo prueban, **cuéntenme qué les pareció**. Estoy iterando rápido y todo el feedback me sirve.

---

## Notas para postear

### ✅ Qué hacer
- Postear como cuenta personal con historial real en Reddit (no cuenta nueva, te baneean)
- Si nunca posteaste en r/devsarg, primero participá 2-3 días en comentarios para no parecer cuenta zombie
- Responder TODOS los comentarios en las primeras 6 horas (esto sube el post en el algoritmo)
- Si alguien critica algo, agradecé y tomá nota — no defiendas
- Si alguien encuentra un bug, arreglalo MISMO día y respondé "ya está arreglado, gracias"

### ❌ Qué NO hacer
- Editar el título después (Reddit lo penaliza)
- Crosspostear a otros subs el mismo día
- Hablar en tercera persona como si fueras una marca
- Borrar comentarios negativos (engagement es engagement)

### Métricas para mirar
- Upvotes (objetivo: 50+ en 24hs)
- Comentarios (objetivo: 15+)
- Click-through al link (en Render dashboard → Metrics)
- Registros en las primeras 48hs (objetivo: 10+)
