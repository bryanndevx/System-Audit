export type ImportedActivity = {
  numero: string
  actividad: string
  entregable_esperado: string | null
  prioridad: string | null
  numero_hoja?: string | null
}

export type ImportedPhase = {
  nombre: string
  actividades: ImportedActivity[]
}

export type ChecklistImportResponse = {
  nombre_archivo: string
  cantidad_fases: number
  cantidad_actividades: number
  fases: ImportedPhase[]
  checklist_version?: string
  checklist_huella?: string | null
}

export type ActivityExecutionStatus =
  | 'completada'
  | 'parcial'
  | 'error_tecnico'
  | 'sin_automatizacion_configurada'
  | 'no_ejecutable'

export type EvidenceStatus =
  | 'suficiente'
  | 'insuficiente'
  | 'sin_datos'
  | 'no_obtenida'

export type ActivityEvidence = {
  clave: string
  consulta_id: string
  disponibilidad: 'disponible' | 'sin_datos' | 'no_disponible'
  naturaleza: 'exacta' | 'estimada' | 'calculada' | 'no_disponible'
  datos: unknown
}

export type ActivityResult = {
  identificador: string
  numero_original: string
  nombre_original: string
  fase_original: string
  entregable_esperado?: string | null
  prioridad_original?: string | null
  numero_hoja?: string | null
  grado_automatizacion?: 'total' | 'parcial' | 'no_automatizada' | 'error' | 'sin_configuracion' | null
  consultas?: { consulta_id: string; estado: string; filas: number; reutilizada: boolean; duracion_ms: number }[]
  estado_entregable?: 'completo' | 'requiere_informacion_externa' | 'evidencia_incompleta' | 'error_tecnico' | 'sin_configuracion' | null
  informacion_obtenida?: string[]
  informacion_faltante?: string[]
  estado_actividad?: 'completada' | 'incompleta' | null
  motivo_incompleta?: string | null
  estado_ejecucion: ActivityExecutionStatus
  estado_evidencia: EvidenceStatus
  evidencias: ActivityEvidence[]
  advertencias: string[]
  limitaciones: string[]
  duracion_ms: number
  redaccion_ia: {
    estado: 'generada' | 'error' | 'no_configurada' | 'no_aplica' | 'no_solicitada'
    diagnostico: string | null
    recomendacion: string | null
    referencias_evidencia: number[]
    mensaje: string | null
    proveedor: 'gemini'
    modelo: string | null
    criterios_version: string
    contexto_version: string
  }
}

export type AuditExecutionResponse = {
  catalogo_version: string
  actividades: ActivityResult[]
  duracion_total_ms: number
  duracion_ia_ms: number
  nombre_aplicacion?: string | null
  entorno_auditado?: string | null
  fecha_ejecucion?: string | null
  checklist_version?: string | null
  checklist_huella?: string | null
  criterios_evaluacion_version?: string | null
  duracion_ejecucion_ms?: number | null
  resumen?: AuditSummary | null
  almacenamiento?: {
    estado: 'guardada' | 'error' | 'no_guardada'
    id: string | null
    fecha: string | null
    mensaje: string | null
  }
}

export type AuditSummary = {
  total: number
  automatizadas: number
  parciales: number
  errores_sql: number
  sin_configuracion: number
  errores_ia: number
  porcentaje_automatizacion: number
  no_ejecutables?: number
  porcentaje_parcial?: number
  requieren_informacion_externa?: number
  con_evidencia_postgresql?: number
}

export type AuditHistoryItem = {
  id: string
  base_datos: string
  checklist_version?: string | null
  fecha: string
  resumen: AuditSummary
  duracion_sql_ms: number
  duracion_ia_ms: number
}

export type AuditHistoryPage = {
  auditorias: AuditHistoryItem[]
  total: number
  limite: number
  desplazamiento: number
}

export type SavedAudit = {
  id: string
  base_datos: string
  fecha: string
  resultado: AuditExecutionResponse
}
