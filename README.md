# Dashboard de crédito de APIs

Una página que responde a tres preguntas: cuánto saldo queda, cuánto se ha gastado en los últimos 30 días y qué proveedor se va a quedar sin crédito antes.

Proveedores: OpenRouter, fal.ai y OpenAI.

## Arrancar

Necesita Python 3.9 o superior. No hay dependencias que instalar.

```bash
cp .env.example .env
```

Rellena las claves en `.env` y lanza el servidor:

```bash
python server.py
```

Abre http://127.0.0.1:8787.

## Acceder desde cualquier sitio (Railway)

El repo lleva `Dockerfile` y `railway.json`, así que Railway lo despliega tal cual:

1. En Railway: **New Project → Deploy from GitHub repo → `dashboard_api_credits`**.
2. En **Variables**, añade `OPENROUTER_API_KEY`, `FAL_ADMIN_KEY`, `OPENAI_ADMIN_KEY`, `DASHBOARD_USUARIO` y `DASHBOARD_PASSWORD`.
3. En **Settings → Networking**, pulsa **Generate Domain**. Esa es la dirección.

Fuera de tu ordenador la página pide usuario y contraseña, y el servidor se niega a arrancar si falta `DASHBOARD_PASSWORD`. Cada push a `main` se redespliega solo.

## Qué enseña cada proveedor

| Proveedor | Saldo | Gasto por día | Desglose |
|---|---|---|---|
| OpenRouter | Sí, más el límite de la clave | Solo con una management key | Por modelo, con management key |
| fal.ai | Sí | Sí | Por modelo, con cantidad y unidad |
| OpenAI | No: su API no lo publica | Sí | Por línea de factura |

Un proveedor sin clave o que no responde aparece marcado como tal y no afecta a los demás.

## Cómo funciona

- `server.py` sirve la página y `/api/resumen`, que consulta a los tres proveedores en paralelo y guarda la respuesta 60 segundos. El botón Actualizar salta esa caché.
- Las claves se quedan en el servidor: el navegador solo recibe cifras.
- En local escucha solo en `127.0.0.1`, sin contraseña. Desplegado (cuando existe `PORT`) escucha en todas las interfaces y exige usuario y contraseña.
- `static/index.html` es toda la interfaz (tema oscuro con degradados). Las reglas visuales están en `DESIGN.md`. OpenAI no publica su saldo y Anthropic no tiene API de saldo: se escriben a mano en la propia página y se guardan en el navegador.

## Añadir un proveedor

Escribe una función en `server.py` que devuelva el diccionario de `base()` relleno y añádela a `PROVEEDORES` con el nombre de su variable de entorno. La página lo pinta sin tocar nada más.

## Saldos de OpenAI y Anthropic (se guardan en el servidor)

OpenAI no publica su saldo y Anthropic no tiene API de consumo para cuentas individuales, así que el saldo se anota a mano en su tarjeta.

- **OpenAI:** desde que anotas el saldo, la página le resta automáticamente el consumo que devuelve la API de costes. Lo ya facturado ese mismo día no se resta. El coste de OpenAI tarda unas horas en reflejarse.
- **Anthropic:** no se puede restar solo; se actualiza a mano.
- Los saldos se guardan en `saldos.json`, dentro de `DATA_DIR`, del volumen de Railway (`RAILWAY_VOLUME_MOUNT_PATH`) o de `./data`, por este orden. **En Railway hay que añadir un volumen** (servicio → Volumes → mount path `/data`); sin él los saldos se pierden en cada despliegue.
