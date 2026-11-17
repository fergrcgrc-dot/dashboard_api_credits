"""Dashboard de crédito de APIs.

Un único proceso, sin dependencias: sirve la página y un endpoint JSON que
pregunta a cada proveedor por saldo y gasto. Las claves se leen del entorno
(o de un fichero .env junto a este script) y nunca salen hacia el navegador.

    python server.py            # http://127.0.0.1:8787

En local escucha solo en 127.0.0.1 y no pide contraseña. Desplegado (cuando el
alojamiento define PORT, o con HOST=0.0.0.0) exige DASHBOARD_PASSWORD.
"""

from __future__ import annotations

import base64
import datetime as dt
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DIAS = 30
CACHE_SEGUNDOS = 60


def dir_datos() -> Path:
    """Carpeta persistente: DATA_DIR, el volumen de Railway o ./data."""
    return Path(os.environ.get("DATA_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or RAIZ / "data")


_cerrojo_saldos = threading.Lock()


def leer_saldos() -> dict:
    try:
        return json.loads((dir_datos() / "saldos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_saldo(id_: str, saldo: float, base_dia: float) -> None:
    """Anota el saldo de hoy. base_dia es lo que OpenAI ya llevaba facturado hoy, para no restarlo después."""
    ahora = dt.datetime.now(dt.timezone.utc)
    with _cerrojo_saldos:
        datos = leer_saldos()
        datos[id_] = {"saldo": round(saldo, 4), "fecha": ahora.date().isoformat(),
                      "anotado": ahora.isoformat(timespec="seconds"), "base_dia": round(base_dia, 6)}
        carpeta = dir_datos()
        carpeta.mkdir(parents=True, exist_ok=True)
        tmp = carpeta / "saldos.json.tmp"
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(carpeta / "saldos.json")


def cargar_env() -> None:
    """Lee .env sin pisar lo que ya venga del entorno."""
    ruta = RAIZ / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip("\"'"))


def pedir(url: str, cabeceras: dict[str, str]) -> dict:
    peticion = urllib.request.Request(url, headers={"Accept": "application/json", **cabeceras})
    try:
        with urllib.request.urlopen(peticion, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"HTTP {e.code} en {urllib.parse.urlsplit(url).netloc}: {cuerpo}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Sin conexión con {urllib.parse.urlsplit(url).netloc}: {e.reason}") from None


def ultimos_dias() -> list[str]:
    hoy = dt.datetime.now(dt.timezone.utc).date()
    return [(hoy - dt.timedelta(days=n)).isoformat() for n in range(DIAS - 1, -1, -1)]


def serie_completa(por_dia: dict[str, float]) -> list[dict]:
    return [{"dia": d, "usd": round(por_dia.get(d, 0.0), 4)} for d in ultimos_dias()]


def euro(x: float) -> str:
    """Dos decimales con coma, como el resto de la página."""
    return f"{x:.2f}".replace(".", ",")


def base(id_: str, nombre: str, panel: str) -> dict:
    return {
        "id": id_, "nombre": nombre, "panel": panel, "estado": "ok", "error": None,
        "saldo": None, "limite": None, "gastado_limite": None,
        "gasto_30d": None, "serie": None, "desglose": [], "notas": [],
    }


# ------------------------------------------------------------------ proveedores


def openrouter(clave: str) -> dict:
    p = base("openrouter", "OpenRouter", "https://openrouter.ai/settings/credits")
    cab = {"Authorization": f"Bearer {clave}"}
    creditos = pedir("https://openrouter.ai/api/v1/credits", cab)["data"]
    p["saldo"] = round(creditos["total_credits"] - creditos["total_usage"], 4)
    p["notas"].append(
        f"Comprado {euro(creditos['total_credits'])} $ · consumido {euro(creditos['total_usage'])} $ desde el alta."
    )
    llave = pedir("https://openrouter.ai/api/v1/key", cab)["data"]
    if llave.get("limit") is not None:
        p["limite"] = llave["limit"]
        p["gastado_limite"] = round(llave["limit"] - (llave.get("limit_remaining") or 0), 4)
    try:
        actividad = pedir("https://openrouter.ai/api/v1/activity", cab)["data"]
    except RuntimeError:
        p["notas"].append("El gasto por día necesita una clave de gestión (management key); esta no lo es.")
        return p
    por_dia: dict[str, float] = {}
    por_modelo: dict[str, dict] = {}
    for fila in actividad:
        dia = str(fila.get("date", ""))[:10]
        usd = float(fila.get("usage") or 0)
        por_dia[dia] = por_dia.get(dia, 0.0) + usd
        m = por_modelo.setdefault(fila.get("model", "?"), {"usd": 0.0, "n": 0})
        m["usd"] += usd
        m["n"] += int(fila.get("requests") or 0)
    p["serie"] = serie_completa(por_dia)
    p["gasto_30d"] = round(sum(x["usd"] for x in p["serie"]), 4)
    p["desglose"] = [
        {"nombre": k, "cantidad": v["n"], "unidad": "peticiones", "usd": round(v["usd"], 4)}
        for k, v in sorted(por_modelo.items(), key=lambda kv: -kv[1]["usd"])
    ]
    return p


def fal(clave: str) -> dict:
    p = base("fal", "fal.ai", "https://fal.ai/dashboard/billing")
    cab = {"Authorization": f"Key {clave}"}
    cuenta = pedir("https://api.fal.ai/v1/account/billing?expand=credits", cab)
    p["saldo"] = (cuenta.get("credits") or {}).get("current_balance")
    inicio = ultimos_dias()[0] + "T00:00:00Z"
    consulta = urllib.parse.urlencode({"start": inicio, "timeframe": "day", "expand": "time_series,summary"})
    uso = pedir(f"https://api.fal.ai/v1/models/usage?{consulta}", cab)
    por_dia = {
        b["bucket"][:10]: sum(float(r.get("cost") or 0) for r in b.get("results", []))
        for b in uso.get("time_series", [])
    }
    p["serie"] = serie_completa(por_dia)
    p["gasto_30d"] = round(sum(x["usd"] for x in p["serie"]), 4)
    p["desglose"] = sorted(
        (
            {"nombre": r["endpoint_id"], "cantidad": r.get("quantity"), "unidad": r.get("unit"),
             "usd": round(float(r.get("cost") or 0), 4)}
            for r in uso.get("summary", [])
        ),
        key=lambda r: -r["usd"],
    )
    if uso.get("has_more"):
        p["notas"].append("Hay más filas de uso de las que devuelve una página; el total puede quedarse corto.")
    return p


def costes_openai(clave: str, desde: str) -> list[tuple[str, str, float]]:
    """Filas (día, concepto, usd) desde el día indicado (YYYY-MM-DD, UTC) hasta hoy."""
    cab = {"Authorization": f"Bearer {clave}"}
    inicio = int(dt.datetime.fromisoformat(desde + "T00:00:00+00:00").timestamp())
    dias = (dt.datetime.now(dt.timezone.utc).date() - dt.date.fromisoformat(desde)).days + 1
    consulta = urllib.parse.urlencode(
        {"start_time": inicio, "bucket_width": "1d", "limit": max(1, min(dias, 180)), "group_by": "line_item"}
    )
    costes = pedir(f"https://api.openai.com/v1/organization/costs?{consulta}", cab)
    filas = []
    for cubo in costes.get("data", []):
        dia = dt.datetime.fromtimestamp(cubo["start_time"], dt.timezone.utc).date().isoformat()
        for r in cubo.get("results", []):
            filas.append((dia, r.get("line_item") or "sin detalle", float((r.get("amount") or {}).get("value") or 0)))
    return filas


def openai(clave: str) -> dict:
    p = base("openai", "OpenAI", "https://platform.openai.com/settings/organization/billing/overview")
    manual = leer_saldos().get("openai")
    primero = ultimos_dias()[0]
    filas = costes_openai(clave, min(primero, manual["fecha"]) if manual else primero)
    por_dia: dict[str, float] = {}
    por_linea: dict[str, float] = {}
    for dia, linea, usd in filas:
        por_dia[dia] = por_dia.get(dia, 0.0) + usd
        if dia >= primero:
            por_linea[linea] = por_linea.get(linea, 0.0) + usd
    p["serie"] = serie_completa(por_dia)
    p["gasto_30d"] = round(sum(x["usd"] for x in p["serie"]), 4)
    p["desglose"] = [
        {"nombre": k, "cantidad": None, "unidad": None, "usd": round(v, 4)}
        for k, v in sorted(por_linea.items(), key=lambda kv: -kv[1])
    ]
    if manual:
        gastado = max(0.0, sum(v for d, v in por_dia.items() if d >= manual["fecha"]) - manual.get("base_dia", 0.0))
        p["saldo"] = round(manual["saldo"] - gastado, 4)
        p["manual"] = {"anotado": manual["saldo"], "fecha": manual["fecha"], "gastado_desde": round(gastado, 4)}
    else:
        p["notas"].append("OpenAI no publica el saldo de prepago por API: anótalo a mano y desde ahí se resta el consumo.")
    return p


def anthropic() -> dict:
    p = base("anthropic", "Anthropic", "https://console.anthropic.com/settings/billing")
    p["estado"] = "manual"
    manual = leer_saldos().get("anthropic")
    if manual:
        p["saldo"] = manual["saldo"]
        p["manual"] = {"anotado": manual["saldo"], "fecha": manual["fecha"], "gastado_desde": 0.0}
    p["notas"].append("Anthropic no ofrece API de consumo para esta cuenta: el saldo no se resta solo, hay que actualizarlo a mano.")
    return p


PROVEEDORES = [
    ("OPENROUTER_API_KEY", "OpenRouter", "openrouter", openrouter),
    ("FAL_ADMIN_KEY", "fal.ai", "fal", fal),
    ("OPENAI_ADMIN_KEY", "OpenAI", "openai", openai),
]


def consultar(variable: str, nombre: str, id_: str, funcion) -> dict:
    clave = os.environ.get(variable, "").strip()
    if not clave:
        p = base(id_, nombre, "")
        p["estado"] = "sin_clave"
        p["error"] = f"Falta {variable} en .env"
        return p
    try:
        return funcion(clave)
    except Exception as e:  # un proveedor caído no tumba a los demás
        p = base(id_, nombre, "")
        p["estado"] = "error"
        p["error"] = str(e)
        return p


_cache: dict = {"cuando": 0.0, "datos": None}
_cerrojo = threading.Lock()


def resumen(forzar: bool = False) -> dict:
    with _cerrojo:
        if not forzar and _cache["datos"] and time.time() - _cache["cuando"] < CACHE_SEGUNDOS:
            return _cache["datos"]
        with ThreadPoolExecutor(max_workers=len(PROVEEDORES)) as ex:
            proveedores = list(ex.map(lambda a: consultar(*a), PROVEEDORES))
        proveedores.append(anthropic())
        datos = {
            "actualizado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "dias": DIAS,
            "umbral_saldo_bajo": float(os.environ.get("UMBRAL_SALDO_BAJO", "5")),
            "proveedores": proveedores,
        }
        _cache.update(cuando=time.time(), datos=datos)
        return datos


# ------------------------------------------------------------------------ http


def anfitrion() -> str:
    """Abierto a la red solo si lo pide el alojamiento (PORT) o HOST."""
    return os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")


def autorizado(cabecera: str | None) -> bool:
    """En local no hay contraseña. Abierto a la red, usuario y contraseña siempre."""
    if anfitrion() in ("127.0.0.1", "localhost"):
        return True
    clave = os.environ.get("DASHBOARD_PASSWORD", "")
    if not clave or not cabecera or not cabecera.startswith("Basic "):
        return False
    try:
        usuario, _, dada = base64.b64decode(cabecera[6:]).decode("utf-8").partition(":")
    except Exception:
        return False
    esperado = os.environ.get("DASHBOARD_USUARIO", "fernando")
    return hmac.compare_digest(usuario.encode(), esperado.encode()) and hmac.compare_digest(dada.encode(), clave.encode())


class Manejador(BaseHTTPRequestHandler):
    def _enviar(self, codigo: int, tipo: str, cuerpo: bytes) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self) -> None:  # noqa: N802
        ruta = urllib.parse.urlsplit(self.path)
        if ruta.path == "/salud":  # para la comprobación del alojamiento; no enseña datos
            return self._enviar(200, "text/plain; charset=utf-8", b"ok")
        if not autorizado(self.headers.get("Authorization")):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Credito de APIs"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if ruta.path == "/":
            self._enviar(200, "text/html; charset=utf-8", (RAIZ / "static" / "index.html").read_bytes())
        elif ruta.path == "/api/resumen":
            forzar = "forzar=1" in ruta.query
            cuerpo = json.dumps(resumen(forzar), ensure_ascii=False).encode("utf-8")
            self._enviar(200, "application/json; charset=utf-8", cuerpo)
        else:
            self._enviar(404, "text/plain; charset=utf-8", b"No existe")

    def do_POST(self) -> None:  # noqa: N802
        ruta = urllib.parse.urlsplit(self.path)
        if not autorizado(self.headers.get("Authorization")):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Credito de APIs"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if ruta.path != "/api/saldo":
            return self._json(404, {"error": "No existe"})
        origen = self.headers.get("Origin")  # un POST desde otra web no debe poder cambiar los saldos
        if origen and urllib.parse.urlsplit(origen).netloc != self.headers.get("Host"):
            return self._json(403, {"error": "Origen no permitido"})
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json(415, {"error": "Se esperaba JSON"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= 1000:
                raise ValueError
            datos = json.loads(self.rfile.read(n).decode("utf-8"))
            id_ = datos["proveedor"]
            saldo = float(datos["saldo"])
            if id_ not in ("openai", "anthropic") or not 0 <= saldo < 1e7:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            return self._json(400, {"error": "Datos no válidos"})
        base_dia = 0.0
        clave = os.environ.get("OPENAI_ADMIN_KEY", "").strip()
        if id_ == "openai" and clave:  # lo ya facturado hoy no cuenta como consumo posterior
            try:
                hoy = dt.datetime.now(dt.timezone.utc).date().isoformat()
                base_dia = sum(u for d, _, u in costes_openai(clave, hoy) if d == hoy)
            except Exception:
                pass
        try:
            guardar_saldo(id_, saldo, base_dia)
        except OSError as e:
            return self._json(500, {"error": f"No se pudo guardar en disco: {e.strerror or e}"})
        _cache["cuando"] = 0.0
        self._json(200, {"ok": True})

    def _json(self, codigo: int, datos: dict) -> None:
        self._enviar(codigo, "application/json; charset=utf-8", json.dumps(datos, ensure_ascii=False).encode("utf-8"))

    def log_message(self, *args) -> None:  # silencio en consola
        pass


if __name__ == "__main__":
    cargar_env()
    puerto = int(os.environ.get("PORT") or os.environ.get("PUERTO") or "8787")
    host = anfitrion()
    if host not in ("127.0.0.1", "localhost") and not os.environ.get("DASHBOARD_PASSWORD"):
        raise SystemExit("Falta DASHBOARD_PASSWORD: no se abre a la red una página con saldos sin contraseña.")
    servidor = ThreadingHTTPServer((host, puerto), Manejador)
    print(f"Dashboard de crédito de APIs en http://{host}:{puerto}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
