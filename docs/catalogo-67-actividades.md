# Revisión individual de las 67 actividades

Revisión adicional del 17 de noviembre: ver [estado del entregable, análisis de las ocho fases y cinco consultas adicionales](revision-entregables.md). Los IDs originales y entregables se conservan; la falta de información externa se muestra como entregable incompleto, aun cuando sus consultas se hayan completado.

Fuente de requisitos: exclusivamente A–E del checklist. Sin resultados históricos. Las capacidades siguientes se revisaron por entregable; el resultado de una ejecución puede degradarse por permisos, errores o límites. Los IDs de consultas corresponden a SELECT revisados o a la plantilla de conteo FK con identificadores escapados.

## 1. Arquitectura del Software

### 1.1 — Documentar stack tecnológico completo: motor de BD, versión, ORM/framework, lenguaje backend

**Entregable:** Ficha técnica de arquitectura. **Prioridad:** Alta. **Número en la hoja:** 1.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `server_facts`, `extensions`.

**Alcance/verificación pendiente:** Repositorio y responsable técnico: ORM, framework y lenguaje backend no son identificables por el motor PostgreSQL.

### 1.2 — Elaborar diagrama de arquitectura general (capas: presentación, negocio, datos, integración)

**Entregable:** Diagrama de arquitectura. **Prioridad:** Alta. **Número en la hoja:** 2.

**Capacidad:** Necesariamente externa.

**Evidencias predefinidas:** Sin SELECT capaz de producir este documento empresarial.

**Alcance/verificación pendiente:** Se necesita el diseño de capas de la aplicación y sus integraciones; un diagrama ER no constituye ese entregable.

### 1.3 — Identificar el tipo de arquitectura (monolito, microservicios, multi-tenant, multi-empresa)

**Entregable:** Nota técnica. **Prioridad:** Media. **Número en la hoja:** 3.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `server_facts`, `user_schemas`, `partition_configuration`.

**Alcance/verificación pendiente:** Repositorio y documentación de despliegue para confirmar monolito, microservicios o aislamiento empresarial.

### 1.4 — Mapear conexiones e integraciones externas (APIs, webhooks, otros sistemas, colas de mensajería)

**Entregable:** Mapa de integraciones. **Prioridad:** Alta. **Número en la hoja:** 4.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `foreign_servers`, `extensions`.

**Alcance/verificación pendiente:** Contrastar FDW y extensiones con APIs, webhooks, colas y conexiones definidas en la aplicación.

### 1.5 — Documentar ambiente(s) de despliegue: servidor, cloud/on-premise, contenedores, balanceo

**Entregable:** Ficha de infraestructura. **Prioridad:** Media. **Número en la hoja:** 5.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `server_facts`, `engine_configuration`.

**Alcance/verificación pendiente:** Inventario de infraestructura para identificar servidor, cloud, contenedores y balanceadores.

### 1.6 — Identificar y listar esquemas/bases de datos por módulo o dominio funcional

**Entregable:** Mapa de esquemas. **Prioridad:** Alta. **Número en la hoja:** 6.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `user_schemas`, `table_inventory`.

**Alcance/verificación pendiente:** Validar con negocio la correspondencia entre esquemas y dominios funcionales.

### 1.7 — Registrar la versión actual del modelo de datos y su historial de cambios mayores

**Entregable:** Bitácora de versiones. **Prioridad:** Media. **Número en la hoja:** 7.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `migration_candidates`, `server_facts`.

**Alcance/verificación pendiente:** Repositorio de migraciones y bitácora aprobada; los nombres de tablas no demuestran versiones aplicadas.

### 1.8 — Documentar convenciones de nomenclatura utilizadas (tablas, campos, prefijos, idioma)

