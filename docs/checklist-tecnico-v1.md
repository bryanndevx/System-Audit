# Checklist PostgreSQL técnico v1

Versión de requisitos: **postgresql-tecnico-v1**. Criterio de evaluación: **evaluacion-observable-ia-v1**. Esta versión fue solicitada explícitamente el 17 de noviembre de 2026 y sustituye el alcance empresarial únicamente en las nuevas auditorías que importen esta versión.

El archivo importable es [`frontend/referencias/checklist_postgresql_tecnico_v1.xlsx`](../frontend/referencias/checklist_postgresql_tecnico_v1.xlsx). Contiene 67 actividades, ocho fases e identificadores 1.1–8.10, con los nombres y entregables exactos de la nueva solicitud. F/G/H están vacías. Se conservaron los nombres de fase y prioridades originales porque la reformulación no propuso otras prioridades. No se sobrescribió `checklist_bd_smardent.xlsx` ni se copiaron sus resultados históricos.

Los requisitos legibles por máquina están en `backend/app/technical_checklist_v1.json`. La hoja `Version` contiene ID y SHA-256 de los requisitos y del identificador de criterio. El importador comprueba la lista completa, sus textos, entregables, prioridades y orden; rechaza un archivo versionado alterado. La API también comprueba la versión, aunque se omita la interfaz. No acepta una mezcla de actividades técnicas con el alcance anterior. Un Excel sin metadatos pero con los requisitos exactos puede identificarse por su contenido.

La versión original sigue soportada. Las auditorías guardadas no se actualizan ni se recalculan al abrirlas; las que no registraron versión se presentan como históricas. El historial, el resultado y la portada del PDF identifican la versión cuando existe. No comparar porcentajes del checklist original con los de esta reformulación como si midieran el mismo alcance.

## Estados y medición

Solo se presentan dos estados por actividad:

- **Completada**: todas las evidencias necesarias se obtuvieron dentro del alcance técnico, sin errores ni truncamiento pendientes, y existe diagnóstico/recomendación IA válidos con referencias a evidencias existentes.
- **Incompleta**: falta información externa o la evaluación no pudo terminar por otro motivo. Se conservan evidencias y la causa interna: permisos, error SQL/conexión, límite de recursos, formato de historial no reconocido o IA no disponible.

Un control ausente, deshabilitado o deficiente no impide completar su evaluación. Ejemplos: SSL off; sesión sin TLS; archive_mode off; vista materializada no poblada; extensión de estadísticas no instalada. No se corrigen esos controles desde la auditoría. La ausencia de estadísticas se documenta con su alcance; no se inventa carga ni hit ratio cuando no existe denominador.

Para esta lista completa: `automatización = completadas / 67 × 100`. Se registra también incompletas y tiempo total de proceso (`duracion_ejecucion_ms`: conexión, evidencia e IA, hasta preparar el guardado), además de las duraciones SQL e IA separadas. Guardado, descarga de PDF y tiempo del navegador no forman parte de esa medición. La suficiencia técnica intermedia no cuenta por sí sola como automatización final. Si Gemini falla o está deshabilitado, la actividad permanece incompleta aunque todas sus consultas hayan funcionado.

La nueva versión no puede usarse para cambiar a mitad de una medición los requisitos del experimento anterior. Antes de medir, fijar este Excel y su huella, la versión de código, los criterios, permisos y condiciones de captura. La auditoría manual y la automática deben utilizar los mismos requisitos. Una modificación posterior requiere una versión nueva, no editar silenciosamente v1.

## Evidencias implementadas por fase

