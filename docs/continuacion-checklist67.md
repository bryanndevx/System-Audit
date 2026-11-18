# Checklist de 67 actividades: implementación y validación

Este documento conserva el alcance del checklist original. Para las nuevas actividades reformuladas rige [PostgreSQL técnico v1](checklist-tecnico-v1.md). La nueva instrucción también revoca la excepción de superusuario descrita a continuación: ahora se rechaza incluso si confirma el aviso. Los registros históricos no se modifican.

## Actualización autorizada — 17 de noviembre de 2026

La conexión detecta los cinco atributos administrativos y solicita confirmación mediante un modal. La opción recomendada es **Cambiar usuario**; **Entiendo, continuar en lectura** permite volver a verificar la cuenta conservando transacciones de lectura, timeout, destinos permitidos y política TLS. Esta excepción fue solicitada explícitamente por el usuario y sustituye el rechazo incondicional anterior de cuentas elevadas. No convierte al superusuario en un rol de privilegios mínimos.

La API responde 409 con `elevated_privileges_confirmation_required` y etiquetas de privilegios, sin credenciales. El campo booleano estricto `conexion.confirmar_privilegios_elevados` vale `false` por defecto y debe aceptarse explícitamente para comprobar y ejecutar con una cuenta elevada. Editar los datos o comenzar otra auditoría descarta la aceptación en la interfaz; el backend revalida los atributos en cada conexión. No se guarda la contraseña ni la aceptación como preferencia permanente. La API permite que un cliente autenticado envíe la confirmación explícita; no depende de que use esta interfaz.

Verificación de esta actualización: 183 pruebas unitarias aprobadas; navegador con servicios simulados verificó modal, Escape, foco, bloqueo previo, aceptación, invalidación al editar y presentación móvil. Compilación y lint del frontend comprobados. No se realizó conexión a SmartDent.

Se revisaron las columnas A–E de la hoja `Checklist Maestro`. El catálogo conserva fase, número de hoja, identificador compuesto, nombre, entregable y prioridad en `backend/app/checklist_catalog.json`. F/G/H no se importan como resultados. El Excel y `docs/documentacion.docx` permanecen como referencias locales excluidas de Git. El Word solo orienta la estructura documental; no se copiaron resultados históricos.

## Resultado comprobado y criterio

Prueba con PostgreSQL 18, instancia aislada, cuatro fixtures ficticias y usuario lector sin privilegios administrativos:

| Cobertura del entregable | Actividades |
| --- | ---: |
| Completa dentro del alcance técnico declarado | 10 |
| Parcial: hay evidencia PostgreSQL y verificaciones pendientes | 55 |
| Necesariamente externa, sin consulta que complete el entregable | 2 |
| Error SQL | 0 |
| Sin configuración | 0 |
| Total | 67 |

Automatización completa = 10 / 67 × 100 = **14,93 %**. No es una meta ni porcentaje de exactitud. Cada ejecución recalcula la cobertura según su evidencia, permisos, límites y correspondencia con el entregable revisado. Un error de Gemini no modifica estos resultados. Consultas completadas no equivalen a actividad completamente automatizada.

Los diez entregables completos son 2.1, 3.1, 3.2, 3.3, 4.1, 4.2, 5.8, 7.1, 7.2 y 8.1. Se refieren a inventarios técnicos declarados: tablas por esquema, campos/orden, tipos y dimensiones declaradas, obligatoriedad, índices, PK/FK, comparación de tipos de FK, restricciones y valores predeterminados, configuración de FK y matriz de roles/membresías/permisos declarados. No certifican uso empresarial, validez de registros ni permisos de infraestructura. Las actividades 1.2 y 8.9 requieren respectivamente arquitectura de capas y procedimiento formal de gestión de cambios.

La revisión individual, consultas y requisitos externos están en [catalogo-67-actividades.md](catalogo-67-actividades.md). Los demás checklists siguen siendo importables, hasta cien actividades; un número desconocido queda sin configuración. Si nombre, fase o entregable no coinciden con la definición revisada, nunca se acredita cobertura completa por compartir el número.

## Motor y seguridad

