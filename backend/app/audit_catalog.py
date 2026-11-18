"""Requisitos A–E y alcance revisado por entregable; no contiene resultados históricos."""

import json
from pathlib import Path

CATALOG = {item["numero"]: item for item in json.loads(
    Path(__file__).with_name("checklist_catalog.json").read_text(encoding="utf-8")
)}

# Un alcance completo se refiere al inventario técnico visible de la conexión,
# no a conformidad empresarial, salud de datos ni validación de la prosa de IA.
COMPLETE_DELIVERABLES = frozenset({"2.1", "3.1", "3.2", "3.3", "4.1", "4.2", "5.8", "7.1", "7.2", "8.1"})
EXTERNAL_REQUIREMENTS = {
    "1.1": "Repositorio y responsable técnico: ORM, framework y lenguaje backend no son identificables por el motor PostgreSQL.",
    "1.2": "Se necesita el diseño de capas de la aplicación y sus integraciones; un diagrama ER no constituye ese entregable.",
    "1.3": "Repositorio y documentación de despliegue para confirmar monolito, microservicios o aislamiento empresarial.",
    "1.4": "Contrastar FDW y extensiones con APIs, webhooks, colas y conexiones definidas en la aplicación.",
    "1.5": "Inventario de infraestructura para identificar servidor, cloud, contenedores y balanceadores.",
    "1.6": "Validar con negocio la correspondencia entre esquemas y dominios funcionales.",
    "1.7": "Repositorio de migraciones y bitácora aprobada; los nombres de tablas no demuestran versiones aplicadas.",
    "1.8": "Guía de nomenclatura aprobada; los patrones observados no constituyen una convención empresarial.",
    "2.2": "Validación funcional de la clasificación; nombres, persistencia y relaciones son indicios, no propósito confirmado.",
    "2.3": "Serie temporal comparable y registros de crecimiento; reltuples es una estimación, no un conteo exacto.",
    "2.4": "Carga representativa y revisión del código; ausencia de uso estadístico no demuestra obsolescencia.",
    "2.5": "Mapa de funcionalidades del backend y confirmación de responsables de cada módulo.",
    "2.6": "Validar propósito, cobertura y efectividad de las tablas candidatas con el diseño de auditoría.",
    "2.7": "Documentación funcional para confirmar el propósito de cada vista, además de sus dependencias declaradas.",
    "2.8": "Revisión del código y documentación funcional para confirmar propósito y cobertura de rutinas y triggers.",
    "3.4": "Catálogos de negocio y validaciones de aplicación complementan dominios, ENUM, DEFAULT, CHECK y FK declarados.",
    "3.5": "Revisar cálculos en consultas y aplicación; no todos los campos derivados están declarados como generados.",
    "3.6": "Diccionario de reglas aprobado y código de validaciones de la aplicación.",
    "3.7": "Validación del propietario de datos; los nombres solo sugieren sensibilidad, sin leer valores personales.",
    "3.8": "Aprobación de estándares y análisis de dependencias antes de proponer renombrados; no se modifica el esquema.",
    "3.9": "Historial de cambios y análisis de consumidores; nombres y comentarios no prueban desuso.",
    "4.3": "Ventana estadística representativa, planes y dependencias antes de eliminar índices aparentemente redundantes.",
    "4.4": "Predicados y planes de consultas reales para confirmar búsquedas frecuentes y necesidad de índices.",
    "4.5": "Historial de consultas y planes anonimizados; una instantánea no demuestra frecuencia ni causa raíz.",
    "4.6": "Medición especializada autorizada para fragmentación exacta; tamaño y tuplas muertas son solo indicadores.",
    "4.7": "Carga y planes representativos para validar orden de columnas y beneficio de índices cubrientes.",
    "4.8": "Patrones de acceso y crecimiento para evaluar la estrategia de particionamiento, no solo su configuración.",
    "5.1": "Validar las relaciones semánticas no declaradas y el alcance de la aplicación; evidencia incluye relaciones FK observadas.",
    "5.2": "Dependencias funcionales y reglas del negocio para demostrar formas normales y redundancia evitable.",
    "5.3": "Relaciones de negocio y verificaciones agregadas autorizadas de registros para confirmar huérfanos.",
    "5.4": "Cardinalidades de negocio y población de datos; las restricciones describen cardinalidad estructural permitida.",
    "5.5": "Mapa real de módulos y reglas compartidas; esquemas diferentes no equivalen necesariamente a módulos.",
    "5.6": "Relaciones N:M del negocio para confirmar tablas puente faltantes, sin deducirlas solo de nombres.",
    "5.7": "Convención aprobada de llaves y requisitos de interoperabilidad para evaluar coherencia normativa.",
    "6.1": "Planes e historial anonimizados y trazas de la aplicación para confirmar causas raíz, incluido N+1.",
    "6.2": "Proyecciones, patrones de acceso y retención empresarial para justificar particionamiento o archivado.",
    "6.3": "Carga de reportería y planes para confirmar beneficio y política de refresco de vistas materializadas.",
    "6.4": "Código y mediciones de rutinas críticas; no se ejecutan ni se modifican rutinas de la base auditada.",
    "6.5": "Política legal y empresarial de retención; estadísticas de volumen no determinan plazos de purga.",
    "6.6": "Trazas de repetición y requisitos de invalidación; caché de bloques PostgreSQL no demuestra caché de aplicación.",
    "6.7": "Recursos del servidor, carga y pool de aplicación para dimensionar parámetros sin cambiarlos.",
    "6.8": "Responsables deben estimar impacto y esfuerzo con carga y dependencias; no se inventan puntajes ni prioridades finales.",
    "7.3": "Reglas de unicidad y relaciones empresariales y comprobaciones de registros autorizadas; metadatos no prueban ausencia de duplicados.",
    "7.4": "Definición de maestros compartidos y reglas intermodulares; no se inspeccionan valores personales.",
    "7.5": "Validaciones del backend para completar la comparación con restricciones y triggers de PostgreSQL.",
    "7.6": "Diseño y pruebas controladas de transacciones críticas; configuración durable no prueba cumplimiento ACID de la aplicación.",
    "7.7": "Reglas temporales y rangos de negocio y comprobaciones agregadas aprobadas; CHECK declarados no prueban todos los datos.",
    "7.8": "Bitácora de cargas, reglas y referencia previa para atribuir inconsistencias a una migración.",
    "8.1": "Alcance: roles, membresías y privilegios declarados de la base conectada; no incluye identidades del sistema operativo.",
    "8.2": "Evidencia de almacenamiento y gestión de claves para cifrado en reposo; SSL del servidor no demuestra TLS en todas las sesiones.",
    "8.3": "Inventario de copias externas, retención y pruebas de restauración. WAL y archivado no prueban backups utilizables ni PITR operativo.",
    "8.4": "RPO/RTO definidos por negocio y ensayos de recuperación; replicación no prueba un plan de continuidad validado.",
    "8.5": "Inspección autorizada de logs anonimizados y cobertura de eventos; configuración y extensiones no prueban trazabilidad efectiva.",
    "8.6": "Evaluación de aplicabilidad normativa por responsables competentes; controles técnicos no certifican cumplimiento legal.",
    "8.7": "Inventario de ambientes, redes y accesos; nombres de bases no demuestran segregación.",
    "8.8": "Repositorio y registros de ejecución de migraciones; detectar tablas candidatas no valida historial ni control de versiones.",
    "8.9": "Se requiere el procedimiento aprobado, solicitudes, revisiones y autorizaciones de cambios; no existe en los catálogos PostgreSQL.",
    "8.10": "Políticas, linaje y pruebas autorizadas de anonimización; extensión o etiqueta no demuestran datos anonimizados.",
}
EXTERNAL_ONLY = frozenset({"1.2", "8.9"})


def definition_matches(activity) -> bool:
    """Impide atribuir al mismo número un entregable distinto del revisado."""
    definition = CATALOG.get(getattr(activity, "numero", None) or getattr(activity, "numero_original", None))
    name = getattr(activity, "actividad", None) or getattr(activity, "nombre_original", None)
    phase = getattr(activity, "fase", None) or getattr(activity, "fase_original", None)
    return bool(definition and name == definition["actividad"]
                and activity.entregable_esperado == definition["entregable_esperado"]
                and phase == definition["fase"])
