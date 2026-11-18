import { useEffect, useState } from 'react'
import AppShell from './AppShell'
import type { ImportedPhase } from './auditTypes'
import type { AuditProgressEvent } from './auditApi'

type AuditProgressProps = {
  username: string
  database: string
  phases: ImportedPhase[]
  startedAt: number
  onLogout: () => void | Promise<void>
  events: AuditProgressEvent[]
  stage: string
}

function formatElapsed(milliseconds: number) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return minutes > 0 ? `${minutes} min ${seconds} s` : `${seconds} s`
}

function AuditProgress({
  username,
  database,
  phases,
  startedAt,
  onLogout,
  events,
  stage,
}: AuditProgressProps) {
  const [elapsed, setElapsed] = useState(() => Date.now() - startedAt)
  const totalActivities = phases.reduce(
    (total, phase) => total + phase.actividades.length,
    0,
  )

  useEffect(() => {
    const timer = window.setInterval(() => {
      setElapsed(Date.now() - startedAt)
    }, 250)
    return () => window.clearInterval(timer)
  }, [startedAt])

  return (
    <AppShell
      activePage="new-audit"
      username={username}
      onLogout={onLogout}
      serverLabel={database}
      serverConnected
    >
      <main className="px-5 py-8 sm:px-8 lg:px-10 lg:py-9">
        <div className="mx-auto max-w-[1120px]">
          <section className="rounded-xl bg-white p-5 shadow-[0_8px_22px_rgba(38,61,100,0.06)] sm:p-7">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <h1 className="text-[30px] leading-tight font-bold tracking-[-0.02em] text-[#263d64] sm:text-[36px]">
                Ejecutando…
              </h1>
              <span className="rounded-md bg-[#edf3ff] px-4 py-2 text-sm text-[#687b99]">
                Base de datos: <strong className="text-[#263d64]">{database}</strong>
              </span>
            </div>

            <dl className="mt-6 grid gap-4 rounded-lg bg-[#edf3ff] p-5 sm:grid-cols-3">
              <div>
                <dt className="text-sm text-[#687b99]">Progreso</dt>
                <dd className="mt-1 text-xl font-semibold text-[#263d64]">{Math.round(events.length / Math.max(1, totalActivities) * 100)}%</dd>
              </div>
              <div>
                <dt className="text-sm text-[#687b99]">Actividades procesadas / total</dt>
                <dd className="mt-1 text-xl font-semibold text-[#263d64]">{events.length} de {totalActivities}</dd>
              </div>
              <div>
                <dt className="text-sm text-[#687b99]">Tiempo transcurrido</dt>
                <dd className="mt-1 text-xl font-semibold text-[#263d64]">{formatElapsed(elapsed)}</dd>
              </div>
            </dl>

            <div
              role="progressbar" aria-label="Actividades procesadas" aria-valuemin={0} aria-valuemax={totalActivities} aria-valuenow={events.length}
              className="mt-5 h-3 overflow-hidden rounded-full bg-[#dce7f8]"
            >
              <div className="h-full rounded-full bg-[#294469] transition-[width]" style={{ width: `${events.length / Math.max(1, totalActivities) * 100}%` }} />
            </div>
            <p className="mt-3 text-xs text-[#687b99]">
              {stage}. Este progreso indica actividades procesadas; el porcentaje de automatización se calcula según la cobertura de sus entregables.
            </p>
          </section>

          <div className="mt-6 space-y-5">
            {phases.map((phase) => (
              <section key={phase.nombre} className="rounded-xl bg-white p-5 shadow-[0_8px_22px_rgba(38,61,100,0.06)]">
                <div className="flex items-center justify-between gap-4 rounded-md bg-[#edf3ff] px-4 py-3">
                  <h2 className="font-semibold text-[#263d64]">{phase.nombre}</h2>
                  <span className="text-sm text-[#687b99]">{phase.actividades.filter((activity) => events.some((event) => event.identificador === activity.numero)).length} / {phase.actividades.length}</span>
                </div>
                <ul className="mt-2 divide-y divide-[#edf1f7]">
                  {phase.actividades.map((activity) => (
                    <li key={activity.numero} className="flex items-center justify-between gap-4 px-3 py-3 text-sm">
                      <span className="text-[#263d64]">
                        <span className="mr-2 text-[#687b99]">{activity.numero}</span>
                        {activity.actividad}
                      </span>
                      <span className="shrink-0 rounded bg-[#eef3fb] px-2 py-1 text-xs text-[#687b99]" title="El estado final se calcula después de interpretar las evidencias">Incompleta</span>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </div>
      </main>
    </AppShell>
  )
}

export default AuditProgress
