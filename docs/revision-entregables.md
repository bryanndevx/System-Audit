# Revisión de entregables — 17 de noviembre de 2026

Se contrastaron nuevamente las 67 actividades y sus entregables A–E con los catálogos, restricciones, estadísticas y configuración que PostgreSQL permite consultar. La revisión individual permanece en [catalogo-67-actividades.md](catalogo-67-actividades.md). No se estableció una meta de actividades completas ni se cambió el significado del entregable para aumentar el porcentaje.

El número diez describe entregables completos dentro del alcance técnico revisado; no significa que solo diez actividades ejecuten consultas. Las otras actividades conservan su evidencia. Se añadió un estado independiente del entregable, `estado_entregable`, además de la ejecución SQL, cobertura técnica y redacción IA:

| Estado | Significado |
| --- | --- |
| Entregable completo | Evidencia suficiente, requisitos coincidentes con el catálogo y sin errores/truncamiento |
| Requiere información externa · incompleta | PostgreSQL aporta una parte o el entregable depende enteramente de fuentes externas |
| Evidencia PostgreSQL incompleta | Falta evidencia técnica, permisos, coincide otro entregable o se excedieron límites; no se atribuye automáticamente a información externa |
| Error técnico | No se obtuvo evidencia por un fallo de ejecución |
| Sin configuración | El identificador no tiene implementación conocida |

Cada resultado guarda `informacion_obtenida` e `informacion_faltante`. La interfaz y el PDF distinguen las consultas terminadas de la completitud del documento solicitado. Los registros anteriores mantienen su clasificación histórica; se necesitan nuevas ejecuciones para obtener los campos y consultas añadidos.

## Revisión por fase

| Fase | Revisión del alcance pendiente |
| --- | --- |
| 1 — Arquitectura (8) | Motor, versión, esquemas, extensiones y metadatos de integración son observables. Lenguajes, ORM, framework, capas, cloud y convenciones aprobadas necesitan repositorios/responsables. La 1.1 ahora presenta una ficha por componente: valores PostgreSQL reales y campos externos vacíos explícitos. |
| 2 — Inventario (8) | Inventario por esquema completo; clasificación empresarial y módulo requieren validación funcional. Volumetría puntual no demuestra crecimiento; estadísticas no prueban desuso. Propósito de vistas/rutinas no queda confirmado solo por sus dependencias. |
| 3 — Diccionario (9) | Orden, tipos declarados y obligatoriedad son inventariables. Cálculos en aplicación, reglas de negocio, datos sensibles, desuso y estándares necesitan información externa. Dominios/ENUM/FK no contienen todas las validaciones del backend. |
| 4 — Rendimiento (8) | Índices y PK/FK son inventariables. Consultas representativas, planes y mediciones especializadas se necesitan para confirmar necesidad, causas, fragmentación, estrategias e idoneidad de mejoras. No se instala una extensión ni se ejecuta código de la aplicación para completar esas mediciones. |
| 5 — Modelo (8) | Tipos de FK comparables; relaciones declaradas permiten dibujar evidencia ER. No demuestran el modelo funcional completo, normalización semántica, cardinalidades empresariales, módulos o tablas puente faltantes. |
| 6 — Mejoras (8) | Configuración y estadísticas aportan contexto; el dimensionamiento, N+1, reportería, retención, caché e impacto/esfuerzo requieren carga, código, infraestructura o decisiones empresariales. No se inventan puntajes. |
| 7 — Integridad (8) | Restricciones y configuración de FK son observables; conteos acotados ya verifican huérfanos de FK declaradas. Maestros, duplicidad de negocio, reglas temporales, aplicación de validaciones, transacciones críticas y atribución a migraciones necesitan definiciones y referencias externas. |
| 8 — Seguridad (10) | Roles y permisos declarados son inventariables. Cifrado de almacenamiento, copias externas y restauraciones, RPO/RTO, logs efectivos, cumplimiento, ambientes, versionado y anonimización no quedan demostrados solo con configuración PostgreSQL. |

## Consultas adicionales

Se incorporaron cinco SELECT revisados que aportan datos distintos, sin comandos de conexión ni secretos:

- `publications` y `subscriptions_metadata` para 1.4: publicaciones, operaciones replicadas y suscripciones habilitadas de la base conectada. No se consulta `subconninfo`.
- `replication_slots` para 8.3 y 8.4: estado y posiciones WAL de slots de la base y slots físicos del clúster. No prueba existencia de una copia utilizable.
- `wal_receiver` para 8.4: estado y tiempos del receptor, excluyendo conexión, direcciones y credenciales. Filas ausentes o NULL requieren contrastar permisos/rol del servidor.
- `audit_log_settings` para 8.5: parámetros efectivos de logging y pgAudit cuando están registrados. No se leen archivos ni se supone que una extensión esté instalada.

Estas evidencias amplían los entregables parciales; no sustituyen fuentes externas ni aumentan por sí mismas los completos. Referencias: [publicaciones](https://www.postgresql.org/docs/18/catalog-pg-publication.html), [estadísticas y visibilidad](https://www.postgresql.org/docs/18/monitoring-stats.html), [slots](https://www.postgresql.org/docs/18/view-pg-replication-slots.html).

## Verificación

Se ejecutan pruebas unitarias de separación de estados y regresión de las 67 actividades, integración en PostgreSQL 18 aislado y recorrido visual con respuestas ficticias. La comparación de la 1.1 exige PostgreSQL/versión observada y valores externos NULL; un error de permisos sigue siendo técnico y no se reclasifica como información externa. No se consulta SmartDent ni Gemini en estas pruebas.

Resultado de la instancia ficticia: 67 actividades, 65 con evidencia técnica (incluidas comprobaciones sin filas), 10 entregables completos y 57 que requieren información externa; de estas últimas, 55 tienen aporte PostgreSQL y dos dependen enteramente de fuentes externas. Cero errores SQL. Son indicadores de esa prueba, no resultados de SmartDent ni una medida de exactitud. Pasaron 189 pruebas unitarias, seis de integración, compilación, lint y revisión en navegador.

Para probar: reiniciar backend, recargar frontend y realizar una nueva ejecución autorizada. En resultados se muestran entregables completos, actividades con evidencia PostgreSQL y requisitos externos. Abrir 1.1 para consultar la ficha incompleta y su información faltante.
