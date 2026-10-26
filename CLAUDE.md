# Verificación de cuadrantes (Sección Sindical CCOO · Ilunion Seguridad Sevilla)

## Cuando el usuario sube un cuadrante `.xlsx` (plantilla de la empresa: hojas CUADRANTES y Leyenda de Turnos)

Es lo habitual: «te subo lo que me den y tú me devuelves los fallos en hojas como la de impresión anual».
No hay que explicar nada ni pedir pasos: ejecutar y entregar.

```
node herramientas/verificar_cuadrante.js <ruta.xlsx> --salida <carpeta en el scratchpad> [opciones]
```

Entregar al usuario con `SendUserFile`:
- `fallos_*.pdf`: una hoja de 2 caras por trabajador (todos) (cuadrante tipo «IMPRESIÓN C. ANUAL» con los días con fallo recuadrados; cara 2 con la lista de fallos, vacaciones concedidas y recuadro de comprobación para el trabajador).
- `incidencias_*.csv`: todas las incidencias, identificando a cada trabajador solo por nº de empleado.

Y un resumen corto en el chat: nº de trabajadores, errores/avisos, y los fallos más relevantes por regla.
Para enviar hojas **una a una** (no en lote): `--por-trabajador` genera `hojas_individuales/hoja_<nº>.pdf` (uno por trabajador, **de todos**, tengan o no fallos) y `--trabajador 12345,12346` solo los de esos nº. Entregar como `.zip`. Los ficheros individuales (hojas y calendarios) se nombran con **nombre y nº de empleado** (así el delegado sabe a quién enviar cada uno); cada PDF lleva únicamente el nombre de su trabajador.
Por defecto se generan las hojas de **todos** los trabajadores, incluidos los que no tienen fallos (cada trabajador debe comprobar sus vacaciones y demás); `--solo-fallos` las limita a quienes tienen fallos.
**Calendarios (.ics) para que el trabajador meta su previsión en el móvil**: `--calendarios` genera `calendarios/calendario_<nº>_<año>_<etapa>.ics` por trabajador (turnos con su hora, vacaciones/bajas como días completos, sin nombres dentro). `--etapa definitivo` para el cuadrante final; `--alarma 60` añade aviso antes de cada turno. Para sustituir la previsión por el definitivo: el trabajador **borra el calendario «Cuadrante AAAA · previsión» e importa el nuevo** (los identificadores son estables, pero importar encima no elimina los días que dejaron de ser turno).
**App «Mi cuadrante» (`micuadrante.html`)**: PWA estática y portátil (rutas relativas; se puede mover a cualquier alojamiento de ficheros). El trabajador abre un enlace personal por WhatsApp con sus turnos dentro del `#` de la dirección (no viaja a ningún servidor) y la app los guarda en su móvil. `--enlaces --base <URL de micuadrante.html> --tel <WhatsApp del delegado>` genera `enlaces_whatsapp.csv` y `mensajes_whatsapp.txt` (mensaje listo para pegar, con nombre y nº del destinatario solo en el encabezado). Con `--etapa definitivo` se generan los del cuadrante final: la app enseña al trabajador los cambios respecto a su previsión y le deja comprobar sus vacaciones pedidas frente a las concedidas.
**Actualizaciones por mes**: `--mes 3` (1–12) genera enlaces que llevan solo ese mes; la app los **fusiona** con lo que el trabajador ya tiene (conserva el resto del año y sus fallos, y le enseña los cambios del mes). Útil cuando llega un cuadrante mensual definitivo.
**La app permite al trabajador marcar sus días** (turnos propios, hora propia, lugar de trabajo, notas) sin necesidad de enlace; esas marcas se mantienen cuando llega una actualización y se comparan con el cuadrante oficial. No hay actualización automática: requeriría un servidor o publicar datos cifrados (decisión pendiente del delegado).
Opciones útiles: `--limite AAAA-MM-DD` y `--contacto "texto"` (se imprimen en el recuadro), `--semana acum`, `--fs horas`, `--banda aviso|no`, `--formacion no`.

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
- Listados, CSV, escritos y resúmenes en el chat: **solo nº de empleado**, nunca nombres (la única excepción son los nombres de los ficheros individuales, a petición del usuario) (`--con-nombres` solo si el usuario lo pide).
- No poner el nombre del delegado en ninguna parte: el contacto de la hoja es opcional y solo lo que el usuario indique.
- No incluir logos ni marcas de la empresa; la hoja lleva la rotulación de la Sección Sindical.

## Reglas de trabajo
- **Nunca subir al repositorio** cuadrantes, PDF de hojas ni CSV de incidencias: llevan nombres de trabajadores y el repositorio es público. Dejarlos en el scratchpad.
- Cada incidencia es un indicio, no una resolución: decirlo al entregar.
- La herramienta web es `cuadrantes.html` (misma lógica, para usar en el navegador); el script la reutiliza.
- Responder en español, breve, sin relleno; marcar `[EDITABLE]` lo que falte.
