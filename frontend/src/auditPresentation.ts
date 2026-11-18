import type { ActivityExecutionStatus, ActivityResult } from './auditTypes'

export const statusPresentation: Record<
  ActivityExecutionStatus,
  { label: string; className: string }
> = {
  completada: { label: 'Completada', className: 'bg-[#e3f6ed] text-[#167052]' },
  parcial: { label: 'Parcial', className: 'bg-[#fff2d8] text-[#9b5a16]' },
  error_tecnico: { label: 'Error técnico', className: 'bg-[#fde9e7] text-[#a33b32]' },
  sin_automatizacion_configurada: { label: 'Sin automatización', className: 'bg-[#eef3fb] text-[#687b99]' },
  no_ejecutable: { label: 'Requiere información externa', className: 'bg-[#eef3fb] text-[#687b99]' },
}

export const coverageLabels = {
  total: 'Completa', parcial: 'Parcial', no_automatizada: 'Externa', error: 'Error técnico', sin_configuracion: 'Sin configuración',
}

export const deliverableLabels = {
  completo: 'Entregable completo',
  requiere_informacion_externa: 'Requiere información externa · incompleta',
  evidencia_incompleta: 'Evidencia PostgreSQL incompleta',
  error_tecnico: 'Error técnico', sin_configuracion: 'Sin configuración',
}

export function deliverableLabel(activity: ActivityResult) {
  return activityStatus(activity).label
}

export function activityStatus(activity: ActivityResult) {
  const completed = activity.estado_actividad === 'completada' || (!activity.estado_actividad && activity.grado_automatizacion === 'total' && activity.redaccion_ia.estado === 'generada' && Boolean(activity.redaccion_ia.diagnostico && activity.redaccion_ia.recomendacion))
  return completed ? { label: 'Completada', className: 'bg-[#e3f6ed] text-[#167052]' }
    : { label: 'Incompleta', className: 'bg-[#fff2d8] text-[#9b5a16]' }
}

export function formatDuration(milliseconds: number) {
  if (milliseconds < 1000) return `${milliseconds} ms`
  const totalSeconds = Math.round(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return minutes > 0 ? `${minutes} min ${seconds} s` : `${seconds} s`
}

export function humanizeKey(key: string) {
  const text = key.replaceAll('_', ' ').trim()
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : key
}

export function formatAuditDate(value: string) {
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Bogota',
  }).format(new Date(value))
}