| Fase | Alcance y consolidaciones |
| --- | --- |
| 1 — 8 actividades | Identificación/compilación PostgreSQL, bases/esquemas/relaciones, propietarios y objetos por esquema, organización observable, extensiones/FDW/servidores/publicaciones/suscripciones, configuración, historial de migración reconocido y patrón sintáctico de nombres. PostgreSQL no ofrece un campo universal de edición comercial; se registra la identificación reportada y no se inventan proveedor/licencia. |
| 2 — 8 actividades | Inventario estructural y particiones, clasificación técnica con ambigüedades explícitas, tamaños/estimaciones actuales con fecha de captura, estadísticas y dependencias, FK, trazabilidad, vistas/materializadas, rutinas/triggers. No se confirma propósito empresarial ni desuso a partir de nombres. |
| 3 — 9 actividades | Columnas, tipos/dimensiones, nulabilidad, defaults/dominos/ENUM/CHECK, generated/identity, controles declarativos, sensibilidad preliminar por nombres/tipos/comentarios, coherencia sintáctica y candidatos sin comentarios/con dependencias limitadas. No se leen registros clínicos ni se afirma que una columna esté deprecada. |
| 4 — 8 actividades | Diseños de índices, PK/FK/UNIQUE, coincidencias estructurales y uso condicionado a la ventana estadística, FK sin soporte como candidatos, disponibilidad y métricas accesibles de pg_stat_statements, mantenimiento observable, índices compuestos/parciales/funcionales/INCLUDE y particiones con límites/tamaños. No se mide fragmentación exacta ni se propone eliminación automática. |
| 5 — 8 actividades | ER físico con entidades, PK y FK, incluyendo entidades aisladas, indicios estructurales, referencias candidatas, cardinalidad física, relaciones/tipos entre esquemas, tablas puente candidatas, generación/composición de PK y comparación de FK. No se inventan relaciones de negocio. |
| 6 — 8 actividades | Sesiones agregadas sin texto SQL, I/O/cache/actividad, capacidad puntual, materializadas, propiedades de rutinas, columnas temporales candidatas a retención, hit ratios calculados en Python, parámetros efectivos y matriz provisional de hallazgos con referencia a evidencia fuente. |
| 7 — 8 actividades | Restricciones, configuración/validación/acciones de FK, prevención declarativa de integridad, candidatos maestros por estructura, controles de BD, capacidades transaccionales configuradas, reglas declaradas de tipos/rangos y migraciones/dependencias. La 7.3 nueva no ejecuta conteos costosos de registros: evalúa capacidad declarativa, conforme a su entregable reformulado. |
| 8 — 10 actividades | Roles/membresías/privilegios, SSL y TLS de sesión, WAL/archivado, replicación/slots/receptor, extensiones/logging/triggers, RLS/políticas, alcance lógico de instancia/bases, versionado detectable y controles de cambio/protección observables. No se certifica cumplimiento normativo ni anonimización de registros. |

`audit_technical.PLANS` define las consultas de las actividades nuevas y reutiliza las transformaciones existentes para inventarios, diccionario, índices y modelo. La traza guardada identifica cada consulta efectivamente usada, duración, disponibilidad y reutilización. No hay un máximo de consultas por actividad; sí límites de recursos por consulta: 5000 filas, timeout de sesión y espera Python. Se informa cualquier truncamiento y la actividad no cuenta como completada.

## Migraciones y estadísticas

Se reconocen metadatos estándar de Alembic, Django, Flyway, Liquibase, Prisma, schema_migrations, Knex y Sequelize. Las tablas y columnas se identifican desde catálogos. Se leen únicamente columnas permitidas de versión/estado/fecha mediante plantillas SELECT revisadas e identificadores escapados; nunca cuerpos SQL, autores, contraseñas, logs o cadenas de conexión. Hay un límite de veinte historiales por captura; superar ese límite deja la evaluación incompleta. Si no hay historiales reconocidos, se documenta ese resultado sin afirmar que no existan migraciones externas o propias. Si existe uno sin permisos o con un formato incompatible, se conserva la razón y se solicita acceso o una exportación técnica autorizada.

Para pg_stat_statements se evalúa primero la capacidad. Si está ausente o no precargada, se documenta el mecanismo no operativo. Si está instalada y operativa, se leen ID y métricas numéricas de consultas de la base conectada, sin texto SQL ni identidades de sesiones. Permisos insuficientes no se disfrazan de extensión ausente. El auditor nunca instala extensiones ni reinicia PostgreSQL.

## IA, hallazgos y continuidad

Gemini recibe la versión y el entregable técnico correspondiente, indicadores permitidos calculados en Python, condiciones observadas y notas de alcance. No recibe credenciales, datos de pacientes, texto SQL, comentarios de objetos, logs ni nombres de objetos/roles innecesarios. La salida debe tener diagnóstico, recomendación y referencias válidas. La validación estructural no certifica la calidad semántica; la redacción requiere revisión del auditor.

La evidencia se guarda antes de solicitar IA y las narrativas se guardan por lote. La recuperación de textos pendientes reutiliza el mismo registro, sin repetir SQL: [recuperación Gemini, reintentos y pruebas](recuperacion-ia.md).

La matriz 6.8 se consolida después de obtener todas las evidencias. Reglas documentadas: criticidad alta provisional para FK no validadas/triggers FK no activos, índices inválidos/no preparados y fsync/full_page_writes off; media para TLS/SSL o archivado deshabilitados; baja para roles administrativos a revisar y materializadas no pobladas. La prioridad es provisional, no un incumplimiento empresarial confirmado ni una orden de cambio. Cada fila referencia actividad y evidencia fuente; la cobertura de fuentes incompletas queda registrada.

WAL y archivado no prueban copias utilizables ni PITR operativo. Replicación no define ni valida RPO/RTO. No se descartan backups externos por no observarlos. pgBackRest puede ser una alternativa a evaluar, no una instalación asumida o una solución obligatoria. El sistema no crea copias, restaura, altera WAL ni habilita TLS.

