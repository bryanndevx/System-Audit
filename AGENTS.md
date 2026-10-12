# Instrucciones del proyecto — Auditoría BD

## Objetivo y fuentes de verdad
- Construir el sistema descrito en `docs/especificacion.md`. El prototipo Figma aprobado es la referencia visual.
- Si falta información, pedirla o indicar el supuesto antes de implementar; no inventar funcionalidades, datos, consultas SQL ni resultados.
- Trabajar una funcionalidad a la vez, según el Sprint y los criterios de aceptación.

## Arquitectura y tecnologías
- Backend: monolito modular sencillo con Python + FastAPI.
- Frontend separado: React + TypeScript + Vite + Tailwind CSS.
- BD propia: PostgreSQL. BD auditada: conexión independiente y de privilegios mínimos, solo lectura.
- Mantener módulos pequeños y con nombres claros; preferir código simple sobre patrones innecesarios.
- No introducir microservicios, colas, RAG ni librerías extra sin justificación y aprobación.

## Seguridad y evidencia
- Nunca escribir contraseñas, tokens ni claves API en el código, logs, pruebas o repositorio.
- No persistir credenciales de las bases auditadas; limitar su uso a la ejecución.
- Nunca ejecutar SQL generado por un LLM; usar exclusivamente consultas revisadas y predefinidas.
- Nunca modificar la base auditada. Usar usuario de solo lectura y protección adicional en la sesión.
- La IA solamente redacta diagnóstico y recomendación a partir de evidencias y criterios técnicos; no calcula resultados ni determina la exactitud.
- Preservar evidencia verificable y distinguir `no automatizada` de `error de ejecución` o `incumplimiento`.
- No enviar datos personales o secretos a la API de IA; usar solo evidencia técnica necesaria.

## Calidad y cambios
- Antes de cambios relevantes: decir brevemente qué archivos se tocarán y por qué.
- Implementar solo lo solicitado. No refactorizar otras partes por iniciativa propia.
- Usar versiones estables y compatibles, registrar dependencias en los archivos estándar y evitar versiones beta.
- Ejecutar verificaciones y pruebas pertinentes; informar claramente qué fue probado y qué no.
- No afirmar que el código funciona sin ejecutarlo o sin evidencia de su funcionamiento.
- Seguir fielmente el Figma; mejorar accesibilidad, estados y adaptabilidad sin alterar el diseño principal.
- Al finalizar: resumir cambios, pruebas, pendientes y cómo probar la función.
- Responder en español claro y explicar nuevos conceptos en una frase.
