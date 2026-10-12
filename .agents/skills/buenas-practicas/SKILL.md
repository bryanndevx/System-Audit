---
name: buenas-practicas
description: Implementar o revisar una funcionalidad del sistema de auditoría PostgreSQL mediante un procedimiento breve y verificable. Usar cuando se pida desarrollar, modificar o revisar código.
---
# Desarrollo sencillo y verificable

1. **Entender:** leer la solicitud, las secciones pertinentes de `docs/especificacion.md` y los archivos concretos relacionados. No recorrer todo el repositorio si no es necesario.
2. **Delimitar:** escribir un mini-plan de 2 a 5 pasos, identificar archivos a cambiar y criterios de aceptación. Ante una decisión de arquitectura no especificada, consultar antes de implementarla.
3. **Implementar:** solución mínima, legible y modular; nombres expresivos, manejo de errores, entrada validada, SQL seguro, evidencias trazables. Reutilizar dependencias existentes y respetar Figma.
4. **Comprobar:** ejecutar las pruebas o verificaciones pertinentes; agregar pruebas pequeñas si cambia lógica de negocio. No afirmar que se probó lo que no se ejecutó.
5. **Revisar:** buscar sobreingeniería, duplicaciones, credenciales filtradas, consultas peligrosas y cambios ajenos a la tarea; corregir lo necesario.
6. **Entregar:** indicar qué archivos se tocaron, cómo probar, resultados reales de pruebas y qué queda pendiente en lenguaje sencillo.

## Restricciones especiales
- La IA solo redacta diagnóstico/recomendación, no modifica datos ni genera SQL ejecutable.
- La exactitud se mide comparando evidencias SQL con referencia manual, no juzgando prosa del modelo.
- No instalar paquetes, agregar capas o cambiar versiones sin explicar la razón y obtener aprobación cuando afecte el alcance.
- No iniciar otra funcionalidad o Sprint sin solicitud.