**Entregable:** Guía de convenciones. **Prioridad:** Media. **Número en la hoja:** 8.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_columns`.

**Alcance/verificación pendiente:** Guía de nomenclatura aprobada; los patrones observados no constituyen una convención empresarial.

## 2. Inventario de Base de Datos (Tablas)

### 2.1 — Listar todas las tablas existentes agrupadas por esquema/módulo funcional

**Entregable:** Inventario de tablas. **Prioridad:** Alta. **Número en la hoja:** 1.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `user_schemas`, `table_inventory`.

**Alcance/verificación pendiente:** Inventario de metadatos declarados de la base conectada. No acredita reglas de negocio, calidad de registros ni objetos ajenos al alcance visible.

### 2.2 — Clasificar cada tabla: maestra, transaccional, catálogo/parametría, auditoría, temporal/staging

**Entregable:** Matriz de clasificación. **Prioridad:** Alta. **Número en la hoja:** 2.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_columns`, `table_constraints`, `table_foreign_keys`, `table_relation_properties`.

**Alcance/verificación pendiente:** Validación funcional de la clasificación; nombres, persistencia y relaciones son indicios, no propósito confirmado.

### 2.3 — Registrar volumetría actual (cantidad de registros) y tasa de crecimiento estimada

**Entregable:** Reporte de volumetría. **Prioridad:** Media. **Número en la hoja:** 3.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `database_size`, `database_statistics_context`, `table_volumetry`.

**Alcance/verificación pendiente:** Serie temporal comparable y registros de crecimiento; reltuples es una estimación, no un conteo exacto.

### 2.4 — Identificar tablas obsoletas, huérfanas o sin uso activo en la aplicación

**Entregable:** Lista de tablas candidatas a baja. **Prioridad:** Media. **Número en la hoja:** 4.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `database_statistics_context`, `table_usage_statistics`, `table_foreign_keys`, `view_dependencies`, `table_trigger_inventory`, `table_routine_dependencies`.

**Alcance/verificación pendiente:** Carga representativa y revisión del código; ausencia de uso estadístico no demuestra obsolescencia.

### 2.5 — Documentar la relación tabla ↔ módulo/funcionalidad de negocio que la origina

**Entregable:** Matriz tabla-módulo. **Prioridad:** Alta. **Número en la hoja:** 5.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_foreign_keys`, `view_inventory`, `view_dependencies`, `table_trigger_inventory`, `table_comments`, `table_routine_dependencies`.

**Alcance/verificación pendiente:** Mapa de funcionalidades del backend y confirmación de responsables de cada módulo.

### 2.6 — Identificar tablas de log, auditoría y trazabilidad de cambios

**Entregable:** Lista de tablas de auditoría. **Prioridad:** Media. **Número en la hoja:** 6.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_columns`, `table_constraints`.

**Alcance/verificación pendiente:** Validar propósito, cobertura y efectividad de las tablas candidatas con el diseño de auditoría.

### 2.7 — Mapear vistas (views) existentes, su propósito y tablas origen

**Entregable:** Inventario de vistas. **Prioridad:** Media. **Número en la hoja:** 7.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `view_inventory`, `view_dependencies`.

**Alcance/verificación pendiente:** Documentación funcional para confirmar el propósito de cada vista, además de sus dependencias declaradas.

### 2.8 — Inventariar procedimientos almacenados, funciones y triggers, con su propósito

**Entregable:** Inventario de objetos programables. **Prioridad:** Alta. **Número en la hoja:** 8.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `routine_inventory`, `routine_dependencies`, `table_trigger_inventory`, `event_trigger_inventory`.

**Alcance/verificación pendiente:** Revisión del código y documentación funcional para confirmar propósito y cobertura de rutinas y triggers.

## 3. Documentación de Campos (Diccionario de Datos)

### 3.1 — Listar todos los campos de cada tabla con su orden y tabla de origen

**Entregable:** Diccionario de datos - base. **Prioridad:** Alta. **Número en la hoja:** 1.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `column_dictionary`.

**Alcance/verificación pendiente:** Inventario de metadatos declarados de la base conectada. No acredita reglas de negocio, calidad de registros ni objetos ajenos al alcance visible.

### 3.2 — Documentar tipo de dato, longitud/precisión y formato de cada campo

**Entregable:** Diccionario de datos - tipos. **Prioridad:** Alta. **Número en la hoja:** 2.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `column_dictionary`.

**Alcance/verificación pendiente:** Inventario de metadatos declarados de la base conectada. No acredita reglas de negocio, calidad de registros ni objetos ajenos al alcance visible.

