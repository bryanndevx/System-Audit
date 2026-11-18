import { useEffect, useRef } from 'react'
import type { MouseEvent } from 'react'
import EvidenceViewer from './EvidenceViewer'
import { activityStatus, formatDuration, humanizeKey } from './auditPresentation'
import type { ActivityResult } from './auditTypes'

const availabilityLabels = {
  disponible: 'Disponible', sin_datos: 'Sin datos', no_disponible: 'No disponible',
}
const natureLabels = {
  exacta: 'Exacta', estimada: 'Estimada', calculada: 'Calculada', no_disponible: 'Sin medición',
}

function DetailIcon({ kind }: { kind: 'evidence' | 'diagnosis' | 'recommendation' | 'clock' | 'warning' }) {
  const paths = {
    evidence: 'M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9M8 3v6h13M8 3l13 6M7 13h10M7 17h7',
    diagnosis: 'M9 3h6v3H9zM7 5H5v16h14V5h-2M8 11h8M8 15h8M8 18h4',
    recommendation: 'M9 18h6M10 21h4M8 14a6 6 0 1 1 8 0c-1 1-1 2-1 4H9c0-2 0-3-1-4Z',
    clock: 'M12 8v4l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
    warning: 'm12 3 10 18H2L12 3Zm0 6v5m0 3v1',
  }
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0 fill-none stroke-current stroke-[1.6]" strokeLinecap="round" strokeLinejoin="round">
      <path d={paths[kind]} />
    </svg>
  )
}

