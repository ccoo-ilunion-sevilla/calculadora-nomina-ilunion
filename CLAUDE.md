# Verificación de cuadrantes (Sección Sindical CCOO · Ilunion Seguridad Sevilla)

## Cuando el usuario sube un cuadrante `.xlsx` (plantilla de la empresa: hojas CUADRANTES y Leyenda de Turnos)

Es lo habitual: «te subo lo que me den y tú me devuelves los fallos en hojas como la de impresión anual».
No hay que explicar nada ni pedir pasos: ejecutar y entregar.

```
node herramientas/verificar_cuadrante.js <ruta.xlsx> --salida <carpeta en el scratchpad> [opciones]
```

Entregar al usuario con `SendUserFile`:
- `fallos_*.pdf`: una hoja de 2 caras por trabajador con fallos (cuadrante tipo «IMPRESIÓN C. ANUAL» con los días con fallo recuadrados; cara 2 con la lista de fallos, vacaciones concedidas y recuadro de comprobación para el trabajador).
- `incidencias_*.csv`: todas las incidencias, identificando a cada trabajador solo por nº de empleado.

Y un resumen corto en el chat: nº de trabajadores, errores/avisos, y los fallos más relevantes por regla.
Opciones útiles: `--todos` (hojas de todos), `--limite AAAA-MM-DD` y `--contacto "texto"` (se imprimen en el recuadro), `--semana acum`, `--fs horas`, `--banda aviso|no`, `--formacion no`.

Si la estructura no cuadra (faltan días, meses, calendario de otro año, festivos sin marcar) el script lo dice y no genera hojas: informar al usuario de eso primero.

## Reglas y criterios por defecto (los del Excel de referencia del usuario)
- Descanso entre jornadas ≥ 12 h (ET 34.3). 12–13 h solo informativo (Convenio Ilunion art. 56, excepción de trabajo a turnos).
- Descanso semanal: cada semana lun–dom con 36 h seguidas (ET 37.1). Opción acumulable 14 días.
- Un fin de semana libre al mes (sábado y domingo sin turno en la casilla).
- Jornada anual 1.782 h **de trabajo**: el crédito de vacaciones (5,23 h por día) y bajas NO cuenta. La suma de la columna «HORAS» de la empresa (≈1.946) sí lo incluye: no compararla con 1.782.
- Vacaciones 31 días naturales (Convenio Ilunion art. 61). Horquilla mensual 144–176 h (febrero 134–162). 96 días de descanso anual.
- La formación (código F) cuenta como turno por defecto (el Excel del usuario la trata como ausencia).
- No se auditan horas extra reales ni nocturnidad: requieren TC2/nómina.

## Privacidad (la empresa clasifica el cuadrante como documento interno)
- En la hoja PDF de cada trabajador va **solo su propio nombre y nº** (como en la hoja de la empresa). Ningún otro nombre.
- Listados, CSV, escritos y resúmenes en el chat: **solo nº de empleado**, nunca nombres (`--con-nombres` solo si el usuario lo pide).
- No poner el nombre del delegado en ninguna parte: el contacto de la hoja es opcional y solo lo que el usuario indique.
- No incluir logos ni marcas de la empresa; la hoja lleva la rotulación de la Sección Sindical.

## Reglas de trabajo
- **Nunca subir al repositorio** cuadrantes, PDF de hojas ni CSV de incidencias: llevan nombres de trabajadores y el repositorio es público. Dejarlos en el scratchpad.
- Cada incidencia es un indicio, no una resolución: decirlo al entregar.
- La herramienta web es `cuadrantes.html` (misma lógica, para usar en el navegador); el script la reutiliza.
- Responder en español, breve, sin relleno; marcar `[EDITABLE]` lo que falte.
