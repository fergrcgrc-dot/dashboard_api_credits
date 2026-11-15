---
version: "alpha"
name: "Crédito de APIs · Barely-There"
description: "Panel local de saldo y gasto de APIs. Basado en la plantilla The Barely-There UI de designmd.app."
colors:
  primary: "#ffffff"
  secondary: "#000000"
  danger: "#b42318"
  primary-dark: "#0b0b0b"
  danger-dark: "#ff8a7a"
typography:
  display: { fontFamily: system-ui, fontSize: 3.5rem, fontWeight: 200 }
  h2: { fontFamily: system-ui, fontSize: 1.35rem, fontWeight: 300 }
  body-md: { fontFamily: system-ui, fontSize: 15px, fontWeight: 400 }
rounded: { none: 0px }
---
## Overview
Se abre para leer tres cifras y cerrarlo. La interfaz se aparta: lo único con peso visual son los números.
Todo el estilo está en el `<style>` de `static/index.html`.

## Colors
Tres colores y nada más: fondo, tinta y alerta.
- La jerarquía se hace con la opacidad de la tinta: 100% cifras y títulos, 78% texto, 56% rótulos y notas.
- Líneas al 12% y al 32% de la tinta.
- Alerta (`#b42318`, `#ff8a7a` en oscuro) solo para saldo bajo y proveedores caídos, siempre con texto que lo explique.
- Los gráficos van en tinta, sin color de serie.
- Tema oscuro automático con `prefers-color-scheme`.

## Typography
- Una sola familia: la del sistema.
- Cifras grandes en peso 200 con interletraje negativo; títulos en 300; texto en 400.
- Toda cifra con `tabular-nums` (`.num`).

## Layout
- Ancho máximo 1080px. Mucho aire entre secciones (72 a 88px).
- Cada proveedor: columna fija de 260px con saldo y notas, y a la derecha gasto y desglose. Una columna por debajo de 820px.

## Elevation & Depth
Sin sombras y sin degradados. Las secciones se separan con una línea de 1px.

## Shapes
Esquinas rectas en todo.

## Components
- Cifra de cabecera: rótulo, número, una línea de contexto que dice de qué proveedores sale.
- Medidor: pista de 2px con el tramo consumido en tinta y los dos valores escritos debajo.
- Gráfico de barras: una serie, barras con 2px de separación, tres marcas de fecha, detalle al pasar el ratón.
- Tabla de desglose: la barra fina de cada fila es proporcional a la fila más cara.
- Estado vacío: una frase entre dos líneas, sin iconos.

## Do's and Don'ts
- No tarjetas con fondo ni bordes redondeados.
- No iconos ni emoji.
- No un color por proveedor.
- No cifras sin decir a qué proveedores corresponden: si falta un dato, se escribe cuál.
- No botones rellenos: las acciones son texto subrayado.
