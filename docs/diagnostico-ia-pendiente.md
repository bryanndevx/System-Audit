# Diagnóstico del resultado sin narrativa — 17/11/2026

La captura muestra evidencia obtenida y el texto alternativo del frontend «No hay redacción disponible para esta actividad». Ese texto significa que la narrativa no tiene mensaje registrado. No demuestra HTTP 503, clave inválida ni cuota agotada. Se inspeccionó el OpenAPI del backend local activo: ya incluía recuperación y cooldown; no se asumió que fuera una versión antigua. No se consultó SmartDent ni se llamó a Gemini real.

## Revisión por archivo

| Archivo | Hallazgo y acción |
| --- | --- |
| `backend/app/local_config.py` | Lee únicamente tres variables Gemini; la terminal y el proceso tienen prioridad sobre `.env`. Una clave editada requiere reiniciar el proceso actual. La lectura en un proceso nuevo confirmó IA habilitada y presencia de clave, sin mostrarla. Eso no valida la clave contra Google. Sin cambios en este archivo. |
| `backend/run_backend.py` | Carga configuración antes de arrancar Uvicorn; mantiene la configuración de conexión independiente. Sin cambios. |
| `backend/app/audit_engine.py` | El resultado SQL nace con una narrativa por defecto sin mensaje; por sí mismo no contacta Gemini. No se cambiaron consultas, actividades ni criterios SQL. |
| `backend/app/audits.py` | Guardaba la evidencia antes de IA. Si fallaba el guardado, devolvía el resultado original sin ejecutar IA, dejando las narrativas por defecto. Ahora se registra claramente ese impedimento. Se inicializa explícitamente el estado de análisis pendiente antes de guardar. Una excepción inesperada en la etapa IA se registra por clase, sin texto privado, y se guarda su causa segura en el resultado. |
| `backend/app/audit_history.py` | El límite anterior de 16 MiB se aplicaba al resultado íntegro sin compresión. La repetición de metadatos entre actividades podía superarlo. Ahora se conserva JSON normal para registros pequeños y se comprime el cuerpo íntegro de resultados grandes en el mismo JSONB; metadatos y resumen siguen consultables. Máximo 64 MiB descomprimidos y 16 MiB de representación almacenada; lectura limitada y validación de corrupción. No requiere migración ni dependencias adicionales. |
| `backend/app/ai_context.py` | Construye el resumen técnico permitido. Una excepción aquí se producía antes del bloque que manejaba errores Gemini. Los casos de forma inesperada no eran errores de proveedor. Se mantiene el filtrado; no se envía evidencia completa, comentarios ni datos de prueba de carga. Sin cambios en sus reglas. |
| `backend/app/ai_diagnostics.py` | Se aisló el error de contexto por actividad para que no aborte las demás. Se conserva evidencia y se registra `contexto_invalido`; las otras actividades continúan. Se mantienen modelo, lotes, cola, timeout y reintentos limitados previos. |
| `backend/app/audit_coverage.py` | Exige evidencia suficiente y narrativa válida. No se relajó la clasificación para aumentar completadas. Sin cambios en esta revisión. |
| `frontend/src/NewAudit.tsx` | Consume el resultado final del flujo y muestra el resultado devuelto. Un guardado fallido podía llegar como resultado válido, pero con IA sin iniciar. Sin cambios; la respuesta del backend ahora explica esa causa. |
| `frontend/src/auditApi.ts` | La recuperación utiliza el identificador del historial, sesión y CSRF. Se deduplican peticiones simultáneas del navegador. No recibe credenciales PostgreSQL ni ejecuta SQL auditado. |
| `frontend/src/AuditResults.tsx` | Se eliminó el botón manual según la corrección del usuario. Al abrir un registro técnico cuya etapa IA quedó sin terminar y sin error definitivo registrado, se solicita recuperación automáticamente una vez. Si ya está en curso (409), se consulta avance sin duplicar el análisis. No hay bucle ilimitado de llamadas Gemini; errores configurados/proveedor ya agotados se muestran con su causa. |
| `frontend/src/ActivityDetail.tsx` | Se sustituyó el mensaje genérico por una explicación de narrativa sin respuesta/error registrado, diferenciándola de una respuesta HTTP del proveedor. El detalle abierto se actualiza cuando termina la recuperación. |
| `backend/app/audit_pdf.py` | Consume resultados mediante `get_saved_audit`, que descomprime cuando corresponde. No vuelve a consultar la base auditada. Sin cambios. |