### 3.3 — Registrar si el campo es obligatorio (NOT NULL) u opcional

**Entregable:** Diccionario de datos - obligatoriedad. **Prioridad:** Alta. **Número en la hoja:** 3.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `column_dictionary`.

**Alcance/verificación pendiente:** Inventario de metadatos declarados de la base conectada. No acredita reglas de negocio, calidad de registros ni objetos ajenos al alcance visible.

### 3.4 — Documentar valores por defecto y valores permitidos (dominios, catálogos, ENUM)

**Entregable:** Diccionario de datos - dominios. **Prioridad:** Media. **Número en la hoja:** 4.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `column_dictionary`, `column_check_constraints`, `domain_constraints`, `enum_values`, `table_foreign_keys`.

**Alcance/verificación pendiente:** Catálogos de negocio y validaciones de aplicación complementan dominios, ENUM, DEFAULT, CHECK y FK declarados.

### 3.5 — Identificar campos calculados, derivados o de solo lectura

**Entregable:** Lista de campos calculados. **Prioridad:** Media. **Número en la hoja:** 5.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `column_dictionary`.

**Alcance/verificación pendiente:** Revisar cálculos en consultas y aplicación; no todos los campos derivados están declarados como generados.

### 3.6 — Documentar la regla de negocio asociada a cada campo relevante

**Entregable:** Diccionario de datos - reglas de negocio. **Prioridad:** Alta. **Número en la hoja:** 6.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `column_dictionary`, `column_check_constraints`, `domain_constraints`, `enum_values`, `table_foreign_keys`.

**Alcance/verificación pendiente:** Diccionario de reglas aprobado y código de validaciones de la aplicación.

### 3.7 — Identificar campos con datos sensibles: PII, financieros, salud, credenciales

**Entregable:** Mapa de datos sensibles. **Prioridad:** Alta. **Número en la hoja:** 7.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `column_dictionary`.

**Alcance/verificación pendiente:** Validación del propietario de datos; los nombres solo sugieren sensibilidad, sin leer valores personales.

### 3.8 — Estandarizar nomenclatura de campos (idioma, prefijos, sufijos, singular/plural)

**Entregable:** Guía de estandarización de campos. **Prioridad:** Media. **Número en la hoja:** 8.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `column_dictionary`.

**Alcance/verificación pendiente:** Aprobación de estándares y análisis de dependencias antes de proponer renombrados; no se modifica el esquema.

### 3.9 — Documentar campos deprecados, en desuso o pendientes de eliminación

**Entregable:** Lista de campos deprecados. **Prioridad:** Baja. **Número en la hoja:** 9.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `column_dictionary`.

**Alcance/verificación pendiente:** Historial de cambios y análisis de consumidores; nombres y comentarios no prueban desuso.

## 4. Índices y Rendimiento

### 4.1 — Inventariar todos los índices existentes por tabla (nombre, tipo, campos incluidos)

**Entregable:** Inventario de índices. **Prioridad:** Alta. **Número en la hoja:** 1.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `index_inventory`.

**Alcance/verificación pendiente:** Inventario de metadatos declarados de la base conectada. No acredita reglas de negocio, calidad de registros ni objetos ajenos al alcance visible.

### 4.2 — Verificar y documentar llave primaria y llaves foráneas de cada tabla

**Entregable:** Matriz de llaves PK/FK. **Prioridad:** Alta. **Número en la hoja:** 2.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `index_inventory`, `table_inventory`, `table_constraints`, `table_foreign_keys`, `key_constraint_properties`.

**Alcance/verificación pendiente:** Inventario de metadatos declarados de la base conectada. No acredita reglas de negocio, calidad de registros ni objetos ajenos al alcance visible.

### 4.3 — Evaluar índices duplicados, redundantes o no utilizados

**Entregable:** Reporte de índices redundantes. **Prioridad:** Media. **Número en la hoja:** 3.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `index_inventory`.

**Alcance/verificación pendiente:** Ventana estadística representativa, planes y dependencias antes de eliminar índices aparentemente redundantes.

### 4.4 — Identificar tablas sin índice en campos de búsqueda o filtrado frecuente

