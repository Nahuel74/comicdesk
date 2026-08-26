# Deuda Técnica — Registro

> Deuda identificada durante el desarrollo. Pendiente de tratamiento.
> Una vez resuelto un item. Eliminarlo de esta lista.

## Formato

| ID  | Fecha | Hallazgo | Archivos | Tipo | Prioridad |
| --- | ----- | -------- | -------- | ---- | --------- |

**Editar a partir de esta línea**

----

## Pendientes

| ID    | Fecha      | Hallazgo                                                                                                                                                                      | Archivo                                                                               | Tipo          | Prioridad |
| ----- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ------------- | --------- |
| DEBT-001 | 2026-08-26 | `ScanWorker` duplica la implementación entre el panel de carpetas y la lista de cómics; el worker del panel no es utilizado y ambas variantes carecen de manejo de errores por archivo. | `cbl_maker/ui/folder_panel.py`, `cbl_maker/ui/comic_list_workers.py` | Arquitectura / resiliencia | Media |
| DEBT-002 | 2026-08-26 | Los workers de escaneo y enriquecimiento no convierten excepciones inesperadas de lectura/red en una señal de error; una excepción no controlada termina el hilo sin feedback confiable a la UI. | `cbl_maker/ui/folder_panel.py`, `cbl_maker/ui/comic_list_workers.py` | Manejo de errores | Alta |
| DEBT-003 | 2026-08-26 | `ValidateApiKeyWorker` no captura errores de red/API; una excepción inesperada termina el hilo sin emitir resultado y deja el diálogo en estado "Validating..." con el botón deshabilitado. | `cbl_maker/ui/config_dialog.py` | Manejo de errores / UX | Media |
| DEBT-004 | 2026-08-26 | `read_cbz_metadata` no maneja los errores de acceso al archivo CBZ; permisos insuficientes, rutas inexistentes o fallos de lectura pueden propagarse como excepciones no controladas. | `cbl_maker/services/cbz_reader.py` | Manejo de errores | Media |
| DEBT-005 | 2026-08-26 | `Config.save` no maneja errores de escritura; un fallo al persistir la configuración puede propagarse sin feedback claro ni recuperación para la UI. | `cbl_maker/config.py` | Manejo de errores / UX | Media |
| DEBT-006 | 2026-08-26 | `comicvine_api` no valida ni maneja JSON inválido o respuestas con una estructura inesperada; respuestas malformadas pueden causar excepciones no controladas durante el enriquecimiento. | `cbl_maker/services/comicvine_api.py` | Manejo de errores / resiliencia | Alta |
| DEBT-007 | 2026-08-26 | El lector CBZ analiza entrada XML potencialmente no confiable sin la protección equivalente de límites explícitos de tamaño, nodos y profundidad; `cbl_reader.py` ya incorpora estos límites en esta feature. | `cbl_maker/services/cbz_reader.py` | Seguridad / resiliencia | Alta |

### DEBT-007 — Tratamiento posterior

- **Ubicación:** `cbl_maker/services/cbz_reader.py`, en el punto donde se invoca `xml.etree.ElementTree` para analizar XML de entrada. `cbl_maker/services/cbl_reader.py` ya incorpora límites de tamaño, nodos y profundidad en esta feature.
- **Impacto:** Una entrada XML CBZ excesivamente grande, con demasiados nodos o muy profunda puede provocar consumo excesivo de memoria o CPU y degradar la disponibilidad de la aplicación.
- **Tratamiento posterior:** Incorporar en `cbl_maker/services/cbz_reader.py` una protección equivalente a la de `cbl_reader.py`, con límites explícitos de tamaño, nodos y profundidad, además de validación previa de la entrada.

### DEBT-001

- **Hallazgo:** En `cbl_maker/ui/folder_panel.py`, `ScanWorker` duplica implementación y no es utilizado.
- **Impacto:** La implementación duplicada aumenta el costo de mantenimiento y puede provocar comportamientos divergentes o correcciones aplicadas solo a una de las variantes.
- **Tratamiento posterior:** Eliminar o reutilizar la implementación no utilizada y consolidar el comportamiento del escaneo en un único worker compartido.

### DEBT-002

- **Hallazgo:** En `folder_panel.py`, los workers no convierten excepciones inesperadas en señal de error UI.
- **Impacto:** Una excepción no controlada puede terminar el hilo sin feedback confiable, dejando la interfaz en un estado inconsistente o sin informar al usuario del fallo.
- **Tratamiento posterior:** Capturar excepciones inesperadas en los workers, emitir una señal de error con un mensaje seguro y garantizar la restauración del estado de la UI.

### DEBT-003

- **Hallazgo:** En `config_dialog.py`, `ValidateApiKeyWorker` puede quedar en Validating ante errores de red/API.
- **Impacto:** El diálogo puede quedar bloqueado en estado de validación, con controles deshabilitados y sin permitir al usuario reintentar o corregir la configuración.
- **Tratamiento posterior:** Manejar errores de red/API, emitir siempre un resultado de validación o error y restablecer el estado interactivo del diálogo.

### DEBT-004

- **Hallazgo:** En `services/cbz_reader.py`, `read_cbz_metadata` no maneja acceso, rutas ni lectura.
- **Impacto:** Rutas inexistentes, permisos insuficientes o fallos de lectura pueden propagarse como excepciones no controladas y detener el procesamiento de cómics.
- **Tratamiento posterior:** Validar rutas y permisos, capturar errores de apertura/lectura y devolver un error controlado que pueda mostrar o registrar la capa superior.

### DEBT-005

- **Hallazgo:** En `config.py`, `Config.save` no maneja errores de escritura/recuperación UI.
- **Impacto:** Un fallo al persistir la configuración puede propagarse sin feedback claro, provocar pérdida de cambios y dejar la UI en un estado que no refleja la configuración guardada.
- **Tratamiento posterior:** Capturar errores de escritura, preservar la configuración anterior cuando sea posible y comunicar el fallo a la UI para permitir reintento o recuperación.

### DEBT-006

- **Hallazgo:** En `services/comicvine_api.py`, respuestas JSON inválidas/inesperadas pueden provocar excepciones no controladas.
- **Impacto:** Respuestas malformadas o con campos ausentes pueden interrumpir el enriquecimiento y propagar fallos hasta la UI o el procesamiento del lote.
- **Tratamiento posterior:** Validar el JSON y su estructura antes de acceder a los datos, manejar respuestas inválidas de forma controlada y devolver errores recuperables al consumidor.
