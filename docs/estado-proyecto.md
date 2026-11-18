# Estado del proyecto — 17 de noviembre de 2026

**Contrato activo nuevo:** [PostgreSQL técnico v1](checklist-tecnico-v1.md), con Excel nuevo, trazabilidad de versión/huella y estados visibles Completada/Incompleta. La suficiencia de evidencia y la narrativa IA validada determinan el cierre; controles deshabilitados no bloquean una evaluación completa. El checklist empresarial original y sus cifras permanecen históricos. No confundir los resultados anteriores de diez entregables con los de esta reformulación.

Actualización: se implementó el recorrido de las 67 actividades, clasificación por entregable, progreso real y PDF privado desde historial. Prueba aislada: 10 entregables técnicos completos, 55 parciales, 2 externos y cero errores SQL. Ver [alcance, pruebas, límites y arranque actual](continuacion-checklist67.md) y [revisión individual](catalogo-67-actividades.md). Los apartados de seguimiento siguientes documentan etapas anteriores y no sustituyen esa actualización.

Revisión del código local frente a `especificacion.md`. Se conservaron las modificaciones locales que ya existían. «Implementado» describe código presente, no una certificación de funcionamiento en una base real.

## Qué está desarrollado

| Área | Evidencia en el repositorio | Estado |
| --- | --- | --- |
| Diseño | Capturas en `docs/figma/` | Referencias disponibles; fidelidad visual no validada en esta revisión |
| Interfaz base | React, TypeScript, Vite, Tailwind, login y navegación | Compila; revisión visual completa pendiente |
| Autenticación | `auth.py`, `sessions.py`, `user_admin.py`, migraciones 001/002 y script de creación de usuario | Implementada con hash Argon2, sesiones del servidor, cookie HttpOnly, validación de origen y token CSRF |
| Importación Excel | `checklists.py`, formulario y pruebas | Valida archivo y estructura, detecta fases/actividades y conserva orden; requiere el formato documentado |
| Conexión auditada | `external_connections.py` | Destinos permitidos, validación de rol, transacciones de solo lectura, límites de tiempo y política TLS según entorno |
| Motor SQL | `audit_queries.py`, `audit_engine.py`, `/api/audits/execute` | Consultas predefinidas, evidencia estructurada, tiempos y estados completada/parcial/error/sin configuración |
| Alcance del catálogo | 67 actividades revisadas individualmente | 65 con evidencia PostgreSQL total/parcial y 2 necesariamente externas; cobertura comprobada por entregable en la documentación actual |
| Resultados y detalle | `AuditResults.tsx`, `EvidenceViewer.tsx` | Muestra la ejecución actual y los resultados guardados con su evidencia |
| Historial | `audit_history.py`, migración 003, Dashboard y ruta `/auditorias/{uuid}` | Persistencia por usuario implementada y verificada en PostgreSQL aislado; falta aplicar la migración en la base interna local |
| Redacción IA | `ai_context.py`, `ai_diagnostics.py`, detalle de resultados | Integración Gemini implementada con resúmenes agregados y errores separados; validación con API real pendiente de clave local |
| Comparación de evidencia | Script, referencia manual y pruebas | Herramientas presentes para contrastar evidencia; no se calculó exactitud contra una base real en esta revisión |

## Qué falta desarrollar o cerrar

1. **Sprint 3:** validar consultas, permisos, alcance y evidencia contra la base de prueba y el Excel acordados. El crecimiento histórico no se puede deducir de una sola ejecución; varias actividades expresan límites técnicos. El mapeo se basa en identificadores: revisar que el checklist utilizado corresponda al catálogo antes de afirmar cobertura funcional.
2. **Sprint 4:** Gemini elegido e integración implementada. Falta configurar la clave local y validar respuestas reales contra el criterio del auditor. Ver `docs/ia-gemini.md`; la validación estructural no certifica el contenido redactado.
3. **Sprint 5:** historial privado, persistencia, reapertura y progreso incremental implementados. Confirmar activación de la migración 003 en la instalación del usuario.
4. **Sprint 6:** PDF implementado y probado sobre resultados guardados; evaluar documentos de mayor volumen en el despliegue final.
5. **Validación final:** recorrido autenticado completo y revisión visual/adaptabilidad frente al Figma aprobado. Revisar también la navegación y el cierre de sesión en móvil: la barra lateral que los contiene se oculta en pantallas pequeñas.
6. **Límites de recursos:** implementados límites de expansión/filas Excel y 5000 filas por consulta SQL, con truncamiento informado y cobertura parcial. Validar dimensionamiento y rendimiento en bases grandes antes del despliegue.

## Continuación: validación del checklist antes de ejecutar

Se cerró la incompatibilidad entre el Excel aceptado y los límites del motor: el importador rechaza más de 100 actividades y textos que excedan 50 caracteres de identificador, 500 de nombre de actividad o 250 de fase. El error identifica la fila cuando corresponde. Se comprueba también la longitud del identificador después de agregar el número de fase. No se recorta ni omite contenido para hacerlo pasar. Los límites ya existían en el endpoint de ejecución; no se fijó una cantidad de fases ni de actividades obligatorias.