- Consultas predefinidas revisadas; conexión independiente protegida por transacciones de solo lectura, allowlist de destinos, validación SSRF, rol mínimo y TLS según entorno. No se agregan conexiones a SmartDent ni a producción.
- La sesión fija `search_path=pg_catalog` para resolver funciones internas en un esquema de confianza. Los parámetros observados son efectivos en esa sesión: por ejemplo `statement_timeout` incluye la protección del auditor y no demuestra el valor predeterminado del servidor. Se conserva el origen del parámetro cuando está disponible.
- Cada resultado conserva entregable, prioridad, número original de la hoja, evidencias, limitaciones y trazabilidad de consultas: ID, estado, filas, duración y reutilización.
- Máximo 5000 filas por consulta y seis segundos de espera en Python, además del timeout de sesión PostgreSQL. El exceso se marca parcial; no se presentan los totales del subconjunto como inventario completo.
- Las consultas repetidas se reutilizan dentro de una ejecución; la caché termina con ella. No se conservan credenciales ni una caché compartida entre auditorías. No se garantiza una instantánea transaccional única para todas las consultas; las estadísticas pueden cambiar durante el recorrido.
- La 7.3 agrega conteos de huérfanos para hasta diez FK declaradas mediante una plantilla SELECT revisada y `psycopg.sql.Identifier`. Identificadores provienen de catálogos, nunca de IA ni SQL del formulario. Se omiten FDW, tipos personalizados, visibilidad RLS incompleta y permisos insuficientes. No se devuelven registros de negocio ni se inventan reglas de duplicidad.
- Excel: máximo comprimido configurable de 5 MiB por defecto, expansión máxima 30 MiB, 2000 entradas ZIP, 5000 filas y cien actividades. Solo se leen columnas A–H; F/G/H se descartan. Se rechazan excesos completos, sin recortar requisitos.

No se reprodujo un error SQL en 2.2 en las pruebas reales. Se verificaron sus cinco consultas, clasificación conservadora, ambigüedades y herencia de particiones; su cobertura sigue siendo parcial porque el propósito empresarial requiere validación. Un error futuro por permisos/timeout conserva su estado técnico y trazabilidad.

## Gemini

Las 65 actividades con evidencia procesable pueden recibir redacción. El contexto contiene número/nombre/entregable oficial cuando coincide con el catálogo, indicadores agregados calculados en Python, parámetros técnicos permitidos, disponibilidad y requisitos externos. No se envían identidades de objetos/roles, valores de negocio, SQL, comentarios, cuerpos de rutinas, comandos de archivado ni credenciales.

Se envían lotes de hasta doce actividades, secuenciales y sin reintentos automáticos. Una auditoría completa puede requerir hasta seis solicitudes: tenerlo presente al usar cuota gratuita. Cada lote tiene límite de contexto/respuesta y treinta segundos de espera. Ante error se preservan los lotes anteriores y se marcan las redacciones pendientes; la evidencia SQL permanece disponible. Las pruebas de esta entrega simulan Gemini y no consumieron cuota real. La revisión semántica de recomendaciones reales sigue correspondiendo al auditor.

Backups y continuidad distinguen parámetros, contadores y capacidad técnica de una estrategia probada. No se ejecutan copias/restauraciones ni se cambian WAL o archivado. No se afirma que pgBackRest esté instalado, que existan copias utilizables, PITR operativo o RPO/RTO definidos. Tampoco se descartan backups externos por falta de visibilidad PostgreSQL.

## Progreso y PDF

`POST /api/audits/execute-stream` transmite eventos NDJSON: actividad terminada, etapa y resultado final guardado. El avance muestra procesadas/total; no estima automatización. La desconexión cancela la tarea activa; no hay servicio de trabajos en segundo plano. Si la conexión termina al guardar, consultar historial antes de repetir. `/execute` continúa disponible para clientes existentes.

`GET /api/audits/{uuid}/pdf` exporta exclusivamente el resultado guardado del propietario autenticado. No abre la base auditada ni llama a Gemini. Sin sesión devuelve 401 y un registro ajeno/inexistente devuelve 404. El nombre de aplicación y entorno son opcionales; si faltan se indica explícitamente, sin asumir SmartDent.

