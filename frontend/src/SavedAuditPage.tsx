import { useEffect, useState } from 'react'
import AppShell from './AppShell'
import AuditResults from './AuditResults'
import { loadSavedAudit } from './auditApi'
import { ApiError } from './auth'
import type { SavedAudit } from './auditTypes'

type SavedAuditPageProps = {
  auditId: string
  username: string
  onLogout: () => void | Promise<void>
  onUnauthorized: () => void
}

function SavedAuditPage({ auditId, username, onLogout, onUnauthorized }: SavedAuditPageProps) {
  const [record, setRecord] = useState<SavedAudit | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    loadSavedAudit(auditId, controller.signal).then((value) => {
      if (!controller.signal.aborted) setRecord(value)
    }).catch((cause: unknown) => {
      if (controller.signal.aborted) return
      if (cause instanceof ApiError && cause.status === 401) onUnauthorized()
      else setError(cause instanceof ApiError ? cause.message : 'No se pudo contactar al servidor del historial.')
    })
    return () => controller.abort()
  }, [auditId, onUnauthorized])

  if (record) return <AuditResults username={username} database={record.base_datos} result={record.resultado} source="history" onLogout={onLogout} onNewAudit={() => window.location.assign('/nueva-auditoria')} />

  return (
    <AppShell activePage="dashboard" username={username} onLogout={onLogout}>
      <main className="px-5 py-10 sm:px-10">
        <a href="/dashboard" className="text-sm text-[#42618e] underline underline-offset-4">Volver al historial</a>
        {error ? <p role="alert" className="mt-6 rounded-xl border border-[#f1ccc7] bg-white p-5 text-sm text-[#a33b32]">{error}</p> : <p role="status" className="mt-6 text-sm text-[#687b99]">Cargando auditoría guardada…</p>}
      </main>
    </AppShell>
  )
}

export default SavedAuditPage
