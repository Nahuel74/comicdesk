# CBL Maker Desktop

- **Tipo**: feature
- **Complejidad estimada total**: Alta

## Propósito

App de escritorio Linux para:
1. Configurar API key de Comic Vine
2. Explorar carpetas con cómics CBZ
3. Leer metadata de ComicInfo.xml y extraer URLs de Comic Vine
4. Crear archivos CBL con las opciones de ordenamiento

## Stack

- **Runtime**: Python 3.14+
- **UI**: PySide6 (Qt)
- **ZIP**: zipfile (stdlib)
- **XML**: lxml o xml.etree.ElementTree (stdlib)
- **HTTP**: httpx (async) o requests
- **Config**: JSON en ~/.config/cbl-maker/

## Formato CBL (referencia)

```xml
<?xml version="1.0" encoding="utf-8"?>
<ReadingList xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <Name>One World Under Doom (2025)</Name>
    <Books>
        <Book SeriesName="Dr. Strange and Dr. Doom Triumph and Torment" Volume="1989" Issue="1">
            <Database Name="cv" Series="23227" Issue="139720" />
        </Book>
        <Book SeriesName="Avengers" Volume="2023" Issue="19">
            <Database Name="cv" Series="150431" Issue="1074674" />
        </Book>
    </Books>
    <Matchers />
</ReadingList>
```

- **Book attributes**: SeriesName, Volume, Issue → del CBZ (ComicInfo.xml)
- **Database attributes**: Name="cv", Series (CV series ID), Issue (CV issue ID) → de Comic Vine API

## Estructura del Proyecto

```
cbl-maker/
├── main.py                    # Entry point
├── requirements.txt
├── cbl_maker/
│   ├── __init__.py
│   ├── app.py                 # QApplication setup
│   ├── config.py              # Gestión de configuración
│   ├── models.py              # Dataclasses: Comic, ReadingList, etc.
│   ├── services/
│   │   ├── __init__.py
│   │   ├── cbz_reader.py      # Lectura de CBZ + ComicInfo.xml
│   │   ├── comicvine_api.py   # Cliente API Comic Vine con cache
│   │   └── cbl_writer.py      # Generación de archivos CBL
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py     # Ventana principal
│   │   ├── config_dialog.py   # Dialogo de configuración
│   │   ├── folder_panel.py    # Panel de exploración de carpetas
│   │   ├── comic_list.py      # Lista de cómics con drag & drop
│   │   └── reading_list_panel.py  # Panel de lista de lectura
│   └── utils/
│       ├── __init__.py
│       └── url_parser.py      # Extracción de IDs de URLs de Comic Vine
└── tests/
    ├── __init__.py
    ├── test_cbz_reader.py
    ├── test_comicvine_api.py
    ├── test_cbl_writer.py
    └── test_url_parser.py
```

## Historias

### [H-1] Configuración y estructura del proyecto
- **Depende de**: ninguna
- **Complejidad**: Baja
- **Archivos**: requirements.txt, cbl_maker/__init__.py, cbl_maker/config.py, cbl_maker/app.py, main.py
- **Descripción**:
  - Crear estructura de directorios
  - Configurar requirements.txt con dependencias
  - Implementar config.py para leer/guardar API key en ~/.config/cbl-maker/config.json
  - Crear entry point main.py con QApplication
- **Constraints**: 
  - No hardcodear rutas absolutas
  - Usar pathlib para rutas
- **Tests**: test_config.py (leer/escribir config)

### [H-2] Modelos de datos
- **Depende de**: ninguna
- **Complejidad**: Baja
- **Archivos**: cbl_maker/models.py
- **Descripción**:
  - Crear dataclasses: Comic, ReadingList, ComicVineIssue
  - **Comic** (metadata extraída del CBZ):
    - `path`: Path al archivo CBZ
    - `series_name`: str → de ComicInfo.xml/Series
    - `volume`: str → de ComicInfo.xml/Volume
    - `issue_number`: str → de ComicInfo.xml/Number
    - `year`: str → de ComicInfo.xml/Year
    - `web_links`: list[str] → URLs de Comic Vine (campos Web/Notes)
    - `cv_series_id`: Optional[str] → ID de serie en Comic Vine
    - `cv_issue_id`: Optional[str] → ID de issue en Comic Vine
  - **ReadingList**:
    - `name`: str
    - `comics`: list[Comic]
    - `ordered_by`: str ("release_date" | "manual")
  - **ComicVineIssue** (respuesta de API):
    - `id`: str (issue ID, ej: "139720")
    - `series_id`: str (series ID, ej: "23227")
    - `series_name`: str
    - `volume`: str
    - `issue_number`: str
    - `cover_date`: str
    - `web_url`: str
- **Constraints**: 
  - Usar dataclasses, no Pydantic
  - Serializable a JSON
