---
name: release
description: Ejecuta el ciclo de release: release start, estabilización (QA blockers), staging/UAT testing, release finish y push sincronizado.
---

# Release

Usar esta skill cuando el desarrollo está completo (feature/bugfix merges en develop local) y se requiere crear y finalizar una release.

## Reglas globales

- **NUNCA asumir nada de lo que devuelve un subagente**: todo hallazgo, sugerencia o resultado debe ser reportado textualmente al usuario.
- **Deuda técnica jamás se ignora**: todo issue se reporta (en contexto de release solo se reportan errores bloqueantes: compilación, tests fallidos, vulnerabilidades críticas).
- **APROBACIÓN EXPLÍCITA para commit y push**: presentar changelog, esperar OK, commit, esperar OK, push.
- **NUNCA** saltar fases.
- **NUNCA** ignorar exit code != 0.
- Merge conflicts, DETENER y notificar al usuario. NUNCA resolver conflictos.

---

## Fase 1, Release start

1. `git status --porcelain`, working tree limpio
2. `git branch --show-current`, debe estar en `develop`
3. `git fetch origin` (traer todo, incluyendo main actualizado)
4. `git checkout main && git pull origin main && git checkout develop && git pull origin develop`
5. Analizar diff entre main y develop:
    - `git log --oneline --no-merges main..develop` — commits a releasear
    - `git log --oneline --no-merges main..develop --grep='^feat'` — features
    - `git log --oneline --no-merges main..develop --grep='^fix'` — bugfixes
    - `git log --oneline --no-merges main..develop --grep='^BREAKING'` — breaking changes
6. Con base en el diff, proponer versión:
    - Si hay BREAKING → major (`X.0.0`)
    - Si hay feat → minor (`0.X.0`)
    - Solo fix/chore → patch (`0.0.X`)
7. Generar propuesta de changelog con los mensajes de commits agrupados por tipo
8. **Presentar diff, version propuesta y changelog al usuario**, esperar OK explícito
    - Si el usuario emite un OK explícito, modificar changelogData con el propuesto y commitearlo.
9. `git flow release start <version>` (numero SIN prefijo V, ej: `2.8.2`)

---

## Fase 2 — Estabilización de Release (QA)

1. Invocar `executor-quality` configurado estrictamente en modo `--only-blockers` o analizando exclusivamente el diff entre `main..release/<version>`.
2. **Filtrar reportes:** Presentar únicamente errores de compilación, fallos de tests unitarios/integración o vulnerabilidades críticas de seguridad.
3. Si se requieren *hotfixes* de estabilización, ejecutarlos directamente sobre la rama `release/<version>`.

---

## Fase 3 — Testeo en Entorno de Staging/Pre-producción

1. **NO mezclar en develop prematuramente.** Desplegar la rama propia `release/<version>` en el servidor de pruebas o entorno de Staging/UAT (User Acceptance Testing).
2. El usuario ejecuta el testeo manual sobre esta compilación aislada.
3. **Esperar OK del usuario** para proceder al cierre definitivo.

---

## Fase 4 — Finalización y Sincronización Global

1. Proponer: "Finalizo release <version>?"
2. **Esperar OK explícito.**
3. `git flow release finish <version>`
   - Si falla por merge conflict: DETENER. NO resolver. Notificar al usuario.
4. **Sincronizar ambas ramas principales en el remoto:**
   - `git push origin main --tags`
   - `git push origin develop`
5. Informar que la release está completa, mergeada y sincronizada en ambos entornos.

---

**NUNCA** ejecutar desarrollo o planificación en esta skill. Usar `planificacion` y `desarrollo` para eso.
