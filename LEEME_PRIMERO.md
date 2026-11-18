# Inicio — Sistema inteligente de auditoría PostgreSQL

**Nueva versión técnica:** importar [checklist_postgresql_tecnico_v1.xlsx](frontend/referencias/checklist_postgresql_tecnico_v1.xlsx). Ver [alcance, estados, métricas y pruebas](docs/checklist-tecnico-v1.md). El checklist original conserva sus requisitos y sus auditorías; para el criterio nuevo se necesita el nuevo archivo. Una actividad completada requiere evidencia suficiente y diagnóstico/recomendación IA válidos, aunque observe controles deshabilitados.

El proyecto tiene backend FastAPI y frontend React separados. El estado funcional y los pendientes están en [docs/estado-proyecto.md](docs/estado-proyecto.md); los requisitos siguen en [docs/especificacion.md](docs/especificacion.md).

La continuación de las 67 actividades, cobertura comprobada, progreso y exportación PDF está documentada en [docs/continuacion-checklist67.md](docs/continuacion-checklist67.md). Antes de reiniciar esta versión, actualizar las dependencias del backend con `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` desde `backend`; se incorporó ReportLab para los PDF.

## Arranque local en Windows

Ejecutar desde la raíz del proyecto, en dos terminales PowerShell. Los comandos usan las dependencias locales ya instaladas; no hace falta activar el entorno virtual.

Terminal 1, backend:

```powershell
cd backend
.\.venv\Scripts\python.exe run_backend.py
```

El lanzador solicita de forma oculta la contraseña de PostgreSQL interno. Por defecto usa `127.0.0.1:5432`, base `sistema_auditoria` y usuario `postgres`, únicamente en desarrollo. Si la instalación tiene otros valores, configurar `DB_HOST`, `DB_PORT`, `DB_NAME` y `DB_USER` en esa terminal antes de ejecutar. Para despliegue, usar un rol propio con los permisos necesarios para usuarios y sesiones.

La contraseña se mantiene en el entorno del proceso. No escribirla en el código ni en comandos que queden en el historial. Sin terminal interactiva, `DB_PASSWORD` debe llegar configurada mediante el entorno seguro del proceso; el lanzador falla con una indicación si falta. En desarrollo se carga `backend/.env` exclusivamente para las tres variables de Gemini; ver [configuración de IA](docs/ia-gemini.md).

Terminal 2, frontend:

```powershell
cd frontend
npm run dev
```

Abrir **http://localhost:5173**. Usar ese nombre y puerto: la autenticación verifica el origen de la solicitud. Vite reenvía `/api` a `http://127.0.0.1:8000`; este reenvío permite que el navegador use una sola dirección para ambos servicios. Si 5173 está ocupado, Vite informa el error en vez de cambiar silenciosamente de puerto.

`npm run preview` no sustituye el servidor de desarrollo: el reenvío actual está en `server.proxy`. El despliegue necesita servir frontend y `/api` bajo el origen HTTPS configurado.

## Preparación de la base interna, si aún no existe

No es la base auditada. En PostgreSQL/pgAdmin, preparar la base interna indicada por `DB_NAME` y ejecutar, en ese orden y exclusivamente en ella:

1. `backend/sql/migrations/001_create_users.sql`.
2. `backend/sql/migrations/002_create_user_sessions.sql`.

Las migraciones crean las tablas internas y comprueban su estructura cuando ya existen. No se ejecutan automáticamente al iniciar el servidor.

Para crear el primer usuario de la aplicación, configurar las variables de conexión en la misma terminal, introducir la contraseña de forma oculta y ejecutar desde `backend`:

```powershell
$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = '5432'
$env:DB_NAME = 'sistema_auditoria'
$env:DB_USER = 'postgres'
$databaseCredential = Get-Credential -UserName $env:DB_USER -Message 'Acceso a PostgreSQL interno'
try {
    $env:DB_PASSWORD = $databaseCredential.GetNetworkCredential().Password
    .\.venv\Scripts\python.exe -m scripts.create_first_user
} finally {
    Remove-Item Env:DB_PASSWORD -ErrorAction SilentlyContinue
    $databaseCredential = $null
}
```

