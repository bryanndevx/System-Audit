# Recuperación de diagnósticos Gemini

**Actualización vigente:** el usuario indicó que no debe existir un botón manual. La recuperación de una etapa interrumpida se inicia automáticamente al abrir el resultado. Se corrigieron además los caminos de guardado/contexto que podían impedir llegar a Gemini y se incorporó compresión sin pérdida para evidencia grande. Ver [análisis por archivo y reproducciones](diagnostico-ia-pendiente.md); esta actualización sustituye las referencias al botón que se describen como comportamiento anterior en este documento.

El HTTP 503 observado indica indisponibilidad del proveedor, no falta de evidencia PostgreSQL. La implementación anterior enviaba lotes secuenciales de doce actividades (seis solicitudes para 67), tenía timeout HTTP de 20 segundos y detenía los lotes al primer error, sin reintentos. No hay evidencia de concurrencia excesiva dentro de una auditoría, clave incorrecta ni agotamiento de cuota en ese 503. Referencia: [errores Generate Content de Gemini](https://ai.google.dev/gemini-api/docs/generate-content/api-errors?hl=en).

## Comportamiento

- Cola interna por proceso: una solicitud Gemini activa, también entre auditorías simultáneas. El arranque actual utiliza un proceso Uvicorn; múltiples instancias tendrían colas independientes.
- Máximo tres intentos por lote para fallos de red/timeout y HTTP 408, 429, 500, 502, 503 y 504. Backoff exponencial de 2 y 4 segundos más jitter de 0–1 segundos, tomando el mayor valor respecto de `Retry-After` (segundos o fecha HTTP). No reintenta errores de autenticación/configuración ni JSON inválido.
- Si el proveedor pide más de 60 segundos, se deja pendiente sin insistir anticipadamente. La fecha `reintentar_desde` se guarda y respeta también al reabrir el historial; la cola del proceso conserva la espera entre solicitudes.
- Socket de 20 segundos y cierre programado de la conexión a los 30 segundos. No se libera el turno mientras el hilo de red cancelado siga activo.
- Después de agotar intentos se detienen los lotes restantes para evitar gastar cuota durante una caída. Las actividades no enviadas conservan `no_solicitada`; no se les atribuye una respuesta HTTP inexistente.
- Logs limitados a código HTTP, transitoriedad y número de intento. No se registran claves, prompts, respuestas ni evidencias clínicas. El contexto técnico filtrado anterior se conserva.
- Se mantiene el modelo configurado; no hay cambio de proveedor, modelo ni infraestructura nueva.

## Evidencia e historial

Al cerrar la conexión auditada se guarda primero toda la evidencia en la base interna. Si ese guardado falla, se devuelve la evidencia en pantalla con advertencia y no se consume IA. Cada lote válido actualiza el mismo registro del historial; un fallo posterior conserva los lotes anteriores. La exportación PDF utiliza el registro actualizado.

Resultados e historial ofrecen **Reintentar análisis IA pendiente**, mediante `POST /api/audits/{id}/retry-ai`. Requiere sesión, CSRF y propiedad del registro. Solo acepta el identificador guardado: no recibe credenciales ni evidencia desde el navegador. Un bloqueo consultivo de PostgreSQL interno impide analizar simultáneamente el mismo registro entre procesos; una petición duplicada en curso devuelve 409. No se abre conexión a la base auditada ni se ejecuta el motor SQL al reintentar. Los textos válidos se omiten.

Completada sigue exigiendo evidencia suficiente y diagnóstico/recomendación válidos. La información externa real permanece pendiente aunque IA responda. Los avisos generados por un fallo IA no se convierten en información externa durante la reevaluación. Se preservan causas de permisos, errores SQL y evidencia insuficiente. No se modifican actividades ni consultas SQL del catálogo.

`duracion_ia_ms` acumula intentos, esperas de cola y reintentos. `duracion_ejecucion_ms` acumula procesamiento activo, sin sumar las horas que el auditor espere antes de reintentar. La versión del checklist y los criterios se conservan: para una medición experimental nueva debe registrarse también la versión de código y esta política de reintentos. Ningún resultado del experimento se reescribe por abrirlo; solo cambia al solicitar expresamente el análisis pendiente.

## Verificación y uso

Reiniciar backend, recargar frontend, abrir la auditoría guardada y pulsar **Reintentar análisis IA pendiente**. No es necesario importar otra vez el Excel ni repetir las consultas. Cada lote se guarda; si se pierde la conexión del navegador, consultar el historial antes de volver a intentar.

Pruebas locales: `python -m unittest discover -s tests -q` desde backend, `npm run build` y `npm run lint` desde frontend. `tests/test_ai_recovery.py` cubre cliente, backoff, cooldown persistido, concurrencia, estados, permisos HTTP y ruta ASGI con almacenamiento simulado. `tests/integration/test_ai_recovery.py` es opt-in, utiliza un historial PostgreSQL ficticio real y evidencia de las 67 actividades obtenida previamente en la fixture; verifica guardado intermedio de doce narrativas, recuperación posterior al 503, conservación exacta de evidencias/trazas y bloqueo de solicitudes duplicadas.

Todos los proveedores de IA de estas pruebas son **simulados**. No se consumió cuota Gemini real ni se accedió a SmartDent/producción. La disponibilidad, cuota y compatibilidad efectiva del modelo con la cuenta real siguen dependiendo del servicio. Los reintentos reducen fallos transitorios; no garantizan que un proveedor caído se recupere ni certifican la calidad semántica de sus textos.

Resultados ejecutados: suite completa de 218 pruebas aprobada; después de reforzar el cierre por timeout se ejecutaron las 38 pruebas de IA (incluida una nueva prueba de cierre del transporte), todas aprobadas. Compilación y lint aprobados. Integración PostgreSQL 18 aislado: 67 narrativas recuperadas tras un 503 simulado, seis lotes válidos más el intento fallido, guardado intermedio de doce textos, segundo POST sin nuevas llamadas y evidencias/trazas idénticas. Flujo HTTP real: login, historial privado, 67 eventos, persistencia y PDF. Navegador con respuestas simuladas: doble clic bloqueado, actualización de estados/porcentaje, fallo sin pérdida de resultados, móvil sin desbordamiento y sin errores JavaScript. Los procesos locales de prueba se cerraron.

Archivos: `backend/app/ai_diagnostics.py`, `audit_history.py`, `audits.py`, `audit_coverage.py`; `frontend/src/auditApi.ts`, `AuditResults.tsx`; pruebas de IA y endpoints, prueba de integración nueva y documentación de Gemini/checklist.