function ActivityDetail({ activity, onClose }: { activity: ActivityResult; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const presentation = activityStatus(activity)
  const narrative = activity.redaccion_ia
  const references = [...new Set(narrative.referencias_evidencia ?? [])].filter(
    (reference) => Number.isInteger(reference) && reference > 0 && reference <= activity.evidencias.length,
  )

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog.showModal()
    return () => {
      dialog.close()
      document.body.style.overflow = previousOverflow
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
        previousFocus.focus({ preventScroll: true })
      }
    }
  }, [])

  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target !== event.currentTarget) return
    const bounds = event.currentTarget.getBoundingClientRect()
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) {
      onClose()
    }
  }

  const showEvidence = (reference: number) => {
    const evidence = dialogRef.current?.querySelector<HTMLDetailsElement>(`[data-evidence-reference="${reference}"]`)
    if (!evidence) return
    evidence.open = true
    evidence.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'nearest',
    })
    evidence.querySelector('summary')?.focus({ preventScroll: true })
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="activity-detail-title"
      aria-describedby="activity-detail-phase"
      onCancel={(event) => { event.preventDefault(); onClose() }}
      onClick={handleBackdropClick}
      className="m-auto max-h-[calc(100dvh-1rem)] w-[calc(100%-1rem)] max-w-6xl overflow-hidden rounded-2xl border border-[#dce5f2] bg-white p-0 text-[#263d64] shadow-[0_24px_90px_rgba(16,37,65,0.25)] backdrop:bg-[#102541]/60 backdrop:backdrop-blur-sm open:flex open:flex-col sm:max-h-[calc(100dvh-3rem)] sm:w-[calc(100%-3rem)]"
    >
      <header className="shrink-0 border-b border-[#e5ebf4] bg-white px-5 py-5 sm:px-7 sm:py-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold tracking-[0.12em] text-[#687b99] uppercase">Detalle de actividad · {activity.numero_original}</p>
            <h2 id="activity-detail-title" className="mt-2 text-xl leading-snug font-semibold tracking-[-0.02em] break-words sm:text-[26px]">
              {activity.nombre_original}
            </h2>
            <p id="activity-detail-phase" className="mt-1.5 text-sm break-words text-[#687b99]">{activity.fase_original}</p>
            {activity.entregable_esperado && <p className="mt-2 text-sm text-[#536984]"><strong>Entregable:</strong> {activity.entregable_esperado}</p>}
          </div>
          <button
            autoFocus
            type="button"
            onClick={onClose}
            aria-label="Cerrar detalle"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#e5ebf4] text-[#687b99] transition hover:bg-[#f4f7fb] hover:text-[#263d64] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current stroke-2"><path d="m6 6 12 12M18 6 6 18" /></svg>
          </button>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 font-medium ${presentation.className}`}>
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{presentation.label}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#f4f7fb] px-3 py-1.5 text-[#536984]">
            <DetailIcon kind="clock" />SQL: {formatDuration(activity.duracion_ms)}
          </span>
          <span className="rounded-full bg-[#f4f7fb] px-3 py-1.5 text-[#536984]">{activity.evidencias.length} {activity.evidencias.length === 1 ? 'evidencia' : 'evidencias'}</span>
        </div>
      </header>

      <div className="min-h-0 overflow-y-auto overscroll-contain bg-[#f7f9fc] p-5 sm:p-7">
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <section aria-labelledby="evidence-section-title" className="min-w-0">
            <div className="mb-4 flex items-center gap-2.5">
              <span className="text-[#536984]"><DetailIcon kind="evidence" /></span>
              <h3 id="evidence-section-title" className="text-[15px] font-semibold">Evidencia técnica</h3>
            </div>
            <div className="space-y-3">
              {activity.evidencias.length > 0 ? activity.evidencias.map((evidence, index) => (
                <details
                  key={`${evidence.consulta_id}-${evidence.clave}-${index}`}
                  data-evidence-reference={index + 1}
                  open={index === 0}
                  className="group min-w-0 overflow-hidden rounded-xl border border-[#dce5f2] bg-white"
                >
                  <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-4 transition select-none hover:bg-[#f8faff] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#3568ec] [&::-webkit-details-marker]:hidden">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#edf3ff] text-xs font-semibold text-[#42618e]">E{index + 1}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm leading-5 font-semibold break-words">{humanizeKey(evidence.clave)}</span>
                      <span className="mt-1 block text-xs text-[#687b99]">{natureLabels[evidence.naturaleza]} · {availabilityLabels[evidence.disponibilidad]}</span>
                    </span>
                    <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 shrink-0 fill-none stroke-[#687b99] stroke-[1.5] transition-transform group-open:rotate-180 motion-reduce:transition-none"><path d="m5 8 5 5 5-5" /></svg>
                  </summary>
                  <div className="min-w-0 border-t border-[#edf1f7] p-4">
                    <EvidenceViewer value={evidence.datos} />
                    <details className="mt-4 border-t border-[#edf1f7] pt-3 text-xs text-[#687b99]">
                      <summary className="w-fit cursor-pointer rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]">Referencia de consulta</summary>
                      <p className="mt-2 font-mono break-all text-[#536984]">{evidence.consulta_id}</p>
                    </details>
                  </div>
                </details>
              )) : (
                <div className="rounded-xl border border-dashed border-[#cbd7e7] bg-white p-6 text-sm leading-6 text-[#687b99]">No se obtuvo evidencia técnica para esta actividad. Revisa el estado y las observaciones de la ejecución.</div>
              )}
            </div>
          </section>

          <div className="min-w-0 space-y-4">
            {(activity.informacion_faltante?.length ?? 0) > 0 && <section className="rounded-xl border border-[#eddfbd] bg-[#fffbf2] p-5">
              <h3 className="font-semibold text-[#886326]">Qué falta para completar la evaluación</h3>
              {(activity.informacion_obtenida?.length ?? 0) > 0 && <p className="mt-3 text-sm leading-6 text-[#536984]"><strong>Obtenido desde PostgreSQL:</strong> {activity.informacion_obtenida?.join('; ')}.</p>}
              <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-[#886326]">{activity.informacion_faltante?.map((item, index) => <li key={index}>{item}</li>)}</ul>
            </section>}
            {narrative.estado === 'generada' ? (
              <>
                <section aria-labelledby="diagnosis-title" className="rounded-xl border border-[#dce5f2] bg-white p-5">
                  <div className="flex items-center gap-2.5">
                    <span className="text-[#536984]"><DetailIcon kind="diagnosis" /></span>
                    <h3 id="diagnosis-title" className="text-[15px] font-semibold">Diagnóstico</h3>
                  </div>
                  <p className="mt-3 text-sm leading-7 whitespace-pre-wrap break-words text-[#536984]">{narrative.diagnostico}</p>
                </section>
                <section aria-labelledby="recommendation-title" className="rounded-xl border border-[#d4e0f5] bg-[#edf3ff]/60 p-5">
                  <div className="flex items-center gap-2.5">
                    <span className="text-[#42618e]"><DetailIcon kind="recommendation" /></span>
                    <h3 id="recommendation-title" className="text-[15px] font-semibold">Recomendación</h3>
                  </div>
                  <p className="mt-3 text-sm leading-7 whitespace-pre-wrap break-words text-[#536984]">{narrative.recomendacion}</p>
                </section>
                <div className="px-1 text-xs leading-5 text-[#687b99]">
                  {references.length > 0 && (
                    <div className="mb-2 flex flex-wrap items-center gap-1.5">
                      <span className="mr-1">Evidencias citadas</span>
                      {references.map((reference) => (
                        <button key={reference} type="button" onClick={() => showEvidence(reference)} aria-label={`Ver evidencia E${reference}`} className="rounded-md border border-[#d4e0f5] bg-white px-2 py-0.5 font-medium text-[#42618e] hover:bg-[#edf3ff] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]">E{reference}</button>
                      ))}
                    </div>
                  )}
                  <p>Redacción asistida por Gemini. Requiere revisión del auditor.</p>
                </div>
              </>
            ) : (
              <section role={narrative.estado === 'error' ? 'alert' : undefined} className={`rounded-xl border bg-white p-5 ${narrative.estado === 'error' ? 'border-[#f1ccc7]' : 'border-[#dce5f2]'}`}>
                <h3 className="text-[15px] font-semibold">Diagnóstico y recomendación pendientes</h3>
                <p className="mt-3 text-sm leading-6 break-words text-[#687b99]">{narrative.mensaje ?? 'Esta actividad se guardó sin una respuesta ni un error de IA registrado. El análisis automático aún no ha terminado o fue interrumpido; esto no confirma un error de Gemini. La evidencia SQL se conserva.'}</p>
              </section>
            )}

            {activity.advertencias.length > 0 && (
              <section aria-labelledby="warnings-title" className="rounded-xl border border-[#eddfbd] bg-[#fffbf2] p-5">
                <div className="flex items-center gap-2.5 text-[#886326]"><DetailIcon kind="warning" /><h3 id="warnings-title" className="text-sm font-semibold">Observaciones de ejecución</h3></div>
                <ul className="mt-3 list-disc space-y-2 pl-4 text-sm leading-6 break-words text-[#786749]">
                  {activity.advertencias.map((item, index) => <li key={index}>{item}</li>)}
                </ul>
              </section>
            )}
            {activity.limitaciones.length > 0 && (
              <details className="rounded-xl border border-[#dce5f2] bg-white px-5 py-4">
                <summary className="cursor-pointer rounded text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]">Alcance y limitaciones <span className="ml-1 font-normal text-[#687b99]">({activity.limitaciones.length})</span></summary>
                <ul className="mt-3 list-disc space-y-2 pl-4 text-sm leading-6 break-words text-[#687b99]">
                  {activity.limitaciones.map((item, index) => <li key={index}>{item}</li>)}
                </ul>
              </details>
            )}
          </div>
        </div>
      </div>

      <footer className="flex shrink-0 items-center justify-between gap-4 border-t border-[#e5ebf4] bg-white px-5 py-4 sm:px-7">
        <span className="text-xs text-[#687b99]"><kbd className="mr-1.5 rounded border border-[#dce5f2] px-1.5 py-0.5 font-sans text-[11px]">Esc</kbd> para cerrar</span>
        <button type="button" onClick={onClose} className="rounded-lg bg-[#294469] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#172f50] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]">Volver a resultados</button>
      </footer>
    </dialog>
  )
}

export default ActivityDetail