El script pide un nombre y una contraseña nuevos para el usuario de la aplicación; esa contraseña es distinta de la de PostgreSQL. El backend no crea usuarios de demostración.

## Comprobaciones y errores habituales

Si olvidaste la contraseña de la aplicación, abre otra terminal en `backend` y ejecuta:

```powershell
.\.venv\Scripts\python.exe -m scripts.reset_password
```

Solicita la contraseña de PostgreSQL interno, el usuario de la aplicación y una nueva contraseña de al menos 12 caracteres, con confirmación. Solo guarda su hash y cierra las sesiones anteriores del usuario. Requiere acceso administrativo local a la base interna; no cambia la contraseña de PostgreSQL ni reactiva cuentas deshabilitadas. Si no recuerdas el nombre de usuario, puedes consultar la columna `username` de `public.users` en pgAdmin.

- `http://127.0.0.1:8000/health` confirma que responde FastAPI; no comprueba tablas, credenciales ni una auditoría completa.
- Si falta la contraseña o PostgreSQL rechaza la conexión, seguir el mensaje del lanzador y revisar la configuración local.
- Si el login devuelve servicio no disponible, comprobar las tablas internas, sus permisos y la configuración del backend. Arrancar directamente con `uvicorn app.main:app` omite la preparación y validación de `run_backend.py`, incluido el bucle compatible con psycopg en Windows.
- Si aparece «Origen de solicitud no permitido», usar `http://localhost:5173` y comprobar `APP_ORIGIN`.
- Para importar Excel, usar `.xlsx`, hasta 5 MiB por defecto, con hoja `Checklist Maestro` y encabezados A:H: `Fase`, `#`, `Paso / Actividad`, `Entregable Esperado`, `Prioridad`, `Estado`, `Responsable`, `Notas / Evidencia`.
- Cada auditoría admite hasta 100 actividades. El importador comprueba ese límite y los de texto del motor: identificador de hasta 50 caracteres, actividad de hasta 500 y fase de hasta 250. Si se superan, rechaza el archivo completo con un mensaje; no recorta actividades ni sus nombres.
- La conexión auditada usa otro usuario, de privilegios mínimos. En desarrollo solo se permiten por defecto `localhost` y `127.0.0.1`, puerto 5432. Para otro destino autorizado, configurar `AUDITED_DB_ALLOWED_HOSTS` y `AUDITED_DB_ALLOWED_PORTS`; en producción se exige TLS con verificación de identidad.

## Verificaciones

El historial real requiere preparar una vez su tabla en la base interna. Desde `backend`, ejecutar `.\.venv\Scripts\python.exe -m scripts.apply_history_migration` y luego reiniciar el servidor. Ver [activación y funcionamiento del historial](docs/historial-auditorias.md). Solo se guardan las nuevas ejecuciones de auditoría; los resultados anteriores que estaban en memoria no se recuperan retroactivamente.

Para habilitar diagnóstico y recomendación de IA, seguir [la configuración de Gemini](docs/ia-gemini.md): editar `backend/.env`, pegar la clave en `GEMINI_API_KEY` y configurar `GEMINI_ENABLED=1`. No requiere instalar paquetes adicionales. El archivo local no se sube a Git; `.env.example` contiene solo la plantilla sin secretos.

Desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Desde `frontend`:

```powershell
npm run build
npm run lint
```

Las pruebas unitarias no sustituyen la prueba contra PostgreSQL. Las de integración están en `backend/tests/integration/test_audit_engine.py` y requieren una base de prueba preparada y configuración explícita. No cargar sus fixtures en una base real auditada.

Si faltan `.venv` o `node_modules` en otra instalación, preparar las dependencias usando `backend/requirements.txt` y `frontend/package-lock.json` antes del arranque.

**No pegar:** contraseñas de PostgreSQL, tokens, claves API, datos de pacientes/clientes o infraestructura privada en chats o repositorios públicos.

**Regla principal:** reproducir Figma de forma fiel y preferir la implementación más sencilla que satisface los requisitos.
