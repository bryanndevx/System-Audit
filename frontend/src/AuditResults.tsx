import { useEffect, useMemo, useState } from 'react'
import AppShell from './AppShell'
import ActivityDetail from './ActivityDetail'
import { loadSavedAudit, resumeAuditAi } from './auditApi'
import { ApiError } from './auth'
import { activityStatus, formatAuditDate, formatDuration } from './auditPresentation'
import type {
  ActivityResult,
  AuditExecutionResponse,
} from './auditTypes'

type AuditResultsProps = {
  username: string
  database: string
  result: AuditExecutionResponse
  onNewAudit: () => void
  onLogout: () => void | Promise<void>
  source?: 'execution' | 'history'
}

function AuditResults({
  username,
  database,
  result: initialResult,
  onNewAudit,
  onLogout,
  source = 'execution',
}: AuditResultsProps) {
  const [result, setResult] = useState(initialResult)
  const [aiStatus, setAiStatus] = useState('')
  const [selectedActivity, setSelectedActivity] = useState<ActivityResult | null>(null)
  useEffect(() => {
    const id = initialResult.almacenamiento?.id
    const needsResume = (value: AuditExecutionResponse) =>
      value.checklist_version === 'postgresql-tecnico-v1' &&
      !value.actividades.some(a => a.redaccion_ia.estado === 'error') &&
      value.actividades.some(a => a.redaccion_ia.estado === 'no_solicitada' ||
        (a.redaccion_ia.estado === 'no_configurada' && !a.redaccion_ia.mensaje))
    if (!id || !needsResume(initialResult)) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    const apply = (updated: AuditExecutionResponse) => {
      if (controller.signal.aborted) return
      setResult(updated)
      setSelectedActivity(previous => previous ? updated.actividades.find(a => a.identificador === previous.identificador) ?? null : null)
    }
    const poll = async (remaining: number) => {
      try {
        const record = await loadSavedAudit(id, controller.signal)
        apply(record.resultado)
        if (!needsResume(record.resultado)) {
          if (!controller.signal.aborted) setAiStatus('Análisis automático terminado. Revise el diagnóstico o la causa registrada en cada actividad.')
        } else if (remaining > 0 && !controller.signal.aborted) {
          timer = setTimeout(() => void poll(remaining - 1), 5000)
        } else if (!controller.signal.aborted) {
          setAiStatus('El análisis sigue pendiente. Las evidencias están guardadas; al volver a abrir el registro se comprobará su recuperación.')
        }
      } catch (error) {
        if (!controller.signal.aborted) setAiStatus(error instanceof Error ? error.message : 'No se pudo consultar el avance del análisis.')
      }
    }
    void (async () => {
      if (!controller.signal.aborted) setAiStatus('Procesando automáticamente los textos pendientes con las evidencias guardadas…')
      try {
        const updated = await resumeAuditAi(id)
        apply(updated)
        if (!controller.signal.aborted) setAiStatus('Análisis automático terminado. Revise el diagnóstico o la causa registrada en cada actividad.')
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 409) {
          setAiStatus('El análisis automático ya está en curso. Consultando su avance…')
          await poll(60)
        } else setAiStatus(error instanceof Error ? error.message : 'No se pudo terminar el análisis automático. La evidencia SQL está guardada.')
      }
    })()
    return () => { controller.abort(); if (timer) clearTimeout(timer) }
  }, [initialResult])
  const [pdfStatus, setPdfStatus] = useState('')
  const [exporting, setExporting] = useState(false)
  const exportPdf = async () => {
    const id = result.almacenamiento?.id
    if (!id) return
    setExporting(true)
    setPdfStatus('')
    try {
      const response = await fetch(`/api/audits/${id}/pdf`, { credentials: 'same-origin' })
      if (!response.ok) throw new Error(response.status === 401 ? 'Su sesión expiró; vuelva a iniciar sesión.' : 'No fue posible exportar el informe. Intente nuevamente.')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = `auditoria-${id}.pdf`
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setPdfStatus('Informe descargado.')
    } catch (error) {
      setPdfStatus(error instanceof Error ? error.message : 'No fue posible exportar el informe.')
    } finally {
      setExporting(false)
    }
  }
  const groupedActivities = useMemo(() => {
    const groups: [string, ActivityResult[]][] = []
    for (const activity of result.actividades) {
      const last = groups.at(-1)
      if (last?.[0] === activity.fase_original) last[1].push(activity)
      else groups.push([activity.fase_original, [activity]])
    }
    return groups
  }, [result.actividades])

  const configured = result.actividades.filter(
    (activity) => activity.estado_ejecucion !== 'sin_automatizacion_configurada',
  ).length
  const aiErrors = result.actividades.filter((activity) => activity.redaccion_ia.estado === 'error').length
  const aiPending = result.actividades.filter((activity) => activity.redaccion_ia.estado === 'no_solicitada').length
  const coverage = result.actividades.length
    ? Math.round((configured / result.actividades.length) * 100)
    : 0
  const summary = result.resumen
  const legacyCoverage = result.checklist_version !== 'postgresql-tecnico-v1'
  const storage = result.almacenamiento

  return (
    <AppShell
      activePage={source === 'history' ? 'dashboard' : 'new-audit'}
      username={username}
      onLogout={onLogout}
      serverLabel={database}
      serverConnected
    >
      <main className="px-5 py-8 sm:px-8 lg:px-10 lg:py-9">
        <div className="mx-auto max-w-[1120px]">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              {source === 'history' && <a href="/dashboard" className="mb-3 inline-block text-sm text-[#42618e] underline underline-offset-4">Volver al historial</a>}
              <h1 className="text-[30px] font-bold tracking-[-0.02em] text-[#263d64] sm:text-[36px]">Resultados</h1>
              <p className="mt-1 text-sm text-[#687b99]">{database}{storage?.estado === 'guardada' && storage.fecha ? ` · Guardada el ${formatAuditDate(storage.fecha)}` : ' · Resultado de la ejecución actual'}</p>
              <p className="mt-1 text-xs text-[#687b99]">Checklist: {result.checklist_version ?? 'Histórico · versión no registrada'}{result.criterios_evaluacion_version ? ` · ${result.criterios_evaluacion_version}` : ''}</p>
            </div>
            <button type="button" onClick={onNewAudit} className="h-11 rounded-sm bg-[#314a70] px-5 text-sm font-medium text-white hover:bg-[#263f62]">＋ Nueva auditoría</button>
          </div>
          {storage?.estado === 'error' && <div role="alert" className="mt-5 rounded-lg border border-[#eddfbd] bg-[#fffbf2] px-4 py-3 text-sm leading-6 text-[#886326]">
            <strong>Esta auditoría no se guardó en el historial.</strong> {storage.mensaje} Conserva esta pantalla abierta para consultar la evidencia.
          </div>}
          {legacyCoverage && <p className="mt-5 rounded-lg bg-[#fffbf2] p-4 text-sm leading-6 text-[#886326]">Este registro usa el criterio histórico de ejecución y no acredita cobertura completa por entregable con el catálogo actual.</p>}

          <dl className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              [legacyCoverage ? 'Completadas (criterio histórico)' : 'Completadas', summary?.automatizadas ?? configured],
              ['Incompletas', (summary?.total ?? result.actividades.length) - (summary?.automatizadas ?? 0)],
              [legacyCoverage ? 'Porcentaje histórico' : 'Automatización', `${summary?.porcentaje_automatizacion.toLocaleString('es-CO') ?? coverage}%`],
              ['Tiempo total', formatDuration(result.duracion_ejecucion_ms ?? result.duracion_total_ms + result.duracion_ia_ms)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-[#294469] px-5 py-5 text-center text-white">
                <dt className="text-sm text-white/85">{label}</dt>
                <dd className="mt-2 text-3xl font-semibold">{value}</dd>
              </div>
            ))}
          </dl>
          {summary && <p className="mt-3 text-sm leading-6 text-[#687b99]">Evaluadas: {summary.total}. Una actividad completada requiere evidencia suficiente, diagnóstico y recomendación válidos. Un control deshabilitado puede evaluarse completamente; los motivos técnicos de una evaluación incompleta se conservan en su detalle.</p>}
          <p className="mt-3 text-sm text-[#687b99]">
            Redacción IA: {formatDuration(result.duracion_ia_ms)}.
            {aiErrors > 0 && <span role="alert" className="ml-2 text-[#a33b32]">{aiErrors} actividades con error de IA; su evidencia SQL se conserva.</span>}
            {aiPending > 0 && <span className="ml-2">{aiPending} redacciones pendientes: no se enviaron a Gemini tras el fallo de un lote anterior.</span>}
          </p>
          {aiStatus && <p role="status" className="mt-3 text-sm text-[#687b99]">{aiStatus}</p>}

          <section className="mt-8 overflow-hidden rounded-xl bg-white p-4 shadow-[0_8px_22px_rgba(38,61,100,0.06)]">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] border-collapse text-left text-sm">
                <thead className="bg-[#edf3ff] text-xs tracking-[0.04em] text-[#536984] uppercase">
                  <tr>
                    <th className="px-4 py-3 font-medium">Actividad</th>
                    <th className="px-4 py-3 text-center font-medium">Estado</th>
                    <th className="px-4 py-3 text-center font-medium">Tiempo</th>
                    <th className="px-4 py-3 text-center font-medium">Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {groupedActivities.map(([phase, activities], index) => (
                    <FragmentRows key={`${phase}-${index}`} phase={phase} activities={activities} onView={setSelectedActivity} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="mt-7 flex flex-col items-end gap-2">
            <button type="button" onClick={exportPdf} disabled={exporting || storage?.estado !== 'guardada'} className="h-11 rounded-sm bg-[#172f50] px-6 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">{exporting ? 'Preparando PDF…' : 'Exportar PDF'}</button>
            <p role="status" className="text-sm text-[#687b99]">{pdfStatus || (storage?.estado !== 'guardada' ? 'El PDF requiere una auditoría guardada en el historial.' : '')}</p>
          </div>
        </div>
      </main>

      {selectedActivity && (
        <ActivityDetail activity={selectedActivity} onClose={() => setSelectedActivity(null)} />
      )}
    </AppShell>
  )
}

function FragmentRows({
  phase,
  activities,
  onView,
}: {
  phase: string
  activities: ActivityResult[]
  onView: (activity: ActivityResult) => void
}) {
  return (
    <>
      <tr className="bg-[#e3edfc]">
        <th colSpan={4} className="px-4 py-3 font-semibold text-[#263d64]">{phase}</th>
      </tr>
      {activities.map((activity, index) => {
        const presentation = activityStatus(activity)
        return (
          <tr key={activity.identificador} className={`border-b border-[#edf1f7] ${index % 2 ? 'bg-[#f8faff]' : 'bg-white'}`}>
            <td className="px-4 py-3 text-[#263d64]">
              <span className="mr-2 text-[#687b99]">{activity.numero_original}</span>
              {activity.nombre_original}
            </td>
            <td className="px-4 py-3 text-center">
              <span className={`inline-block rounded-full px-3 py-1 text-xs font-medium ${presentation.className}`}>{presentation.label}</span>
            </td>
            <td className="px-4 py-3 text-center text-[#687b99]">{formatDuration(activity.duracion_ms)}</td>
            <td className="px-4 py-3 text-center">
              <button type="button" onClick={() => onView(activity)} className="rounded bg-[#eef3fb] px-4 py-1.5 text-sm text-[#3568ec] hover:bg-[#dce8fa]">Ver</button>
            </td>
          </tr>
        )
      })}
    </>
  )
}

export default AuditResults