**Entregable:** Lista de índices faltantes. **Prioridad:** Alta. **Número en la hoja:** 4.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `index_inventory`, `table_foreign_keys`.

**Alcance/verificación pendiente:** Predicados y planes de consultas reales para confirmar búsquedas frecuentes y necesidad de índices.

### 4.5 — Analizar consultas más frecuentes/pesadas mediante query log o plan de ejecución

**Entregable:** Reporte de consultas críticas. **Prioridad:** Alta. **Número en la hoja:** 5.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `query_observability`, `active_query_snapshot`.

**Alcance/verificación pendiente:** Historial de consultas y planes anonimizados; una instantánea no demuestra frecuencia ni causa raíz.

### 4.6 — Revisar fragmentación de índices y necesidad de mantenimiento (rebuild/reorganize)

**Entregable:** Reporte de fragmentación. **Prioridad:** Media. **Número en la hoja:** 6.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `index_inventory`, `table_volumetry`.

**Alcance/verificación pendiente:** Medición especializada autorizada para fragmentación exacta; tamaño y tuplas muertas son solo indicadores.

### 4.7 — Evaluar necesidad de índices compuestos o cubrientes (covering index)

**Entregable:** Propuesta de índices compuestos. **Prioridad:** Media. **Número en la hoja:** 7.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `index_inventory`, `table_foreign_keys`.

**Alcance/verificación pendiente:** Carga y planes representativos para validar orden de columnas y beneficio de índices cubrientes.

### 4.8 — Documentar estrategia de particionamiento de tablas de alto volumen, si aplica

**Entregable:** Nota de particionamiento. **Prioridad:** Baja. **Número en la hoja:** 8.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `partition_configuration`, `table_volumetry`.

**Alcance/verificación pendiente:** Patrones de acceso y crecimiento para evaluar la estrategia de particionamiento, no solo su configuración.

## 5. Revisión del Modelo de Datos

### 5.1 — Validar/actualizar el diagrama entidad-relación (ER) completo de la aplicación

**Entregable:** Diagrama ER actualizado. **Prioridad:** Alta. **Número en la hoja:** 1.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_foreign_keys`.

**Alcance/verificación pendiente:** Validar las relaciones semánticas no declaradas y el alcance de la aplicación; evidencia incluye relaciones FK observadas.

### 5.2 — Verificar nivel de normalización y detectar redundancias evitables

**Entregable:** Reporte de normalización. **Prioridad:** Media. **Número en la hoja:** 2.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_columns`, `table_constraints`, `table_foreign_keys`.

**Alcance/verificación pendiente:** Dependencias funcionales y reglas del negocio para demostrar formas normales y redundancia evitable.

### 5.3 — Identificar relaciones huérfanas o sin llave foránea formalmente definida

**Entregable:** Lista de relaciones sin FK. **Prioridad:** Alta. **Número en la hoja:** 3.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_columns`, `table_foreign_keys`.

**Alcance/verificación pendiente:** Relaciones de negocio y verificaciones agregadas autorizadas de registros para confirmar huérfanos.

### 5.4 — Revisar cardinalidad de relaciones (1:1, 1:N, N:M) y su correcta implementación

**Entregable:** Matriz de cardinalidad. **Prioridad:** Media. **Número en la hoja:** 4.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_columns`, `table_constraints`, `table_foreign_keys`.

**Alcance/verificación pendiente:** Cardinalidades de negocio y población de datos; las restricciones describen cardinalidad estructural permitida.

### 5.5 — Validar consistencia del modelo entre módulos relacionados o compartidos

**Entregable:** Reporte de consistencia inter-módulos. **Prioridad:** Alta. **Número en la hoja:** 5.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_foreign_keys`, `column_dictionary`.

**Alcance/verificación pendiente:** Mapa real de módulos y reglas compartidas; esquemas diferentes no equivalen necesariamente a módulos.

### 5.6 — Identificar tablas puente/intermedias faltantes en relaciones N:M

**Entregable:** Lista de tablas puente pendientes. **Prioridad:** Media. **Número en la hoja:** 6.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_constraints`, `table_foreign_keys`.

