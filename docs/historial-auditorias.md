# Historial de auditorías — Sprint 5

El Dashboard consulta auditorías reales guardadas en la base interna. Cada usuario ve únicamente las suyas; no hay registros de demostración. La pantalla Ver recupera la evidencia y la redacción originales, sin conectarse otra vez a la base auditada ni llamar a Gemini.

## Activar en la instalación local

Detener el backend con Ctrl+C y ejecutar desde la raíz del proyecto:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.apply_history_migration
.\.venv\Scripts\python.exe run_backend.py
```

El primer comando Python aplica `backend/sql/migrations/003_create_audit_runs.sql` exclusivamente en la base interna configurada mediante `DB_*`. Solicita la contraseña de PostgreSQL si no está en el entorno; es distinta de la clave Gemini. Es una preparación de una sola vez y puede repetirse sobre el esquema compatible sin borrar registros. Requiere la tabla `public.users` de la migración 001; el login sigue necesitando también la migración 002 de sesiones.

El segundo comando inicia el backend con el código nuevo. El frontend se inicia como siempre con `npm run dev` desde `frontend`.

La migración no se ejecuta automáticamente al arrancar el servidor. Si falta o no hay permisos, el Dashboard muestra el error correspondiente. Una auditoría que termina su ejecución conserva la evidencia en pantalla y muestra claramente si no pudo guardarse; no se presenta como persistida. No cerrar esa pantalla esperando poder recuperarla del historial.

Si falla el comando de preparación, el diagnóstico diferencia la comprobación de conexión de la aplicación del SQL. El mensaje «Conexión a la base interna verificada. Aplicando migración 003…» indica que se superó la primera etapa. Los errores posteriores muestran una causa segura y el código PostgreSQL cuando está disponible: permisos, tabla requerida, modo de solo lectura, bloqueo o incompatibilidad de estructura. No se imprime el error original del controlador ni las credenciales. No iniciar el backend esperando que complete por sí mismo una migración que falló.

## Qué se guarda

`public.audit_runs` conserva un UUID, propietario, nombre de la base auditada, fecha UTC del guardado y el resultado estructurado completo en JSONB. JSONB permite conservar objetos y listas de evidencia dentro de PostgreSQL sin convertirlos en texto plano de reporte.

El resultado contiene actividades en su orden, estados SQL, evidencia, advertencias, limitaciones, tiempos, resumen determinista y redacción IA con sus versiones/referencias. No se recibe ni guarda el formulario de conexión: host, puerto, usuario auditado y contraseña quedan fuera de la función de persistencia. La clave Gemini tampoco forma parte del resultado.

El tamaño máximo del resultado es de 16 MiB en su representación JSON UTF-8. Si se supera, no se trunca la evidencia ni se inserta un registro incompleto; se informa que no se guardó. Este límite no reemplaza los límites todavía pendientes sobre extracción de grandes evidencias del motor.

Solo se guardan nuevas ejecuciones completadas por esta versión del backend. Las auditorías previas que existían únicamente en memoria no se pueden recuperar retroactivamente. Un error de Gemini se conserva como error de IA junto con la evidencia SQL disponible.

## Indicador de automatización técnica

Se calcula en Python, con estas categorías excluyentes para SQL:

- **Automatizadas:** ejecución `completada` y evidencia `suficiente` o `sin_datos`. Un resultado vacío válido no es un error.
- **Parciales:** ejecución parcial o completada con evidencia insuficiente/no obtenida.
- **Errores SQL:** `error_tecnico`.
- **Sin configuración:** `sin_automatizacion_configurada`.

Porcentaje = automatizadas / total de actividades evaluadas × 100, redondeado a dos decimales. El total incluye todas las categorías. No se usa la cantidad de actividades mapeadas como si demostrara automatización completa. Los errores IA se cuentan aparte, pues pueden coexistir con una extracción SQL correcta. Este indicador no mide exactitud, conformidad ni calidad de la redacción, ni representa el éxito integral del flujo SQL + IA.

## Consultas y acceso

- `GET /api/audits?limit=20&offset=0`: listado del usuario autenticado, sin cargar toda la evidencia. Máximo 100 registros por página; el Dashboard muestra 20.
- `GET /api/audits/{uuid}`: resultado guardado del mismo usuario. Un UUID inexistente o de otro usuario devuelve el mismo 404.
- `POST /api/audits/execute`: al terminar SQL y la redacción IA, calcula el resumen y guarda el resultado en la base interna. Devuelve el estado de guardado y su identificador.

Los filtros por propietario provienen de la sesión, no de parámetros suministrados por el navegador. Las consultas están predefinidas y parametrizadas. No hay endpoints nuevos para ejecutar SQL arbitrario, borrar auditorías o consultar resultados de terceros. El detalle histórico tiene una URL `/auditorias/{uuid}` que admite recarga y permite regresar al Dashboard.

## Verificación realizada — 14 de noviembre de 2026

- 164 pruebas unitarias del backend aprobadas, incluyendo cálculo del indicador, guardado, fallo al confirmar la transacción, límite de tamaño, separación de propietarios y conservación de evidencia si falla el guardado.
- PostgreSQL 18 de prueba aislado en otro puerto, sin modificar la instancia del usuario: migración repetible, JSONB, paginación, durabilidad tras reinicio y consultas privadas por propietario.
- HTTP real sobre ese clúster: autenticación, 401 sin sesión, 404 entre usuarios, 422 para parámetros inválidos, ejecución de inventario con usuario de lectura en una base ficticia separada y reapertura del resultado guardado. Gemini se mantuvo desactivado en esa prueba.
- Frontend: compilación y ESLint correctos. Chrome en escritorio y móvil con respuestas ficticias: listado, paginación, detalle, modal, recarga, orden de fases repetidas, historial vacío, servicio no disponible y sesión expirada. Reabrir/recargar no envió solicitudes de ejecución.

La base interna real del usuario no fue migrada durante estas verificaciones: ejecutar el comando de activación local. Siguen pendientes el progreso incremental real y la exportación PDF desde los resultados guardados.
