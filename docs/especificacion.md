# Especificación funcional — Sistema inteligente de auditoría PostgreSQL

## Estado
- Prototipo visual inicial realizado en Figma. Se usa como referencia principal, no como código fuente.
- Seis Sprints definidos. Implementación incremental, sin módulos adicionales no solicitados.

## Propósito
Permitir a un auditor importar el checklist Excel de su empresa, conectarse a una base PostgreSQL con credenciales de solo lectura, ejecutar automáticamente las actividades técnicamente resolubles desde PostgreSQL, mostrar evidencia y recibir diagnósticos/recomendaciones redactados por IA; consultar resultados históricos y exportar un PDF.

## Pantallas y flujo
1. **Login:** autenticación de usuario de la aplicación (distinta de las credenciales de PostgreSQL auditado).
2. **Dashboard:** auditorías realizadas, fecha, base, automatización, tiempo y acción `Ver`; acceso a `Nueva auditoría` y `Cerrar sesión`.
3. **Nueva auditoría:** importar `.xlsx`, detectar fases y actividades del archivo, configurar y probar conexión PostgreSQL, iniciar auditoría si ambos pasos son válidos.
4. **En proceso:** progreso (procesadas/total), tiempo y estados por fases/actividades. Progreso NO significa porcentaje de automatización.
5. **Resultados:** resumen (total, automatizadas, no automatizadas, porcentaje, tiempo), tabla por fases y detalle de cada actividad; acceso a `Exportar PDF`.
6. **Detalle:** evidencia organizada (tabla resumida o parámetros), diagnóstico, recomendación y tiempo. Debe permitir regresar a resultados.

## Checklist y catálogo
- El Excel es la fuente de fases, nombres de actividades y orden; no fijar 8 fases ni 65 actividades en código.
- Validar tamaño, extensión, estructura y contenido antes de procesar; no ejecutar macros ni código de archivos.
- Un catálogo interno asocia explícitamente cada actividad conocida con el conjunto de consultas SQL, transformación de evidencia y criterios de análisis.
- Una actividad automatizable puede requerir varias consultas: ejecutarlas todas de forma controlada antes del análisis.
- Si requiere información ajena a PostgreSQL para resolverse completamente, clasificar `No automatizada` con razón específica.
- Si una actividad no está mapeada en el catálogo, mostrar `Sin automatización configurada`; no decir que necesariamente requiere datos externos.
- Un fallo de consulta, permisos o IA es un ERROR; no presentarlo como `No automatizada` ni como `Conforme`.

## Flujo interno de actividad automatizada
1. Obtener la definición del catálogo y ejecutar SQL predefinido sin escritura.
2. Conservar el resultado original necesario para verificar el hallazgo, con límites y sin datos sensibles.
3. Construir el resumen de evidencia mediante lógica determinista Python.
4. Enviar únicamente el contexto técnico necesario al modelo de IA con criterios de análisis.
5. Validar la respuesta estructurada (diagnóstico + recomendación); registrar error si falla.
6. Registrar estado, tiempo, evidencia, diagnóstico, recomendación y metadatos de ejecución.

## IA
- Usar una API de modelo de lenguaje; sin RAG para primera versión.
- La IA redacta diagnóstico y recomendación; nunca genera SQL ejecutable, cambia valores ni decide la exactitud.
- Usar criterios técnicos previamente revisados y evitar conclusiones categóricas si la evidencia es insuficiente.
- La API de IA de la aplicación requiere su propia cuenta/credenciales y puede tener costo, separado de ChatGPT Plus/Codex.

## Indicadores de investigación
1. Automatización: actividades automatizadas / total evaluadas * 100, definiendo qué estados cuentan.
2. Tiempo: medir duración de las actividades automatizadas; comparar con ejecución manual equivalente sobre el mismo alcance.
3. Exactitud de resultados: comparar los datos devueltos automáticamente con una referencia manual obtenida en condiciones equivalentes (versión, permisos, alcance, instante/estado). No evaluar la redacción de la IA como si fuera precisión de consultas.
   Ejemplo: si la referencia tiene 17 esquemas y el sistema 15, verificar primero filtros/visibilidad; contrastar también identidades de esquemas y tablas, no solo cantidades.

## PDF
- Resumen general y resultados por fases, respetando orden del Excel.
- Para cada actividad automatizada: evidencia real presentada de forma legible y compacta; debajo diagnóstico, recomendación y tiempo.
- Plantillas sencillas por tipo de evidencia: parámetro/valor, tabla corta, lista agrupada, filas con observaciones y totales.
- Si hay muchas tablas, agrupar por esquema y mostrar nombres en una celda con ajuste de línea; preservar la trazabilidad del dato original.
- Las actividades no automatizadas aparecen con su motivo, sin presentarlas como incumplimientos.
- Exportar resultados guardados; no repetir la auditoría por exportar o abrir el historial.

## Seguridad y límites
- Usuario PostgreSQL específico de permisos mínimos; protección adicional mediante transacción de solo lectura y tiempos máximos.
- No exponer conexiones ni claves en frontend/URL/logs. Evitar que la configuración de host habilite acceso a destinos no autorizados (restringir destinos/red según despliegue).
- Validar certificado TLS para conexiones remotas según el contexto; `ssl=on` por sí solo no prueba que todas las sesiones sean seguras.
- No auditar backend, frontend o infraestructura ajena a los datos consultables de PostgreSQL.
- No modificar estructuras, parámetros ni datos de la BD auditada.
- El prototipo puede mejorarse en navegación, responsividad y mensajes, sin añadir paneles complejos, gráficas o módulos extra.

## Plan de seis Sprints
1. Diseño y elaboración del prototipo (ya existe versión inicial Figma).
2. Interfaz base, autenticación e importación del checklist Excel.
3. Conexión PostgreSQL y automatización de actividades mediante consultas predefinidas.
4. Integración de API de IA para diagnóstico y recomendación.
5. Progreso, resultados, indicadores e historial en el Dashboard.
6. Exportación del reporte de auditoría en PDF.

## Datos que necesitamos antes de implementar módulos concretos
- Enlace/exportaciones del Figma que se puedan visualizar; validar pantallas finales.
- Archivo Excel real o uno anonimizado con la misma estructura.
- Catálogo de actividades candidatas, consultas y criterios técnicos por preparar durante Sprint 3.
- Base PostgreSQL local de prueba con datos ficticios y credenciales de lectura.
- Proveedor de API de IA elegido durante Sprint 4; no es necesario para iniciar.
