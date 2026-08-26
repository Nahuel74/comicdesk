---
name: desarrollo
description: Lee un plan de .opencode/plans/, crea rama, ejecuta desarrollo con executors en paralelo por historia, QA, pre-commit y feature finish. Sin release.
---

# Desarrollo

Usar esta skill cuando hay un plan aprobado en `.opencode/plans/` y se requiere ejecutar el desarrollo.

## Reglas globales

- **Sintetizar, no filtrar:** Consolidar outputs de subagentes en reporte estructurado (Errores, Advertencias, Sugerencias). Ordenar por criticidad. No eliminar datos, solo estructurarlos.
- **Aislamiento de Deuda Técnica:** Si se detecta deuda preexistente, registrarla en `DEBT_LOG.md` para tratamiento posterior. No bloquear la historia actual a menos que la deuda impida la implementación.
- **Automatización de Pasos Deterministas:** Pasos de preparación (Fase 1) y análisis sintáctico se ejecutan automáticamente. Solo detener ante `exit code != 0` o conflictos de merge.
- **NUNCA** ignorar exit code != 0.
- Si un executor falla 3 veces → escalar al usuario.
- Merge conflicts → DETENER y notificar al usuario. NUNCA resolver conflictos.
- **NUNCA pushear** feature o bugfix branches a origin. Todo es local hasta la release.

---

## Fase 1 — Preparación (automática)

### 1.1 Validar working tree

1. `git status --porcelain` — si hay cambios sin commit, hacer `git stash push -m "auto-stash pre-desarrollo"`
2. `git branch --show-current` — si ya estás en feature/bugfix, validar nombre
3. Si no está en develop: `git checkout develop && git pull`
4. Si no hay rama: crear según el plan

### 1.2 Crear rama

1. Inferir tipo (`feature` / `bugfix`) del contexto del plan e idioma del repositorio
2. Crear rama automáticamente: `git flow feature start <nombre>` o `git flow bugfix start <nombre>`

---

## Fase 2 — Desarrollo por historias

### 2.1 Agrupar historias por paralelismo

Según el plan, identificar los grupos de paralelismo:

- Grupo 1: historias sin dependencias (paralelo)
- Grupo 2: historias que dependen de Grupo 1 (paralelo entre sí)
- etc.

### 2.2 Ejecutar Grupo 1 (paralelo con verificación de aislamiento)

Para cada historia en el grupo, descomponerla en subtareas atómicas e **invocar executors directamente** según el dominio de cada archivo:

1. Identificar los archivos a modificar/crear según el plan
2. **Verificar intersección de archivos:** si dos executors modifican archivos compartidos, forzar ejecución secuencial para ese subconjunto
3. Agrupar cambios por dominio (`src/` → executor-frontend, `server/` → executor-backend, `db/` → executor-database)
4. Para cada grupo, invocar el executor correspondiente vía `task()` en paralelo
5. Incluir en cada prompt: archivo exacto, acción concreta, constraints del plan, tests a verificar

**Formato de invocación a executor:**

```
TAREA: Implementar [H-<N>] <título> — <acción específica>
ARCHIVO: <ruta exacta>
ACCIÓN: qué cambiar específicamente
CONSTRAINTS: qué respetar (del plan)
TESTS: qué tests verificar
```

### 2.3 Evaluar resultados del Grupo 1

1. **Consolidar outputs en reporte estructurado:** Errores, Advertencias, Sugerencias (ordenados por criticidad)
2. Errores de executor → analizar, re-planificar, re-invocar (máx 3 intentos)
3. Si el usuario aprueba el reporte: continuar

### 2.4 Ejecutar Grupo 2 (y siguientes)

Repetir pasos 2.2 y 2.3 para cada grupo secuencialmente.

## Fase 3 — QA post-cambio

1. Invocar `executor-quality` sobre archivos modificados
2. **Clasificar hallazgos:**
   - Errores del cambio actual → corregir
   - Deuda técnica preexistente → registrar en `DEBT_LOG.md`, no bloquear
3. Ejecutar los fixes aprobados
4. Volver a ejecutar quality checks + `executor-quality`
5. **Repetir pasos 2–4** hasta que no haya errores del cambio actual → avanzar a Fase 4

---

## Fase 4 — Pre-commit

1. Pre-commit review:
    - Código nuevo no rompe archivos afectados
    - Cumple convenciones (300 líneas, SRP, DRY)
    - Consistente con estructura existente
    - No hay dead code
2. Presentar lista de cambios y funciones que el usuario deberá testear localmente. Esperar OK explícito del usuario.
3. Commit: `git add -A && git commit -m "<mensaje>"`
4. **IMPORTANTE: NO hacer push.** El feature branch es local.
5. Elimina el archivo del plan original.
6. Finish: `git flow feature finish <nombre>` o `git flow bugfix finish <nombre>`
    - Si falla por merge conflict: DETENER. NO resolver. Notificar al usuario.
7. **Fin de la skill.** El desarrollo está mergeado a develop localmente.

---

**NUNCA** ejecutar release tasks en esta skill.
