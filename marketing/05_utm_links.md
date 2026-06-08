# Links UTM listos para copiar y pegar

Cada link tiene parámetros UTM que se capturan automáticamente cuando el usuario llega al landing. Después podés ver de dónde vinieron en `/admin/metrics`.

**URL base:** `https://jobagent-latam.onrender.com`

⚠️ **NO modifiques los parámetros UTM** — están coordinados con el tracking del backend.

---

## 📘 Reddit

### r/devsarg
```
https://jobagent-latam.onrender.com/?utm_source=reddit&utm_medium=post&utm_campaign=devsarg_launch
```

### r/Argentina
```
https://jobagent-latam.onrender.com/?utm_source=reddit&utm_medium=post&utm_campaign=argentina_launch
```

### r/RecursosHumanos
```
https://jobagent-latam.onrender.com/?utm_source=reddit&utm_medium=post&utm_campaign=rrhh_launch
```

### r/Trabajo_Argentina
```
https://jobagent-latam.onrender.com/?utm_source=reddit&utm_medium=post&utm_campaign=trabajo_ar_launch
```

---

## 💼 LinkedIn

### Post personal (storytelling)
```
https://jobagent-latam.onrender.com/?utm_source=linkedin&utm_medium=post&utm_campaign=personal_launch
```

### Post en grupos de LinkedIn (bootcamps, comunidades)
```
https://jobagent-latam.onrender.com/?utm_source=linkedin&utm_medium=group&utm_campaign=bootcamp_launch
```

### Mensajes directos en LinkedIn (1-on-1)
```
https://jobagent-latam.onrender.com/?utm_source=linkedin&utm_medium=dm&utm_campaign=outreach
```

---

## 🐦 Twitter / X

### Hilo principal de lanzamiento
```
https://jobagent-latam.onrender.com/?utm_source=twitter&utm_medium=thread&utm_campaign=launch
```

### Tweets sueltos / engagement orgánico
```
https://jobagent-latam.onrender.com/?utm_source=twitter&utm_medium=tweet&utm_campaign=organic
```

### Bio link en perfil
```
https://jobagent-latam.onrender.com/?utm_source=twitter&utm_medium=bio&utm_campaign=permanent
```

---

## 💬 Discord / Slack

### Servidores tech (devs.ar, Frontend Cafe, QA Latam)
```
https://jobagent-latam.onrender.com/?utm_source=discord&utm_medium=tech&utm_campaign=launch
```

### Bootcamps (Henry, Coderhouse, Soy Henry)
```
https://jobagent-latam.onrender.com/?utm_source=discord&utm_medium=bootcamp&utm_campaign=launch
```

---

## 📱 WhatsApp / Telegram

### Grupos generalistas (Empleos Argentina, etc.)
```
https://jobagent-latam.onrender.com/?utm_source=whatsapp&utm_medium=group&utm_campaign=launch
```

### Grupos IT específicos
```
https://jobagent-latam.onrender.com/?utm_source=whatsapp&utm_medium=group_tech&utm_campaign=launch
```

### Telegram channels
```
https://jobagent-latam.onrender.com/?utm_source=telegram&utm_medium=channel&utm_campaign=launch
```

---

## 📘 Facebook

### Grupos "Trabajos Argentina"
```
https://jobagent-latam.onrender.com/?utm_source=facebook&utm_medium=group&utm_campaign=launch
```

### Marketplace (si decidís usarlo)
```
https://jobagent-latam.onrender.com/?utm_source=facebook&utm_medium=marketplace&utm_campaign=launch
```

---

## 📨 Email outreach

### Cold email a contactos
```
https://jobagent-latam.onrender.com/?utm_source=email&utm_medium=cold&utm_campaign=outreach
```

### Newsletter (a futuro)
```
https://jobagent-latam.onrender.com/?utm_source=email&utm_medium=newsletter&utm_campaign=monthly
```

---

## 🤝 Referidos / Word of mouth

### Link para compartir entre usuarios
```
https://jobagent-latam.onrender.com/?utm_source=referral&utm_medium=user_share&utm_campaign=organic
```

---

## 🎯 Convención de UTMs (para crear nuevos)

| Param | Qué representa | Ejemplos |
|-------|---------------|----------|
| `utm_source` | De dónde viene (plataforma) | `reddit`, `linkedin`, `twitter`, `discord`, `whatsapp`, `email`, `facebook` |
| `utm_medium` | Formato/canal específico | `post`, `thread`, `group`, `dm`, `tweet`, `bio`, `email`, `cold` |
| `utm_campaign` | Campaña/momento | `devsarg_launch`, `launch`, `outreach`, `monthly`, `referral` |

### Reglas
1. **Todo en minúsculas, sin tildes ni espacios** (usar `_` para separar)
2. **Mantener consistencia**: si una vez usaste `reddit_devsarg` no uses `devsarg_reddit` después
3. **Source siempre es la plataforma**, no el canal específico dentro
4. **Campaign sirve para agrupar** posts del mismo lanzamiento

---

## 📊 Cómo medir resultados

Una vez que postees, abrí `/admin/metrics?days=7` y mirá:

1. **Tabla "Origen de registros (UTM)"** → cuántos usuarios trajo cada canal
2. **Eventos** → ver `signup_completed` por día
3. **Funnel de conversión** → cuántos llegaron a "Primera búsqueda" y "Es Pro"

### Decisiones según los datos

- Si **Reddit > LinkedIn > Twitter** en registros → doble down en Reddit, postear en más subreddits
- Si **LinkedIn > Reddit pero todos van directo a "Es Pro"** → LinkedIn trae usuarios de mayor calidad, invertir más ahí
- Si **alta tasa de signup pero baja conversión a "Primera búsqueda"** → problema en el onboarding
- Si **alta primera búsqueda pero baja conversión a Pro** → el producto no convence o el pricing es alto
