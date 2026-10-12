# Inicio — Sistema inteligente de auditoría PostgreSQL

Este paquete NO es una aplicación terminada. Contiene instrucciones listas para trabajar en Cursor + Codex, sin depender de Cursor en tiempo de ejecución.

1. Crea una carpeta vacía llamada `sistema-auditoria`.
2. Extrae el contenido de este ZIP **dentro de esa carpeta**, conservando `.agents/skills/...` y `docs/`.
3. Abre esa carpeta (la raíz, no `docs/`) en Cursor.
4. Instala la extensión **Codex (OpenAI)** en Cursor, entra con **Iniciar sesión con ChatGPT**, y usa el panel de Codex, no el selector de modelos del agente nativo de Cursor.
5. Comprueba que Codex puede leer `AGENTS.md` y `docs/especificacion.md`. Primero pídele **solo un resumen sin modificar archivos**.
6. Crea un repositorio Git y haz el primer commit sin incluir secretos.
7. Prepara una copia del diseño Figma (enlace autorizado + capturas/assets) y un Excel de ejemplo con la estructura verdadera. Guárdalos fuera del repositorio si contienen datos sensibles.
8. Instala/valida Node.js LTS, Python estable compatible y Git. Usa solo paquetes estables.
9. Crea React/Vite/TypeScript/Tailwind y FastAPI progresivamente en el Sprint 2; no instales la API de IA, ReportLab ni todas las librerías por adelantado.
10. Construye una funcionalidad pequeña, pruébala y realiza un commit antes de la siguiente.

**No pegar:** contraseñas de PostgreSQL, tokens, claves API, datos de pacientes/clientes o infraestructura privada en chats o repositorios públicos.

**Regla principal:** reproducir Figma de forma fiel y preferir la implementación más sencilla que satisface los requisitos.