Después de la elección del usuario se implementó Gemini, con `gemini-3.5-flash-lite` como modelo estable predeterminado y cuota gratuita disponible según documentación consultada. Usa contexto agregado permitido, criterios derivados de las limitaciones del motor y salida estructurada; preserva resultados SQL si falla la IA. Está deshabilitado por defecto hasta configurar la clave local. No se enviaron evidencias ni se consumió cuota durante el desarrollo. Ver configuración, criterios y límites en `ia-gemini.md`.

Verificación de esta integración: 135 pruebas unitarias del backend aprobadas; compilación de producción y ESLint del frontend correctos. Incluye filtrado de datos, salida inválida/truncada, cuota, timeout, separación de estados SQL/IA y cierre de conexión antes de redactar. Las respuestas de Gemini son simuladas en pruebas; falta validar una llamada real tras configurar la clave local. No se cambiaron dependencias ni se ejecutaron auditorías contra una base real durante esta implementación.

Seguimiento del error genérico comunicado por el usuario: el cliente ahora muestra HTTP y estados conocidos sin revelar mensajes o metadatos privados del proveedor. Se añadió `scripts.check_gemini`, una prueba de una sola solicitud con datos ficticios y sin conexión PostgreSQL. Verificación: 139 pruebas unitarias aprobadas. La causa exacta del fallo de la cuenta aún requiere ejecutar ese diagnóstico con la clave local; no se confirmó que el modelo, la cuota o el esquema fueran la causa y no se cambió automáticamente de modelo.

Seguimiento de HTTP 400 INVALID_ARGUMENT: se sustituyó el esquema generado por Pydantic por `responseSchema` con tipos, propiedades y campos requeridos del subconjunto REST de Gemini; los límites y la validación estricta permanecen en Python. Se agregó reconocimiento de claves expiradas/bloqueadas y detalle técnico sanitizado exclusivo del comando local. Verificación: 141 pruebas unitarias aprobadas. El 400 reportado no identifica por sí solo el campo rechazado; la corrección de compatibilidad y el diagnóstico mejorado requieren repetir la prueba local con la clave para confirmar el resultado real.

Revisión de configuración e interpretación: ahora se carga `backend/.env` en desarrollo para Gemini, con prioridad del entorno de la terminal, plantilla sin secretos y sin dependencias nuevas. Se reforzó el contexto con criterios para cada actividad y hallazgos calculados en Python; la respuesta debe citar evidencias existentes que se muestran como E1, E2, etc. Las versiones son `hallazgos-agregados-v2` y `gemini-criterios-v2`. Verificación: 152 pruebas unitarias aprobadas, compilación y ESLint correctos. Incluye una prueba del diagnóstico leyendo la clave de un archivo temporal sin solicitarla ni mostrarla. Las pruebas no consumieron API real. El usuario reportó un HTTP 503 por alta demanda; cargar `.env` no soluciona una indisponibilidad del proveedor.

## Mejora del modal de actividad

Se reorganizó el detalle manteniendo la paleta del Figma de `docs/figma/ver.png`: encabezado y cierre visibles, evidencia desplegable, diagnóstico y recomendación separados, observaciones de ejecución diferenciadas de las limitaciones, y pie con regreso a resultados. En escritorio usa dos columnas; en móvil se apilan. Los identificadores de consulta quedan en una referencia desplegable y las citas E1/E2 permiten abrir la evidencia correspondiente.

El diálogo nativo mantiene el foco dentro del modal, cierra con Escape o al pulsar fuera y devuelve el foco al control que lo abrió. La página de fondo no se desplaza. Las tablas tienen encabezados visibles al desplazarse y los registros anidados se muestran por lotes sin omitir el resto.

Verificación: compilación y ESLint del frontend correctos. Comprobación visual y de interacción en Chrome con datos ficticios, a 1440×1000 y 390×844: apertura/cierre, teclado, retorno de foco, citas, carga de todas las filas, registros anidados, texto extenso, error de IA y ausencia de evidencia, sin errores JavaScript. La vista temporal se trasladó fuera del frontend; las capturas y el material de prueba local quedan fuera de Git en `local-data/modal-preview-75cbd4d4/`. No se ejecutó una nueva auditoría ni se modificaron backend o dependencias para este cambio visual.

## Tablas compactas de evidencia

Se sustituyeron los bloques de parámetros por tablas Parámetro/Valor. Las listas de objetos, incluidas las que contienen estructuras anidadas, ahora muestran una fila por registro y columnas para sus campos simples. Los campos anidados se consultan con Ver detalles en una fila expandida, sin repetir los valores principales. Las listas largas dentro de una celda son desplegables; las listas de valores independientes también se muestran como filas. Se redujeron los espacios, se alinearon las cifras y se conservaron encabezados, desplazamiento y carga por lotes.