ReportLab genera portada, resumen, fases/actividades en orden, entregables, tablas adaptadas, relaciones FK observadas, diagnóstico, recomendación, limitaciones, trazabilidad, conclusiones y anexos. Las matrices anchas se dividen en grupos con identificación de fila; tablas largas repiten encabezado y pueden dividir filas altas. Los anexos idénticos se comparten sin omitir la referencia. Los diagramas muestran hasta veinte relaciones y conservan la matriz completa obtenida; no acreditan un ER funcional completo. La cantidad de páginas depende del inventario; se conservan evidencias extensas en vez de truncarlas silenciosamente.

## Cómo ejecutar y probar

Detener el backend anterior con Ctrl+C en su terminal. Desde la raíz:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Si el historial aún no está preparado, ejecutar una vez en la base interna:
.\.venv\Scripts\python.exe -m scripts.apply_history_migration
.\.venv\Scripts\python.exe run_backend.py
```

En otra terminal, desde la raíz:

```powershell
cd frontend
npm run dev
```

Abrir `http://localhost:5173`, importar el Excel, probar conexión autorizada de lectura, ejecutar, verificar cobertura y abrir detalles. Con el resultado guardado, usar **Exportar PDF**; también funciona desde historial. Para Gemini configurar `backend/.env` según [ia-gemini.md](ia-gemini.md), sin pegar la clave en terminales compartidas o repositorios.

Comprobaciones automatizadas:

Resultado final: **179 pruebas unitarias aprobadas**, seis de integración real en PostgreSQL 18 aprobadas, compilación de producción y ESLint correctos, dependencias sin incompatibilidades detectadas por `pip check`. También se completaron los recorridos HTTP y de navegador descritos abajo. Estos resultados no certifican una base real ni la calidad semántica de respuestas reales de Gemini.

```powershell
# Desde backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# Desde frontend
npm run build
npm run lint
```

Integración: las pruebas `tests/integration/test_audit_engine.py` y `test_catalog67.py` requieren `RUN_AUDIT_INTEGRATION=1` y variables `AUDIT_TEST_HOST`, `AUDIT_TEST_PORT`, `AUDIT_TEST_DATABASE`, `AUDIT_TEST_USER`, `AUDIT_TEST_PASSWORD` mediante un entorno seguro. Preparar las cuatro fixtures de `tests/fixtures/` exclusivamente en una instancia ficticia aislada, antes de conceder lectura. Nunca instalar fixtures en SmartDent. Las cinco pruebas previas y la nueva prueba de 67 actividades pasaron con PostgreSQL 18. La referencia independiente de controles contiene una FK NOT VALID, exactamente un huérfano y una sesión sin TLS; el motor los distinguió correctamente.

Además se probó por HTTP real: autenticación, migración idempotente, persistencia tras reiniciar PostgreSQL, paginación, aislamiento por usuario, 67 eventos de avance, guardado/reapertura y PDF privado sin repetir ejecución. En Chrome se verificaron importación, transmisión de entregables/prioridades, ocho fases, modal 2.2, móvil sin desbordamiento, descarga y ausencia de errores JavaScript. Las respuestas del servicio se simularon para esa revisión visual; el recorrido HTTP independiente sí usó FastAPI/PostgreSQL reales. Artefactos ficticios y capturas permanecen en `local-data/`, excluidos de Git.

Pendientes externos: validar consultas en otras versiones PostgreSQL y bases de mayor tamaño, aportar documentación de negocio/infraestructura para completar los 55 entregables parciales y dos externos, revisión semántica de Gemini con la cuenta del usuario y ensayo autorizado sobre una base real. No se estimó exactitud de datos reales ni se accedió a producción. No se realizó `git push`.

Referencias técnicas: [estadísticas y visibilidad PostgreSQL](https://www.postgresql.org/docs/18/monitoring-stats.html), [esquemas de confianza y search_path](https://www.postgresql.org/docs/18/ddl-schemas.html), [ReportLab 5.1.0](https://pypi.org/project/reportlab/5.1.0/).
