import { ApiError, restoreSession } from './auth'
import type { AuditExecutionResponse, AuditHistoryPage, SavedAudit } from './auditTypes'

async function readHistory<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', signal })
  if (!response.ok) {
    const error = await response.json().catch(() => null) as { detail?: unknown } | null
    throw new ApiError(response.status, typeof error?.detail === 'string' ? error.detail : 'No fue posible consultar el historial.')
  }
  return await response.json() as T
}

export function loadAuditHistory(offset: number, signal: AbortSignal) {
  return readHistory<AuditHistoryPage>(`/api/audits?limit=20&offset=${offset}`, signal)
}

export function loadSavedAudit(id: string, signal: AbortSignal) {
  return readHistory<SavedAudit>(`/api/audits/${encodeURIComponent(id)}`, signal)
}

const pendingAnalyses = new Map<string, Promise<AuditExecutionResponse>>()

export function resumeAuditAi(id: string): Promise<AuditExecutionResponse> {
  const pending = pendingAnalyses.get(id)
  if (pending) return pending
  const operation = retryAuditAi(id).finally(() => pendingAnalyses.delete(id))
  pendingAnalyses.set(id, operation)
  return operation
}

async function retryAuditAi(id: string): Promise<AuditExecutionResponse> {
  const session = await restoreSession()
  if (!session) throw new ApiError(401, 'Su sesión expiró; vuelva a iniciar sesión.')
  const response = await fetch(`/api/audits/${encodeURIComponent(id)}/retry-ai`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'X-CSRF-Token': session.csrf_token },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new ApiError(response.status, body?.detail ?? 'No fue posible terminar el análisis. Las evidencias guardadas se conservan.')
  }
  return await response.json() as AuditExecutionResponse
}

export type AuditProgressEvent = { tipo: string; identificador?: string; procesadas?: number; total?: number; estado?: string; grado?: string; etapa?: string }

export async function readAuditStream(response: Response, onProgress: (event: AuditProgressEvent) => void): Promise<AuditExecutionResponse> {
  if (!response.body) throw new Error('El navegador no recibió la respuesta del backend.')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let pending = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      pending += decoder.decode(value, { stream: !done })
      const lines = pending.split('\n')
      pending = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.trim()) continue
        const event = JSON.parse(line) as AuditProgressEvent & { resultado?: AuditExecutionResponse; mensaje?: string }
        if (event.tipo === 'error') throw new Error(event.mensaje || 'No se pudo completar la auditoría.')
        if (event.tipo === 'resultado' && event.resultado) return event.resultado
        onProgress(event)
      }
      if (done) throw new Error('La conexión terminó antes de recibir los resultados. Consulte el historial antes de repetir la auditoría.')
    }
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
