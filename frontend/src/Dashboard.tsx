import AppShell from './AppShell'
import { useEffect, useState } from 'react'
import { loadAuditHistory } from './auditApi'
import { formatAuditDate, formatDuration } from './auditPresentation'
import { ApiError } from './auth'
import type { AuditHistoryPage } from './auditTypes'

function DatabaseIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" />
    </svg>
  )
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v8M8 12h8" />
    </svg>
  )
}

type DashboardProps = {
  username: string
  onLogout: () => void | Promise<void>
  onUnauthorized: () => void
}

function Dashboard({ username, onLogout, onUnauthorized }: DashboardProps) {
  const [history, setHistory] = useState<AuditHistoryPage | null>(null)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    loadAuditHistory(offset, controller.signal).then((page) => {
      if (controller.signal.aborted) return
      setHistory(page)
      setLoading(false)
    }).catch((cause: unknown) => {
      if (controller.signal.aborted) return
      if (cause instanceof ApiError && cause.status === 401) onUnauthorized()
      else {
        setError(cause instanceof ApiError ? cause.message : 'No se pudo contactar al servidor del historial.')
        setLoading(false)
      }
    })
    return () => controller.abort()
  }, [offset, refresh, onUnauthorized])

  const changePage = (nextOffset: number) => {
    setLoading(true)
    setError('')
    setOffset(nextOffset)
  }

  return (
    <AppShell activePage="dashboard" username={username} onLogout={onLogout}>
      <main className="px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-[1120px]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-[30px] leading-tight font-bold tracking-[-0.02em] text-[#263d64] sm:text-[36px]">
                Dashboard
              </h1>
              <p className="mt-1 text-sm text-[#687b99]">Sistema de Auditoría de Bases de Datos</p>
            </div>
            <a
              href="/nueva-auditoria"
              className="flex h-11 items-center gap-2 rounded-sm bg-[#314a70] px-5 text-sm font-medium text-white transition hover:bg-[#263f62] focus-visible:ring-2 focus-visible:ring-[#314a70] focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              <PlusIcon />
              Nueva auditoría
            </a>
          </div>

          <section aria-labelledby="audits-title" className="mt-12">
            <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 id="audits-title" className="text-[24px] font-semibold text-[#263d64]">Auditorías realizadas</h2>
                <p className="mt-2 text-sm text-[#687b99]">Historial de tus auditorías guardadas</p>
              </div>
              <button type="button" disabled={loading} onClick={() => { setLoading(true); setError(''); setRefresh((value) => value + 1) }} className="rounded-md border border-[#dce5f2] bg-white px-3 py-2 text-sm text-[#42618e] disabled:opacity-50">Actualizar</button>
            </div>

            <div className="overflow-hidden rounded-xl bg-white shadow-[0_8px_22px_rgba(38,61,100,0.06)]">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse text-left">
                  <thead className="bg-[#294469] text-white">
                    <tr className="text-xs tracking-[0.05em] uppercase">
                      <th scope="col" className="px-5 py-4 font-medium">Base de datos</th>
                      <th scope="col" className="px-5 py-4 font-medium">Fecha</th>
                      <th scope="col" className="px-5 py-4 text-center font-medium">Automatización técnica</th>
                      <th scope="col" className="px-5 py-4 text-center font-medium">Tiempo SQL</th>
                      <th scope="col" className="px-5 py-4 text-center font-medium">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? <tr><td colSpan={5} className="px-5 py-10 text-center text-sm text-[#687b99]" role="status">Cargando historial…</td></tr> : error ? <tr><td colSpan={5} className="px-5 py-8 text-sm text-[#a33b32]" role="alert">{error}</td></tr> : history?.auditorias.length === 0 ? <tr><td colSpan={5} className="px-5 py-10 text-center text-sm text-[#687b99]">Todavía no tienes auditorías guardadas. Inicia una nueva auditoría para generar el primer registro.</td></tr> : history?.auditorias.map((audit, index) => (
                      <tr key={audit.id} className={`border-b border-[#e5ebf4] last:border-b-0 ${index % 2 === 1 ? 'bg-[#f8faff]' : 'bg-white'}`}>
                        <td className="px-5 py-5">
                          <span className="flex items-center gap-3 text-[15px] font-medium text-[#263d64]">
                            <span className="text-[#3568ec]"><DatabaseIcon /></span>
                            {audit.base_datos}
                            <span className="mt-1 block text-xs text-[#687b99]">{audit.checklist_version ?? 'Histórico · versión no registrada'}</span>
                          </span>
                        </td>
                        <td className="px-5 py-5 text-sm text-[#687b99]">{formatAuditDate(audit.fecha)}</td>
                        <td className="px-5 py-5 text-center text-sm font-medium text-[#263d64]">
                          <span>{audit.resumen.porcentaje_automatizacion.toLocaleString('es-CO')}%</span>
                          <span className="mt-1 block text-xs font-normal text-[#687b99]">{audit.resumen.automatizadas} de {audit.resumen.total} actividades</span>
                          {(audit.resumen.errores_sql > 0 || audit.resumen.errores_ia > 0) && <span className="mt-1 block text-xs font-normal text-[#a33b32]">Errores SQL: {audit.resumen.errores_sql} · IA: {audit.resumen.errores_ia}</span>}
                        </td>
                        <td className="px-5 py-5 text-center text-sm text-[#687b99]">{formatDuration(audit.duracion_sql_ms)}</td>
                        <td className="px-5 py-5 text-center">
                          <a href={`/auditorias/${audit.id}`} aria-label={`Ver auditoría de ${audit.base_datos} del ${formatAuditDate(audit.fecha)}`} className="inline-block rounded bg-[#eef3fb] px-4 py-1.5 text-sm text-[#42618e] hover:bg-[#dce8fa] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]">Ver</a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {!loading && !error && history && history.total > 0 && <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-[#687b99]">
              <p>{offset + 1}–{offset + history.auditorias.length} de {history.total} auditorías</p>
              <div className="flex gap-2">
                <button type="button" disabled={offset === 0} onClick={() => changePage(Math.max(0, offset - 20))} className="rounded-md border border-[#dce5f2] bg-white px-3 py-2 disabled:opacity-40">Anterior</button>
                <button type="button" disabled={offset + history.auditorias.length >= history.total} onClick={() => changePage(offset + 20)} className="rounded-md border border-[#dce5f2] bg-white px-3 py-2 disabled:opacity-40">Siguiente</button>
              </div>
            </div>}
            <p className="mt-3 text-xs leading-5 text-[#687b99]">La automatización técnica cuenta ejecuciones SQL completadas con evidencia suficiente o sin datos. Los resultados parciales y los errores se distinguen de la redacción de IA.</p>
          </section>
        </div>
      </main>
    </AppShell>
  )
}

export default Dashboard