La conexión conserva allowlist/SSRF, política TLS, credenciales efímeras, transacciones de lectura y timeouts. Conforme a la nueva instrucción, una cuenta superusuario se rechaza incluso si confirma el aviso; la opción de continuar no aparece en ese caso. Los fixtures se preparan con un operador únicamente antes de auditar una instancia ficticia; la ejecución del motor utiliza roles lectores.

## Pruebas y resultados

Las pruebas nuevas cubren versión/huella y rechazo de mezclas/alteraciones, estados según evidencia + IA, controles habilitados/deshabilitados, ausencia de estadísticas, permisos, plantillas de historial, privacidad, ER físico y generación de PDF. Se conserva la suite de regresión del checklist original.

Resultado de verificaciones: **202 pruebas unitarias aprobadas**, ocho pruebas de integración aprobadas en cada variante preparada, build y lint del frontend correctos, dependencias compatibles según `pip check`. Los artefactos ficticios y capturas permanecen en `local-data/`, excluidos de Git. No hay dependencias nuevas en esta actualización.

En PostgreSQL 18 aislado, base ficticia `auditoria_prueba`, se ejecutaron dos variantes: pg_stat_statements ausente y habilitada. Ambas obtuvieron evidencia suficiente para las 67 actividades. Con respuestas de IA **simuladas y validadas**: 67 completadas, 0 incompletas, 100 %. Con IA simulada no disponible: 0 completadas, 67 incompletas, 0 %, preservando toda la evidencia. Un rol adicional sin acceso al historial dejó las actividades de migración incompletas por permisos. Estos resultados validan el funcionamiento bajo fixtures; no son una medición de tesis con Gemini real ni resultados de SmartDent.

También se probó el flujo HTTP real con IA deshabilitada: versión, 67 eventos, resultado incompleto correctamente, historial privado y PDF sin repetir consultas. El recorrido de navegador usa respuestas ficticias y comprueba estado Completada con evidencia + narrativa, dos estados visibles, versión, móvil, ER y exportación.

No se accedió a SmartDent ni producción, no se consumió cuota Gemini y no se realizó git push. Pendientes: prueba con la cuenta real de Gemini y revisión semántica del auditor, otras versiones PostgreSQL, formatos propios de migración y bases de mayor volumen. No se extrapola el 100 % de fixtures a esas condiciones.

## Cómo probar

1. Detener y reiniciar el backend con `.\.venv\Scripts\python.exe run_backend.py` desde `backend`.
2. Recargar el frontend; importar `checklist_postgresql_tecnico_v1.xlsx` y comprobar que muestre `postgresql-tecnico-v1`.
3. Probar la conexión autorizada con una cuenta lectora, ejecutar y revisar diagnóstico/recomendación. Una clave de Gemini configurada no garantiza disponibilidad ni cuota.
4. Abrir historial y exportar PDF; verificar versión, huella y que no se ejecuten nuevas consultas al exportar.

Pruebas: `python -m unittest discover -s tests -v`; integración opt-in con `RUN_AUDIT_INTEGRATION=1`, variables `AUDIT_TEST_*`, fixtures exclusivamente ficticias y `tests.integration.test_technical_checklist`. `AUDIT_METADATA_ONLY_USER` habilita el caso de historial sin permisos. Desde frontend ejecutar `npm run build` y `npm run lint`.

Referencias de consultas y criterios: [pg_stat_statements](https://www.postgresql.org/docs/18/pgstatstatements.html), [identificación del sistema](https://www.postgresql.org/docs/18/functions-info.html), [estadísticas](https://www.postgresql.org/docs/18/monitoring-stats.html), [restricciones](https://www.postgresql.org/docs/18/ddl-constraints.html).

## Archivos principales de esta actualización

- Requisitos/versionado: `technical_checklist_v1.json`, `checklist_versions.py`, `checklists.py`, generador `scripts/create_technical_checklist.py` y Excel nuevo.
- Evidencias: `audit_technical.py`, `audit_technical_queries.py`, `audit_technical_templates.py`; integración con `audit_engine.py` y cierre en `audit_coverage.py`.
- IA, API, historial y PDF: `ai_context.py`, `audits.py`, `audit_history.py`, `audit_pdf.py`; política de conexión en `external_connections.py`.
- Frontend: `NewAudit`, `AuditResults`, `ActivityDetail`, `AuditProgress`, `Dashboard`, `ElevatedPrivilegesDialog`, `EvidenceViewer`, `ObservedRelations`, tipos y presentación.
- Pruebas nuevas: `test_technical_checklist.py` unitario y de integración, fixture técnica y ajuste explícito del caso superusuario. Se preservaron las pruebas y requisitos históricos.