**Alcance/verificación pendiente:** Relaciones N:M del negocio para confirmar tablas puente faltantes, sin deducirlas solo de nombres.

### 5.7 — Revisar convención de llaves primarias (autoincremental, UUID, compuesta) y su coherencia

**Entregable:** Nota técnica de llaves. **Prioridad:** Media. **Número en la hoja:** 7.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_inventory`, `table_constraints`, `column_dictionary`.

**Alcance/verificación pendiente:** Convención aprobada de llaves y requisitos de interoperabilidad para evaluar coherencia normativa.

### 5.8 — Validar consistencia de tipos de datos entre campos relacionados (FK vs PK)

**Entregable:** Reporte de inconsistencias de tipos. **Prioridad:** Alta. **Número en la hoja:** 8.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `table_foreign_keys`, `column_dictionary`.

**Alcance/verificación pendiente:** Inventario de metadatos declarados de la base conectada. No acredita reglas de negocio, calidad de registros ni objetos ajenos al alcance visible.

## 6. Optimización y Mejoras

### 6.1 — Identificar consultas lentas y su causa raíz (falta de índice, mal diseño, N+1, etc.)

**Entregable:** Reporte de causas raíz. **Prioridad:** Alta. **Número en la hoja:** 1.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `query_observability`, `active_query_snapshot`.

**Alcance/verificación pendiente:** Planes e historial anonimizados y trazas de la aplicación para confirmar causas raíz, incluido N+1.

### 6.2 — Proponer particionamiento o archivado para tablas de alto volumen

**Entregable:** Propuesta de particionamiento/archivado. **Prioridad:** Media. **Número en la hoja:** 2.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `partition_configuration`, `table_volumetry`.

**Alcance/verificación pendiente:** Proyecciones, patrones de acceso y retención empresarial para justificar particionamiento o archivado.

### 6.3 — Evaluar necesidad de vistas materializadas o tablas resumen para reportería

**Entregable:** Propuesta de vistas materializadas. **Prioridad:** Media. **Número en la hoja:** 3.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `view_inventory`, `view_dependencies`.

**Alcance/verificación pendiente:** Carga de reportería y planes para confirmar beneficio y política de refresco de vistas materializadas.

### 6.4 — Revisar y optimizar procedimientos almacenados y funciones críticas

**Entregable:** Informe de optimización de SP/funciones. **Prioridad:** Alta. **Número en la hoja:** 4.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `routine_inventory`, `routine_dependencies`, `table_trigger_inventory`, `event_trigger_inventory`.

**Alcance/verificación pendiente:** Código y mediciones de rutinas críticas; no se ejecutan ni se modifican rutinas de la base auditada.

### 6.5 — Proponer política de archivado/purga de datos históricos

**Entregable:** Propuesta de retención y purga. **Prioridad:** Media. **Número en la hoja:** 5.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_volumetry`, `partition_configuration`.

**Alcance/verificación pendiente:** Política legal y empresarial de retención; estadísticas de volumen no determinan plazos de purga.

### 6.6 — Evaluar uso de caché de aplicación o BD para consultas repetitivas

**Entregable:** Propuesta de estrategia de caché. **Prioridad:** Baja. **Número en la hoja:** 6.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `cache_statistics`, `query_observability`.

**Alcance/verificación pendiente:** Trazas de repetición y requisitos de invalidación; caché de bloques PostgreSQL no demuestra caché de aplicación.

### 6.7 — Revisar configuración del motor: connection pool, buffers, timeouts, memoria

**Entregable:** Reporte de configuración del motor. **Prioridad:** Media. **Número en la hoja:** 7.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `engine_configuration`.

**Alcance/verificación pendiente:** Recursos del servidor, carga y pool de aplicación para dimensionar parámetros sin cambiarlos.

### 6.8 — Priorizar mejoras identificadas mediante matriz de impacto vs. esfuerzo

