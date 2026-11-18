# Diagnóstico y recomendación con Gemini — Sprint 4

La aplicación conserva la evidencia y los estados calculados por Python. Gemini solo redacta diagnóstico y recomendación sobre un resumen técnico agregado. La redacción requiere revisión del auditor y no es una medición de exactitud ni un dictamen de cumplimiento.

## Modelo y cuota gratuita

Se utiliza por defecto `gemini-3.5-flash-lite`, modelo estable con entrada/salida en cuota gratuita según la [tabla oficial de precios](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite), consultada el 12 de noviembre de 2026. La disponibilidad y los límites dependen del proyecto/cuenta y pueden cambiar. Verificar el nivel gratuito y los límites en Google AI Studio. El programa no habilita facturación, no cambia de modelo automáticamente y no puede asegurar coste cero si el proyecto ya tiene facturación de pago.

Google indica que el contenido del nivel gratuito puede utilizarse para mejorar sus productos. Por ello el programa no envía evidencia completa: usa exclusivamente el contexto descrito abajo. No habilitarlo para información cuya política interna prohíba enviar incluso estadísticas técnicas agregadas a un proveedor externo.

## Activar localmente

1. Crear la clave en [Google AI Studio](https://aistudio.google.com/apikey) y comprobar que el proyecto utiliza el nivel deseado.
2. Detener el backend con `Ctrl+C` si está ejecutándose.
3. Abrir `backend/.env` con un editor. Si no existe, copiar `backend/.env.example` a `.env`. El archivo local está excluido de Git y no debe compartirse. Es texto sin cifrar; no es un gestor de secretos.

```dotenv
GEMINI_ENABLED=1
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=
```

Pegar la clave real después del `=` de `GEMINI_API_KEY`, guardar y cerrar el editor. No ponerla en el frontend ni usar un nombre que comience por `VITE_`. La plantilla tiene `GEMINI_ENABLED=0`: cambiarlo a `1` para activar. No pegar la clave en este documento ni en comandos que queden en el historial.

4. En una terminal nueva, dentro de `backend`, ejecutar:

```powershell
.\.venv\Scripts\python.exe run_backend.py
```

El lanzador pedirá además la contraseña de PostgreSQL interno si no está configurada. La clave Gemini y esa contraseña son distintas. En desarrollo se carga `backend/.env` desde su ruta fija, independientemente de la carpeta desde la cual se invoque Python. Solo se leen las tres variables Gemini anteriores; admite `NOMBRE=valor`, valores entre comillas simples/dobles y líneas de comentario con `#`. No interpreta comandos, escapes o sustituciones ni admite comentarios al final de un valor. No carga credenciales de bases auditadas.

Las variables ya definidas en la terminal tienen prioridad sobre `.env`. Si se habían configurado con los comandos anteriores y se desea usar exclusivamente el archivo, eliminarlas antes de iniciar:

```powershell
Remove-Item Env:GEMINI_API_KEY, Env:GEMINI_ENABLED, Env:GEMINI_MODEL -ErrorAction SilentlyContinue
```

Reiniciar el backend después de editar `.env`; los valores ya cargados permanecen en el proceso. En producción no se lee este archivo: inyectar las variables de forma segura en el despliegue. La alternativa de configurar variables únicamente en PowerShell sigue funcionando.

Para deshabilitar Gemini, iniciar el backend con `GEMINI_ENABLED=0` o sin esa variable. Si se habilita sin clave válida, las actividades elegibles muestran un error de configuración de IA y conservan la evidencia SQL. `GEMINI_MODEL` permite seleccionar otro identificador de modelo estable; comprobar antes sus capacidades, cuotas y precio. No se aceptan rutas, URLs ni identificadores marcados como preview/experimental.

## Contexto enviado y trazabilidad

`app/ai_context.py` construye la versión `postgres-tecnico-contexto-v1` (criterios `gemini-criterios-v4`). Para `postgresql-tecnico-v1` se envían el nombre y entregable reformulados y se evalúa únicamente el alcance observable, sin exigir habilitar controles ni aportar documentos empresariales fuera del nuevo requisito. Ver [contrato y condición de cierre con IA](checklist-tecnico-v1.md). Para el checklist original se conservan sus criterios de alcance.

- Identificador conocido y tema fijo; número, nombre y entregable originales solo si coinciden con el catálogo A–E revisado. No se transmiten instrucciones arbitrarias del Excel.
- Estado SQL y de evidencia calculados por el motor.
- Por cada evidencia, una referencia ordinal, disponibilidad y naturaleza.
- Valores enteros/booleanos de primer nivel de una lista permitida explícita: por ejemplo, total de tablas, campos, FK, índices o disponibilidad de una ventana representativa.
- Longitudes de listas técnicas permitidas, sin sus elementos. Un conteo de elementos resumidos no garantiza objetos únicos.
- Hallazgos calculados por Python con descripciones fijas: visibilidad por permisos, grupos de índices candidatos, campos fuera de un patrón y diferencias de tipos entre FK. No inventa reglas ni umbrales de negocio. Se conserva la cobertura parcial declarada por el motor cuando corresponde.

Se agregan contadores técnicos de roles, privilegios, FK, huérfanos y extensiones conocidas; parámetros técnicos explícitamente permitidos, disponibilidad de consultas y requisitos externos fijos por actividad. No se envían credenciales, servidor, base, usuario, nombres de esquemas/tablas/campos/roles, comentarios, expresiones SQL, comandos de archivado, valores predeterminados ni registros de negocio. Los campos desconocidos se excluyen. Las limitaciones provienen del catálogo revisado, no de texto libre del Excel.

La evidencia original continúa disponible en resultados e historial privado. La redacción incorpora proveedor, modelo solicitado, versiones de contexto/criterios y referencias a las evidencias usadas. El detalle muestra E1, E2, etc. Python rechaza referencias inexistentes, repetidas o ausentes. Esta comprobación aporta trazabilidad; no demuestra que la prosa represente fielmente cada evidencia.

## Criterios de redacción `gemini-criterios-v4`

Se contrastaron con los alcances y limitaciones que ya expresa `audit_engine.py`; no se agregan umbrales nuevos ni reglas de negocio.

Las actividades de las ocho fases reciben criterios y requisitos externos específicos desde `ACTIVITY_CRITERIA` y `audit_catalog.EXTERNAL_REQUIREMENTS`. Por ejemplo, 3.3 distingue NOT NULL de validez de negocio, 4.4 trata FK sin índice como candidatas, 5.8 distingue tipo exacto de incompatibilidad y 8.3/8.4 separan WAL/replicación de backups utilizables y RPO/RTO probados. Las dos actividades necesariamente externas, sin evidencia SQL, no se envían a Gemini. No se calculan resultados ni estados mediante IA.

| Actividades | Criterios |
| --- | --- |
| 2.1–2.8 | Inventarios no confirman función empresarial; una instantánea no mide crecimiento histórico; contadores sin ventana representativa no prueban obsolescencia; esquema no equivale a módulo. |
| 3.1–3.9 | Los metadatos describen estructura, no validez de registros o reglas empresariales; nombres no confirman sensibilidad/deprecación; no se presupone una convención aprobada. |
| 4.1–4.8 | Los candidatos no justifican creación/eliminación de índices; requieren carga y planes revisados; estadísticas no prueban fragmentación exacta ni frecuencia histórica. |
| 5.1–5.8 | FK e indicios estructurales no prueban cardinalidad empresarial, normalización o necesidades funcionales; contrastar con responsables y carga. |

Para todas las actividades: describir únicamente la evidencia resumida; no calcular porcentajes ni resultados, no emitir SQL, no recomendar ejecución automática, no convertir ausencia de evidencia en conformidad/incumplimiento. No decidir la exactitud. Si la evidencia es parcial, decirlo y orientar la revisión manual. La protección no depende solo del prompt: los datos se filtran antes de enviarse y el modelo nunca recibe una conexión ni un mecanismo para ejecutar consultas.

## Ejecución y errores

Actualización del 17 de noviembre de 2026: si falla un lote enviado, sus actividades quedan en `error`; los lotes posteriores, que no llegaron a enviarse, quedan en `no_solicitada` y la interfaz muestra **Redacción pendiente**. No se atribuye un HTTP 503 a solicitudes inexistentes. Se conservan las redacciones ya generadas y la evidencia SQL; el resumen cuenta errores de IA únicamente en las actividades del lote fallido. Los registros históricos conservan la clasificación original, porque no contienen trazabilidad suficiente para reconstruir qué solicitudes se enviaron.

HTTP 503/UNAVAILABLE indica indisponibilidad o sobrecarga del servicio según [la documentación oficial de Gemini](https://ai.google.dev/gemini-api/docs/generate-content/api-errors?hl=en); no es un error SQL. El análisis forma parte de la ejecución y una etapa interrumpida sin error definitivo se recupera automáticamente al abrir el resultado, sin botón manual. Ver [diagnóstico por archivo](diagnostico-ia-pendiente.md) y [política de recuperación y pruebas](recuperacion-ia.md). El comando `python -m scripts.check_gemini` sigue siendo una prueba independiente con datos ficticios y puede consumir cuota; no modifica resultados guardados.

Después de finalizar las consultas y cerrar la conexión auditada se envían lotes secuenciales de hasta doce actividades con evidencia procesable. Una auditoría completa puede requerir seis solicitudes; considerar la cuota de la cuenta. Ante error se detienen los lotes pendientes y se preservan los ya generados. Actividades sin catálogo, sin evidencia o con error SQL no se envían.

La API REST se invoca por HTTPS a un destino fijo, con clave en una cabecera y sin herramientas o búsqueda. No se siguen redirecciones. Cada lote limita contexto a 96 KiB y respuesta a 256 KiB, con socket de veinte segundos y cierre programado a los treinta segundos. La cola mantiene el turno hasta que termina el hilo de red.

Se solicita JSON con `responseMimeType` y un `responseSchema` sencillo del subconjunto OpenAPI admitido por Gemini. No se envían `$defs`, `$ref` ni restricciones de longitud generadas por Pydantic. Python exige una entrada por identificador solicitado, diagnóstico/recomendación, referencias de evidencia válidas, textos no vacíos de hasta 1500 caracteres y finalización completa. Se rechazan duplicados, identificadores ajenos, campos adicionales, bloqueos y respuestas truncadas. Esto valida la estructura; no certifica la veracidad de la prosa.

Cuota agotada (429), permisos, indisponibilidad, formato inválido o tiempo agotado se conservan como causas de IA. La cola realiza hasta tres intentos por lote ante errores transitorios con backoff, jitter y `Retry-After`. No reintenta automáticamente errores de configuración o respuesta inválida ni cambia de modelo. La evidencia se guarda antes de IA y cada lote válido se guarda después. El tiempo SQL permanece en `duracion_total_ms`; el tiempo acumulado IA va en `duracion_ia_ms`, sin repartir artificialmente un tiempo de lote entre actividades.

## Prueba manual

Si aparece un error genérico de IA, ejecutar desde `backend`, en otra terminal:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_gemini
```

Carga la misma configuración de `.env` en desarrollo. Si no encuentra la clave allí ni en el entorno, la solicita de forma oculta. Realiza una única solicitud con datos ficticios al modelo de `GEMINI_MODEL` (o al predeterminado), valida la misma salida estructurada que usa la auditoría y muestra un resultado seguro. Puede consumir cuota; no conecta con PostgreSQL ni ejecuta una auditoría. La ejecución explícita de este comando habilita la llamada de prueba en su proceso, incluso si `GEMINI_ENABLED=0` deshabilita la IA del servidor. No compartir la clave ni usar comandos que la impriman.

Los errores incluyen el código HTTP y, cuando se reconoce, el estado de la API: 400 indica solicitud inválida o requisitos del proyecto y también puede corresponder a una clave inválida/expirada; 404 indica que el modelo/ruta no está disponible para ese proyecto/API y 503 indica un problema de disponibilidad. Revisar el diagnóstico antes de cambiar de modelo; no se selecciona otro automáticamente.

El comando local muestra además el mensaje técnico de Google, limitado a 1200 caracteres y con la clave, URLs, correos y rutas de proyecto ocultos. No imprime cabeceras, metadatos ni la respuesta completa. Este detalle no se devuelve al frontend. Permite conocer, por ejemplo, un campo rechazado sin repetir el diagnóstico genérico.

Con backend y frontend iniciados, importar el Excel y ejecutar una auditoría sobre una base autorizada con usuario de lectura. En Resultados → Ver, comprobar evidencia, diagnóstico y recomendación. Si falla la cuota o la clave, debe aparecer «Error de IA» y seguir disponible la evidencia. Comprobar los textos como auditor; no confundir la cobertura del catálogo con exactitud ni con éxito de la redacción.

Las pruebas automatizadas usan respuestas simuladas y verifican filtrado, esquema, errores, conservación de evidencia y cierre de conexión antes de la IA. No utilizan una clave real ni consumen cuota. La validación real contra Gemini queda pendiente de configurar la clave localmente.

Referencias de implementación: [API generateContent](https://aistudio.google.com/api-reference/generate-content), [salida estructurada](https://aistudio.google.com/docs/structured-output) y [manejo de claves](https://aistudio.google.com/docs/api-key).
