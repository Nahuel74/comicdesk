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