- **Tests**: test_models.py (creación, serialización)

### [H-3] Lector de CBZ + ComicInfo.xml
- **Depende de**: H-2
- **Complejidad**: Media
- **Archivos**: cbl_maker/services/cbz_reader.py
- **Descripción**:
  - Función para abrir CBZ (ZIP) y extraer ComicInfo.xml
  - Parsear XML y extraer campos del atributo/elemento:
    - Series → series_name
    - Volume → volume
    - Number → issue_number
    - Year → year
    - Web → web_links (extraer URLs de Comic Vine)
    - Notes → web_links (extraer URLs de Comic Vine)
  - Extraer URLs usando regex: `comicvine\.gamespot\.com/[^/]+/(\d{4}-\d+)/?`
  - Retornar objeto Comic con metadata
  - Función para escanear carpeta recursivamente y retornar list[Comic]
- **Constraints**:
  - ComicInfo.xml puede no existir → retornar metadata mínima (solo path)
  - Manejar encoding UTF-8 y Latin-1
  - No extraer imágenes, solo metadata
- **Tests**: test_cbz_reader.py con CBZ mock (ZIP con XML de prueba)

### [H-4] Cliente API Comic Vine
- **Depende de**: H-2
- **Complejidad**: Alta
- **Archivos**: cbl_maker/services/comicvine_api.py
- **Descripción**:
  - Clase ComicVineClient con:
    - Constructor recibe api_key
    - `get_issue(issue_id)` → ComicVineIssue (extrae series_id del response)
    - `get_volume(volume_id)` → ComicVineIssue (para obtener series_id)
    - `search_issue(query)` → list[ComicVineIssue]
  - Rate limiting: mínimo 1 segundo entre requests (time.sleep)
  - Cache en memoria (dict) + persistencia en disco (~/.config/cbl-maker/cache/)
  - Manejo de errores: rate limit (429), API key inválida (100), no encontrado (101)
  - Logging de requests para debug
- **Constraints**:
  - Respetar rate limit estrictamente (1 req/segundo)
  - Cache para evitar requests duplicados
  - Extraer series_id del campo `volume.id` o `volume.names` del response
- **Tests**: test_comicvine_api.py con responses mockeadas

### [H-5] Escritor de CBL
- **Depende de**: H-2
- **Complejidad**: Media
- **Archivos**: cbl_maker/services/cbl_writer.py
- **Descripción**:
  - Función `generate_cbl(reading_list: ReadingList)` → str (XML)
  - Generar XML válido con formato ComicRack:
    ```xml
    <?xml version="1.0" encoding="utf-8"?>
    <ReadingList xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Name>{list_name}</Name>
        <Books>
            {for each comic:}
            <Book SeriesName="{series_name}" Volume="{volume}" Issue="{issue_number}">
                <Database Name="cv" Series="{cv_series_id}" Issue="{cv_issue_id}" />
            </Book>
        </Books>
        <Matchers />
    </ReadingList>
    ```
  - Función `save_cbl(xml_content: str, output_path: Path)`
- **Constraints**:
  - XML válido que Komga/Kavita/ComicRack CE importen
  - Atributos en orden: SeriesName, Volume, Issue
  - Database siempre con Name="cv"
  - Si cv_series_id o cv_issue_id son None, omitir elemento Database
- **Tests**: test_cbl_writer.py (generación XML, validación contra formato real)

### [H-6] Parser de URLs de Comic Vine
- **Depende de**: ninguna
- **Complejidad**: Baja
- **Archivos**: cbl_maker/utils/url_parser.py
- **Descripción**:
  - Función `extract_comicvine_ids(url: str)` → dict con `series_id` y `issue_id`
  - Extraer de URLs como:
    - `https://comicvine.gamespot.com/doctor-strange-and-doctor-doom-triumph-and-torment/4000-139720/`
      → `{"series_id": "23227", "issue_id": "139720"}` (formato: `{type}-{id}`)
  - El número antes del guión indica el tipo: 4000 = issue, 4050 = volume/series
  - Validar formato: `\d{4}-\d+`
- **Constraints**:
  - Manejar URLs con/sin trailing slash, con/sin www
  - Solo extraer IDs, no resolver nombres
- **Tests**: test_url_parser.py (varias URLs, edge cases)

### [H-7] UI: Ventana principal y configuración
- **Depende de**: H-1, H-3, H-4
- **Complejidad**: Media
- **Archivos**: cbl_maker/ui/main_window.py, cbl_maker/ui/config_dialog.py
- **Descripción**:
  - MainWindow con menú Archivo > Configuración
  - Dialogo de configuración:
    - Campo API Key (con botón "Validar contra Comic Vine")
    - Campo carpeta por defecto
    - Botón Guardar/Cancelar
  - StatusBar con estado de conexión a Comic Vine