Verificación: compilación y ESLint correctos; revisión en Chrome para escritorio y móvil con datos ficticios. Se comprobaron la tabla de parámetros, los 42 registros simples y 32 grupos anidados accesibles con Mostrar más, la expansión de varios niveles y la distinción de cero, falso, nulo y campo ausente. No hubo errores JavaScript. Capturas de revisión fuera de Git en `local-data/table-preview/`. Cambio limitado a `EvidenceViewer.tsx` y esta documentación; sin ejecutar auditorías ni modificar datos.

## Historial real — 14 de noviembre de 2026

Se añadió almacenamiento en PostgreSQL interno, listado paginado por propietario, reapertura por UUID y estado de guardado explícito. El Dashboard dejó de mostrar ejemplos. El indicador técnico se calcula en Python y distingue parciales, errores SQL, ausencia de configuración y errores IA. El detalle histórico utiliza el resultado almacenado sin repetir SQL ni Gemini y mantiene el orden de las fases, incluso cuando un nombre de fase aparece de nuevo.

Seguimiento del fallo local de preparación: se corrigió el script para conservar los mensajes seguros de configuración/conexión y distinguir errores de migración por código PostgreSQL. Verificación ampliada a 168 pruebas unitarias aprobadas. La causa del fallo comunicado por el usuario todavía requiere repetir el comando local; no se confirmó un error de contraseña, permisos o estructura y no se modificó la base real durante esta revisión.

Verificación: 164 pruebas unitarias aprobadas, compilación y ESLint correctos, prueba real de almacenamiento/HTTP en PostgreSQL aislado y revisión de la interfaz en Chrome con datos ficticios. Se comprobó persistencia tras reiniciar PostgreSQL, acceso 404 entre usuarios y una ejecución de lectura guardada y reabierta. No se modificó la base real del usuario ni se consumió Gemini. Ver pasos de activación y límites en `historial-auditorias.md`.

No se implementaron funcionalidades de otros Sprints durante la reparación del arranque.

## Diagnóstico del arranque

- PostgreSQL 18 estaba activo y escuchando en 5432.
- No había servidores escuchando en 8000 o 5173 al iniciar el diagnóstico.
- Las variables de conexión y autenticación no estaban configuradas en el proceso de revisión. Esto no demuestra que falten en otras terminales del usuario.
- Se reprodujo una espera superior a 12 segundos al ejecutar `run_backend.py` sin entrada interactiva ni `DB_PASSWORD`: `getpass` esperaba la contraseña. Se agregó una comprobación para fallar con instrucciones claras en esa situación.
- El lanzador ya proporcionaba valores de desarrollo y un bucle de eventos compatible con psycopg en Windows. Se conservaron y se agregó validación anticipada de la política de conexiones auditadas y manejo de cancelación.
- Vite podía elegir otro puerto si 5173 estaba ocupado; ese origen distinto sería rechazado por la autenticación configurada para `http://localhost:5173`. Se fijaron host y puerto con fallo explícito si está ocupado. No se observó un conflicto de puertos durante la revisión inicial.
- La guía anterior describía la extracción de un paquete inicial y no explicaba cómo arrancar el código existente. Se reemplazó por instrucciones operativas.

## Verificación y límites

- Antes de los cambios: 103 pruebas unitarias del backend correctas; compilación y ESLint del frontend correctos.
- Tras los cambios: 108 pruebas unitarias del backend correctas, incluidas regresiones del arranque y errores de conexión sin exponer detalles del controlador.
- Seguimiento del error de conexión: 110 pruebas unitarias correctas tras reconocer también errores genéricos de libpq de autenticación/base inexistente y preservar los espacios de las contraseñas. El error reportado por el usuario todavía requiere repetir el arranque para identificar la causa local; no se confirmó una contraseña incorrecta ni una base inexistente.
- Compilación de producción y ESLint del frontend correctos tras los cambios.
- Pruebas HTTP con procesos temporales: backend `/health` y frontend `/` respondieron 200. El reenvío `/api/auth/me` devolvió el 503 esperado al faltar configuración; no se simuló un login exitoso. Estos procesos se cerraron al terminar.
- Se comprobó en procesos reales que la ausencia de contraseña con entrada redirigida o `NUL` termina con código 2, y que un segundo Vite en 5173 ocupado falla en vez de elegir otro puerto.
- Se descubrieron las cinco pruebas de integración; quedaron omitidas porque no estaba configurada la base de prueba. No se cuentan como pruebas aprobadas contra PostgreSQL.
- No se instalaron paquetes ni se cambiaron versiones.
- No se modificó ninguna base de datos. No se dispone de credenciales en este proceso para confirmar que existan la base interna, las tablas o un usuario activo. La autenticación y las consultas reales requieren esa validación local; no se atribuye una causa definitiva a esos componentes sin comprobarlos.

Consultar [la guía de inicio](../LEEME_PRIMERO.md) para arrancar y preparar la base interna si hace falta.
