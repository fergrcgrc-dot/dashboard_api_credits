# Dashboard de crédito de APIs

Una página local que responde a tres preguntas: cuánto saldo queda, cuánto se ha gastado en los últimos 30 días y qué proveedor se va a quedar sin crédito antes.

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
- Escucha solo en `127.0.0.1`. La página no lleva contraseña, así que no la expongas a la red tal cual.
- `static/index.html` es toda la interfaz. Las reglas visuales están en `DESIGN.md`.

## Añadir un proveedor

Escribe una función en `server.py` que devuelva el diccionario de `base()` relleno y añádela a `PROVEEDORES` con el nombre de su variable de entorno. La página lo pinta sin tocar nada más.