- **Constraints**:
  - API key nunca se muestra completa (mascarar con ****)
  - Validar API key haciendo request de prueba
- **Tests**: test_config_dialog.py (validación de inputs)

### [H-8] UI: Panel de exploración de carpetas
- **Depende de**: H-3, H-7
- **Complejidad**: Media
- **Archivos**: cbl_maker/ui/folder_panel.py
- **Descripción**:
  - Panel izquierdo con QTreeView para explorar filesystem
  - Filtro para mostrar solo carpetas que contengan CBZ
  - Al seleccionar carpeta → escanear CBZs y populate comic_list
  - Botón "Escanear recursivamente"
  - Progress bar durante escaneo
- **Constraints**:
  - Escaneo en QThread para no congelar UI
  - Cancelar escaneo si cambia de carpeta
- **Tests**: test_folder_panel.py (mock filesystem)

### [H-9] UI: Lista de cómics con metadata
- **Depende de**: H-3, H-7, H-8
- **Complejidad**: Alta
- **Archivos**: cbl_maker/ui/comic_list.py
- **Descripción**:
  - QTableView con columnas: Archivo, Serie, Número, Volumen, Año, URL CV, Estado
  - Columna Estado: ✅ (cv_series_id + cv_issue_id presentes), ⚠️ (parcial), ❌ (sin CV)
  - Click en URL CV → abrir en navegador (QDesktopServices.openUrl)
  - Botón "Enriquecer desde Comic Vine" para buscar IDs faltantes
  - Selección múltiple (Ctrl+Click, Shift+Click) para agregar a reading list
  - Context menu: "Agregar a lista", "Copiar metadata"
- **Constraints**:
  - Requests a Comic Vine en QThread separado
  - Mostrar progreso de enriquecimiento (X/Y procesados)
- **Tests**: test_comic_list.py (renderizado, selección)

### [H-10] UI: Panel de lista de lectura (reading list)
- **Depende de**: H-2, H-5, H-9
- **Complejidad**: Alta
- **Archivos**: cbl_maker/ui/reading_list_panel.py
- **Descripción**:
  - Panel derecho con QListView para reading list
  - Drag & drop para reordenar cómics (Qt drag/drop)
  - Botones: "Mover arriba", "Mover abajo", "Eliminar"
  - Orden por defecto al agregar: cover_date de Comic Vine (más antiguo primero)
  - Botón "Guardar CBL" → diálogo para nombre y ubicación
  - Preview del XML generado (QTextEdit read-only)
- **Constraints**:
  - Persistir orden manual (no reordenar automáticamente)
  - Validar que no haya duplicados (mismo archivo)
  - Exportar CBL válido
- **Tests**: test_reading_list_panel.py (drag & drop, exportación)

### [H-11] Integración y flujo completo
- **Depende de**: H-7, H-8, H-9, H-10
- **Complejidad**: Alta
- **Archivos**: cbl_maker/app.py (modificar), main.py (modificar)
- **Descripción**:
  - Conectar todos los paneles en MainWindow (QSplitter)
  - Flujo completo:
    1. Seleccionar carpeta en folder_panel
    2. Escanear CBZs → comic_list muestra resultados
    3. Enriquecer metadata (click botón) → comicvine_api busca IDs
    4. Seleccionar cómics → agregar a reading_list_panel
    5. Reordenar manualmente si necesario
    6. Guardar CBL → cbl_writer genera XML
  - Guardar/cargar reading lists previas (JSON en ~/.config/cbl-maker/lists/)
  - Atajos: Ctrl+S (guardar lista), Ctrl+E (exportar CBL)
- **Constraints**:
  - Autosave cada 5 minutos
  - Manejar errores de red gracefully (mostrar en statusbar)
- **Tests**: test_integration.py (flujo end-to-end con mocks)

## Dependencias y paralelismo

- **Grupo 1 (paralelo)**: H-1, H-2, H-6
- **Grupo 2 (paralelo)**: H-3, H-4, H-5 (depende de H-2)
- **Grupo 3 (paralelo)**: H-7 (depende de H-1, H-3, H-4)
- **Grupo 4 (paralelo)**: H-8, H-9 (depende de H-3, H-7)
- **Grupo 5**: H-10 (depende de H-2, H-5, H-9)
- **Grupo 6**: H-11 (depende de todo)

## Restricciones Globales

- **Rate Limit Comic Vine**: Mínimo 1 segundo entre requests. Cache obligatorio.
- **Formato CBL**: Debe ser compatible con Komga, Kavita y ComicRack CE
- **No persistir API key en texto plano** → Considerar keyring del OS
- **Manejo de errores**: Todos los servicios deben manejar excepciones y reportar a UI
- **Threading**: Operaciones de red y escaneo en QThread/QRunnable
