---
version: "beta"
name: "Crédito de APIs · Degradados"
description: "Panel de saldo y gasto de APIs, tema oscuro con degradado cian, magenta y naranja."
colors:
  fondo: "#0b0d2b"
  superficie: "rgba(255,255,255,0.045)"
  tinta: "#f5f5f9"
  acento-degradado: "linear-gradient(90deg, #38b6f0, #9b2e8a 55%, #f97316)"
  openai: "#2b9fe0"
  openrouter: "#e0620f"
  fal: "#c4479f"
  anthropic: "#7a83ee"
  error: "#f0646a"
rounded: { card: 16px, pill: 999px }
---
## Overview
Una sola pantalla para saber cuánto saldo queda, cuánto se gasta al día y cuántos días de autonomía hay.
Todo el estilo está en el `<style>` de `static/index.html`.

## Colors
- Fondo azul marino con dos brillos radiales (azul arriba a la derecha, violeta abajo a la izquierda).
- Tarjetas translúcidas con borde de 1px al 11% de blanco.
- Cada plataforma tiene un color fijo (cian, naranja, magenta, índigo) validado para fondo oscuro y daltonismo. El color nunca es la única señal: siempre hay leyenda y nombre.
- El degradado cian, magenta y naranja solo se usa en el botón principal, la pestaña activa y la palabra "gasto" del título.
- Errores en `#f0646a`, siempre con texto que explique el motivo.

## Components
- KPIs: saldo total, gasto a 7 y 30 días, autonomía estimada.
- Gráfico de gasto acumulado por plataforma (30 días) con cursor y detalle al pasar el ratón.
- Reparto del gasto en 7 o 30 días.
- Tarjeta por plataforma: saldo, gasto, autonomía y gasto diario. OpenAI y Anthropic llevan campo de saldo a mano (se guarda en el navegador).
- Tabla de desglose por modelo o concepto.