## Reproducciones ficticias

1. Se amplió una fixture de 67 actividades a unos 2.691 campos de diccionario: aproximadamente 14,6 MB antes de añadir comentarios adicionales. Esta no es una medición del resultado real del usuario y no prueba que su auditoría supere el límite, pero muestra la proximidad al umbral anterior.
2. Una carga artificial mayor a 16 MiB reproduce el rechazo del guardado anterior. En esa rama se omitía IA, independientemente de la clave. La prueba nueva verifica almacenamiento sin pérdida y continuación de los seis lotes sobre PostgreSQL interno real aislado.
3. Una excepción de preparación de contexto antes de la llamada al proveedor reproducía la interrupción general. Ahora solo esa actividad queda con causa explícita y otra actividad ficticia sí obtiene narrativa simulada.
4. Una excepción inesperada en el procesamiento se guarda como `error_interno`; el texto privado de la excepción no sale al frontend. La evidencia se conserva.
5. Navegador con respuestas simuladas: recuperación al abrir el resultado sin botón, una sola petición, ninguna ejecución SQL, actualización del porcentaje/estado, fallo HTTP sin pérdida de evidencia y seguimiento del trabajo existente tras 409.

La coincidencia entre síntomas y caminos de código no permite atribuir retrospectivamente una causa única al registro real sin su aviso de almacenamiento o traza. No se presenta la captura como prueba de un nuevo 503. La disponibilidad y cuota reales de Gemini siguen sin comprobarse, por instrucción de no consumir API real.

## Uso actual

Reiniciar backend para cargar el código y la clave actuales, recargar frontend y abrir el resultado guardado. El análisis forma parte de la ejecución y la recuperación de una etapa interrumpida es automática. No hay botón de reintento. Si la ejecución anterior no llegó a guardarse, no existe evidencia persistida que recuperar: debe ejecutarse una nueva auditoría una vez, usando la versión corregida. Los fallos de proveedor siguen sujetos a los tres intentos y `Retry-After`; no se disfraza una caída persistente como actividad completada.

Los registros pequeños e históricos mantienen su formato y sus resultados; la compresión no elimina campos ni altera las evidencias. Abrir un resultado que tenía diagnóstico válido no vuelve a generar sus textos.

## Verificaciones ejecutadas

- 226 pruebas de la suite completa aprobadas, incluyendo aislamiento de errores de contexto, guardado del error interno, compresión íntegra, compatibilidad histórica, corrupción y límites de descompresión.
- Dos pruebas de integración de recuperación aprobadas sobre PostgreSQL 18 aislado: tamaño normal y carga ficticia mayor de 16 MiB. En ambos casos, un 503 simulado seguido de seis lotes válidos completó las 67 narrativas, con checkpoint intermedio de doce y sin nuevas conexiones SQL auditadas. Los datos artificiales de carga no llegaron al contexto IA.
- Flujo HTTP real con fixtures: login, 67 eventos, historial privado, persistencia, PDF y rechazos 401/404. No se repitieron consultas al descargar.
- Navegador con proveedor y almacenamiento simulados: recuperación automática sin botón, petición única incluso en StrictMode, manejo de trabajo ya iniciado (409), conservación de 67 actividades al fallar, actualización de porcentaje, móvil y ausencia de errores JavaScript.
- Compilación y lint frontend aprobados. Los procesos y clústeres de prueba fueron cerrados. No se realizaron llamadas a Gemini real, escrituras en SmartDent ni git push.

La carga grande se guarda en un envoltorio JSONB marcado `zlib-json-v1`, con un índice de los 67 identificadores para respetar la restricción de integridad existente. La API y el PDF reciben siempre el resultado completo ya descomprimido; no se exponen índices parciales como si fueran evidencias. No hace falta ejecutar una migración.