**Entregable:** Matriz de priorización de mejoras. **Prioridad:** Alta. **Número en la hoja:** 8.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_volumetry`, `index_inventory`, `referential_control`.

**Alcance/verificación pendiente:** Responsables deben estimar impacto y esfuerzo con carga y dependencias; no se inventan puntajes ni prioridades finales.

## 7. Integridad de Datos

### 7.1 — Validar restricciones existentes: NOT NULL, UNIQUE, CHECK, DEFAULT

**Entregable:** Reporte de restricciones. **Prioridad:** Alta. **Número en la hoja:** 1.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `column_dictionary`, `table_constraints`, `domain_constraints`.

**Alcance/verificación pendiente:** Inventario de metadatos declarados de la base conectada. No acredita reglas de negocio, calidad de registros ni objetos ajenos al alcance visible.

### 7.2 — Verificar que la integridad referencial (FK) esté activa y correctamente configurada

**Entregable:** Reporte de integridad referencial. **Prioridad:** Alta. **Número en la hoja:** 2.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `table_foreign_keys`, `referential_control`.

**Alcance/verificación pendiente:** Inventario de metadatos declarados de la base conectada. No acredita reglas de negocio, calidad de registros ni objetos ajenos al alcance visible.

### 7.3 — Identificar registros huérfanos, duplicados o inconsistentes

**Entregable:** Reporte de datos huérfanos/duplicados. **Prioridad:** Alta. **Número en la hoja:** 3.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_constraints`, `referential_control`, `fk_data_check_definitions`, `fk_orphan_count_template`.

**Alcance/verificación pendiente:** Reglas de unicidad y relaciones empresariales y comprobaciones de registros autorizadas; metadatos no prueban ausencia de duplicados.

### 7.4 — Validar consistencia de datos maestros compartidos entre módulos

