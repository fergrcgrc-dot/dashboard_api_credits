"""Dashboard de crédito de APIs.

Un único proceso, sin dependencias: sirve la página y un endpoint JSON que
pregunta a cada proveedor por saldo y gasto. Las claves se leen del entorno
(o de un fichero .env junto a este script) y nunca salen hacia el navegador.

    python server.py            # http://127.0.0.1:8787
"""

from __future__ import annotations

import datetime as dt
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


def openai(clave: str) -> dict:
    p = base("openai", "OpenAI", "https://platform.openai.com/settings/organization/billing/overview")
    cab = {"Authorization": f"Bearer {clave}"}
    inicio = int(dt.datetime.fromisoformat(ultimos_dias()[0] + "T00:00:00+00:00").timestamp())
    consulta = urllib.parse.urlencode(
        {"start_time": inicio, "bucket_width": "1d", "limit": DIAS + 1, "group_by": "line_item"}
    )
    costes = pedir(f"https://api.openai.com/v1/organization/costs?{consulta}", cab)
    por_dia: dict[str, float] = {}
    por_linea: dict[str, float] = {}
    for cubo in costes.get("data", []):
        dia = dt.datetime.fromtimestamp(cubo["start_time"], dt.timezone.utc).date().isoformat()
        for r in cubo.get("results", []):
            usd = float((r.get("amount") or {}).get("value") or 0)
            por_dia[dia] = por_dia.get(dia, 0.0) + usd
            linea = r.get("line_item") or "sin detalle"
            por_linea[linea] = por_linea.get(linea, 0.0) + usd
    p["serie"] = serie_completa(por_dia)
    p["gasto_30d"] = round(sum(x["usd"] for x in p["serie"]), 4)
    p["desglose"] = [
        {"nombre": k, "cantidad": None, "unidad": None, "usd": round(v, 4)}
        for k, v in sorted(por_linea.items(), key=lambda kv: -kv[1])
    ]
    p["notas"].append("OpenAI no publica el saldo de prepago por API: solo se ve en su panel.")
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
        datos = {
            "actualizado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "dias": DIAS,
            "umbral_saldo_bajo": float(os.environ.get("UMBRAL_SALDO_BAJO", "5")),
            "proveedores": proveedores,
        }
        _cache.update(cuando=time.time(), datos=datos)
        return datos


# ------------------------------------------------------------------------ http


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
        if ruta.path == "/":
            self._enviar(200, "text/html; charset=utf-8", (RAIZ / "static" / "index.html").read_bytes())
        elif ruta.path == "/api/resumen":
            forzar = "forzar=1" in ruta.query
            cuerpo = json.dumps(resumen(forzar), ensure_ascii=False).encode("utf-8")
            self._enviar(200, "application/json; charset=utf-8", cuerpo)
        else:
            self._enviar(404, "text/plain; charset=utf-8", b"No existe")

    def log_message(self, *args) -> None:  # silencio en consola
        pass


if __name__ == "__main__":
    cargar_env()
    puerto = int(os.environ.get("PUERTO", "8787"))
    # Solo escucha en local: la página enseña saldos y no lleva contraseña.
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    print(f"Dashboard de crédito de APIs en http://127.0.0.1:{puerto}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
