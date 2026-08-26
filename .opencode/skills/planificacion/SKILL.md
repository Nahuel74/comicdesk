---
name: planificacion
description: Analiza una propuesta, lee archivos relevantes, crea plan detallado con épicas/historias + complejidad de contexto, identifica dependencias y guarda en .opencode/plans/
---

# Planificación

Usar esta skill cuando el usuario presenta una propuesta, feature request o reporte de bug que requiere planificación antes de codear.

## Reglas globales

- **NUNCA** ejecutar cambios de código en esta skill. Solo análisis y planificación.
- **Sintetizar hallazgos**: presentar resumen ejecutivo con alternativas y recomendación. No volcar análisis crudo al usuario.
- **Complejidad de Contexto**: estimar según archivos afectados, profundidad de dependencias y criticidad del componente (no usar escalas de esfuerzo humano).

---

## Fase 1 — Análisis

1. Entender la propuesta del usuario
2. Leer todos los archivos relevantes del codebase:
    - Archivos que se verán afectados
    - Archivos similares (mismo patrón/dominio)
    - Tests existentes relacionados
3. Identificar el alcance:
    - ¿Es una funcionalidad nueva?
    - ¿Es un bugfix?
    - ¿Es un refactor/deuda técnica?
    - ¿Cuál es el radio de impacto? (archivos, capas, dependencias)

## Fase 2 — Estructura del plan

### 2.1 Decidir si aplicar Épicas

- **Épica + Historias**: si el cambio excede el radio de impacto de una vertical slice acotada o requiere +3 historias relacionadas.
- **Solo Historias**: si es un cambio abordable en una vertical slice.

### 2.2 Descomponer en historias

Cada historia debe ser:

- **Una vertical slice**: unidad de funcionalidad verificable, puede cruzar capas si el radio de impacto está acotado
- **Estimable** (debe tener un nivel de complejidad de contexto)

Formato de cada historia en el plan:

```
## [H-<N>] <título>
- **Depende de**: H-<X> | ninguna
- **Complejidad**: Baja | Media | Alta | Crítica
- **Archivos**: lista de archivos a modificar/crear
- **Descripción**: qué hay que hacer
- **Constraints**: qué NO hacer, qué respetar
- **Tests**: qué tests crear o modificar
```

### 2.3 Identificar dependencias

- Si H-2 necesita que H-1 exista para funcionar → H-2 depende de H-1
- Las historias sin dependencias pueden ir en paralelo
- Agrupar historias en **grupos de paralelismo**:
    - Grupo 1 (paralelo): historias sin dependencias
    - Grupo 2 (paralelo): historias que dependen de Grupo 1
    - Grupo 3 (paralelo): historias que dependen de Grupo 2
    - etc.

### 2.4 Complejidad de Contexto

| Complejidad | Archivos | Dependencias              | Criticidad      | Ejemplo LLM                                         |
| ----------- | -------- | ------------------------- | --------------- | --------------------------------------------------- |
| Baja        | 1-2      | Ninguna o superficial     | Aislado         | Cambiar constante, renombrar, archivo único         |
| Media       | 2-5      | 1 nivel de profundidad    | Módulo interno  | Nueva ruta + servicio, nuevo componente             |
| Alta        | 5-10     | 2+ niveles de profundidad | Componente core | Nuevo flujo completo, cambios en múltiples capas    |
| Crítica     | 10+      | Profundo o circular       | Cross-cutting   | Migración de esquema + backend + frontend acoplados |

> **Nota**: La complejidad para un LLM depende del contexto necesario (archivos a leer, grafo de dependencias, riesgo de fallo por omisión), no del esfuerzo humano. Una tarea "trivial" para un humano (ej: cambiar una constante acoplada) puede ser de alta complejidad para un LLM si requiere navegar dependencias profundas.

## Fase 3 — Guardar el plan

1. Crear directorio `.opencode/plans/<nombre-descriptivo>/`
2. Generar un único archivo `plan.md` dentro del directorio
3. El nombre debe reflejar el propósito (ej: `login-social/`, `fix-carrito-precios/`)

### Reglas de estilo

- Mantenerlo eficiente desde un punto de vista de tokens

- No agregar explicaciones redundantes o narrativas

- Utilizar un lenguaje conciso

- No agregar justificaciones o explicaciones del "por qué" que ya estén establecidas

- Priorizar la densidad de viñetas frente al uso de párrafos

- Omitir detalles obvios

- Consolidar las restricciones que sean comunes a las distintas historias

### Formato único (`plan.md`):

```markdown
# <Título del plan>

- **Tipo**: feature | bugfix | refactor
- **Complejidad estimada total**: Baja | Media | Alta | Crítica

## Propósito

<qué resuelve>

## Estructura

<!-- Incluir secciones de Épica solo si el plan requiere múltiples vertical slices relacionadas -->

### [E-<N>] <nombre de la épica>

- **Depende de**: E-<X> | ninguna
- **Complejidad**: Baja | Media | Alta | Crítica
- **Descripción**: <qué abarca>

#### [H-<N>] <título>

- **Depende de**: H-<X> | ninguna
- **Complejidad**: Baja | Media | Alta | Crítica
- **Archivos**: lista de archivos a modificar/crear
- **Descripción**: qué hay que hacer
- **Constraints**: qué NO hacer, qué respetar
- **Tests**: qué tests crear o modificar

## Dependencias y paralelismo

- Grupo 1 (paralelo): H-1, H-3
- Grupo 2 (paralelo): H-2, H-4 (depende de Grupo 1)
```

### Variante sin épicas

Si no hay épicas, el mismo formato sin el nivel de épica:

```markdown
# <Título del plan>

- **Tipo**: feature | bugfix | refactor
- **Complejidad estimada total**: Baja | Media | Alta | Crítica

## Propósito

<qué resuelve>

## Historias

### [H-1] <título>

- **Depende de**: ninguna
- **Complejidad**: <Baja|Media|Alta|Crítica>
- **Archivos**: lista
- **Descripción**: qué hacer
- **Constraints**: qué NO hacer
- **Tests**: qué testear

## Dependencias y paralelismo

- Grupo 1 (paralelo): H-1, H-3
- Grupo 2 (paralelo): H-2 (depende de Grupo 1)
```

## Fase 4 — Presentar al usuario

1. Presentar un **resumen ejecutivo**:
    - Propósito del plan
    - Hallazgos clave del análisis
    - Alternativas consideradas (si aplica)
    - Recomendación estructurada con justificación
2. Exponer el plan completo
3. **Esperar OK explícito** del usuario
4. Si rechaza: ajustar según feedback → volver a Fase 2

---

**NUNCA** pasar directamente a desarrollo. Esta skill solo planifica.