**Entregable:** Reporte de consistencia de maestros. **Prioridad:** Alta. **Número en la hoja:** 4.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_foreign_keys`, `table_constraints`.

**Alcance/verificación pendiente:** Definición de maestros compartidos y reglas intermodulares; no se inspeccionan valores personales.

### 7.5 — Revisar dónde se aplican las validaciones: a nivel de aplicación vs. a nivel de BD

**Entregable:** Matriz de validaciones app vs BD. **Prioridad:** Media. **Número en la hoja:** 5.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `table_constraints`, `table_trigger_inventory`, `column_dictionary`.

**Alcance/verificación pendiente:** Validaciones del backend para completar la comparación con restricciones y triggers de PostgreSQL.

### 7.6 — Auditar el cumplimiento de propiedades ACID en transacciones críticas

**Entregable:** Informe de auditoría transaccional. **Prioridad:** Media. **Número en la hoja:** 6.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `security_configuration`, `cache_statistics`.

**Alcance/verificación pendiente:** Diseño y pruebas controladas de transacciones críticas; configuración durable no prueba cumplimiento ACID de la aplicación.

### 7.7 — Validar consistencia de fechas, rangos y reglas lógicas de negocio en los datos

**Entregable:** Reporte de consistencia lógica. **Prioridad:** Media. **Número en la hoja:** 7.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `column_check_constraints`, `domain_constraints`, `column_dictionary`.

**Alcance/verificación pendiente:** Reglas temporales y rangos de negocio y comprobaciones agregadas aprobadas; CHECK declarados no prueban todos los datos.

### 7.8 — Identificar datos inconsistentes originados por migraciones o cargas previas

**Entregable:** Reporte de hallazgos de migración. **Prioridad:** Alta. **Número en la hoja:** 8.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `migration_candidates`, `referential_control`, `table_constraints`.

**Alcance/verificación pendiente:** Bitácora de cargas, reglas y referencia previa para atribuir inconsistencias a una migración.

## 8. Seguridad y Controles

### 8.1 — Revisar roles, perfiles y permisos de acceso a nivel de base de datos

**Entregable:** Matriz de roles y permisos. **Prioridad:** Alta. **Número en la hoja:** 1.

**Capacidad:** Completa en el alcance técnico declarado.

**Evidencias predefinidas:** `roles`, `memberships`, `privileges`, `column_privileges`, `default_privileges`, `access_controls`.

**Alcance/verificación pendiente:** Alcance: roles, membresías y privilegios declarados de la base conectada; no incluye identidades del sistema operativo.

### 8.2 — Validar cifrado de datos sensibles en reposo y en tránsito

**Entregable:** Reporte de cifrado. **Prioridad:** Alta. **Número en la hoja:** 2.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `security_configuration`, `session_tls`, `extensions`.

**Alcance/verificación pendiente:** Evidencia de almacenamiento y gestión de claves para cifrado en reposo; SSL del servidor no demuestra TLS en todas las sesiones.

### 8.3 — Revisar política de respaldos (backups): frecuencia, retención y pruebas de restauración

**Entregable:** Política de backups validada. **Prioridad:** Alta. **Número en la hoja:** 3.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `wal_configuration`, `archiver`, `backup_progress`.

**Alcance/verificación pendiente:** Inventario de copias externas, retención y pruebas de restauración. WAL y archivado no prueban backups utilizables ni PITR operativo.

### 8.4 — Validar plan de recuperación ante desastres (RPO/RTO definidos y probados)

**Entregable:** Plan de continuidad validado. **Prioridad:** Alta. **Número en la hoja:** 4.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `wal_configuration`, `recovery`, `replication`, `replication_visibility`.

**Alcance/verificación pendiente:** RPO/RTO definidos por negocio y ensayos de recuperación; replicación no prueba un plan de continuidad validado.

### 8.5 — Revisar logs de auditoría y trazabilidad de cambios sobre datos críticos

**Entregable:** Reporte de auditoría de cambios. **Prioridad:** Media. **Número en la hoja:** 5.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `security_configuration`, `extensions`, `table_trigger_inventory`.

**Alcance/verificación pendiente:** Inspección autorizada de logs anonimizados y cobertura de eventos; configuración y extensiones no prueban trazabilidad efectiva.

### 8.6 — Validar cumplimiento normativo aplicable (Ley N.° 29733 - Perú, y normativa sectorial)

**Entregable:** Checklist de cumplimiento normativo. **Prioridad:** Alta. **Número en la hoja:** 6.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `security_configuration`, `access_controls`, `session_tls`.

**Alcance/verificación pendiente:** Evaluación de aplicabilidad normativa por responsables competentes; controles técnicos no certifican cumplimiento legal.

### 8.7 — Revisar segregación de ambientes (desarrollo, pruebas, producción)

**Entregable:** Reporte de segregación de ambientes. **Prioridad:** Media. **Número en la hoja:** 7.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `database_environments`, `roles`.

**Alcance/verificación pendiente:** Inventario de ambientes, redes y accesos; nombres de bases no demuestran segregación.

### 8.8 — Validar control de versiones del esquema mediante migraciones (versionado de BD)

**Entregable:** Reporte de versionado de esquema. **Prioridad:** Media. **Número en la hoja:** 8.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `migration_candidates`.

**Alcance/verificación pendiente:** Repositorio y registros de ejecución de migraciones; detectar tablas candidatas no valida historial ni control de versiones.

### 8.9 — Revisar procedimiento formal de gestión de cambios (change management) sobre BD

**Entregable:** Procedimiento de gestión de cambios. **Prioridad:** Media. **Número en la hoja:** 9.

**Capacidad:** Necesariamente externa.

**Evidencias predefinidas:** Sin SELECT capaz de producir este documento empresarial.

**Alcance/verificación pendiente:** Se requiere el procedimiento aprobado, solicitudes, revisiones y autorizaciones de cambios; no existe en los catálogos PostgreSQL.

### 8.10 — Validar enmascaramiento/anonimización de datos sensibles en ambientes no productivos

**Entregable:** Reporte de enmascaramiento de datos. **Prioridad:** Alta. **Número en la hoja:** 10.

**Capacidad:** Parcial.

**Evidencias predefinidas:** `masking_metadata`, `extensions`, `access_controls`.

**Alcance/verificación pendiente:** Políticas, linaje y pruebas autorizadas de anonimización; extensión o etiqueta no demuestran datos anonimizados.

## Regla de cómputo

Solo cuenta como completa una actividad cuyo nombre, fase y entregable coinciden con el catálogo, cuya capacidad revisada es completa y cuyas consultas/evidencias no tienen errores ni truncamiento. La IA no altera ese cómputo. Los totales se derivan de los resultados, sin objetivo prefijado. Ver [validación y limitaciones](continuacion-checklist67.md).
