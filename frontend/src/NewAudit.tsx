import { useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import AppShell from './AppShell'
import AuditProgress from './AuditProgress'
import AuditResults from './AuditResults'
import ElevatedPrivilegesDialog from './ElevatedPrivilegesDialog'
import { readAuditStream } from './auditApi'
import type { AuditProgressEvent } from './auditApi'
import type {
  AuditExecutionResponse,
  ChecklistImportResponse,
} from './auditTypes'

type ImportStatus = 'idle' | 'loading' | 'success' | 'error'
type ConnectionStatus = 'idle' | 'testing' | 'success' | 'error'
type AuditStatus = 'idle' | 'running' | 'success' | 'error'

type ConnectionFields = {
  host: string
  port: string
  database: string
  username: string
  password: string
}

type ConnectionTestResponse = {
  verified: boolean
  message: string
}

type NewAuditProps = {
  username: string
  csrfToken: string
  onLogout: () => void | Promise<void>
  onUnauthorized: () => void
}

const inputClass =
  'h-11 w-full rounded-[8px] border border-[#d6dfec] bg-white px-4 text-sm text-[#263d64] outline-none transition placeholder:text-[#8a9ab1] focus:border-[#42658f] focus:ring-2 focus:ring-[#42658f]/20'

function UploadIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-7 w-7 fill-none stroke-current stroke-2">
      <path d="M7 3h8l4 4v14H7V3Z" />
      <path d="M14 3v5h5M12 17V10M9 13l3-3 3 3" />
    </svg>
  )
}

function ChecklistIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
      <path d="M4 5h16v15H4V5ZM8 5V3m8 2V3M4 9h16M8 12v5m4-5v5m4-5v5" />
    </svg>
  )
}

function LinkIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
      <path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.2 1.2M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.2-1.2M8 12h8" />
    </svg>
  )
}

function EyeIcon({ crossed = false }: { crossed?: boolean }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
      <path d="M2.5 12s3.5-5.5 9.5-5.5 9.5 5.5 9.5 5.5-3.5 5.5-9.5 5.5S2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.5" />
      {crossed && <path d="m3 3 18 18" />}
    </svg>
  )
}

function NewAudit({
  username,
  csrfToken,
  onLogout,
  onUnauthorized,
}: NewAuditProps) {
  const [selectedFileName, setSelectedFileName] = useState('')
  const [importStatus, setImportStatus] = useState<ImportStatus>('idle')
  const [importError, setImportError] = useState('')
  const [importedChecklist, setImportedChecklist] =
    useState<ChecklistImportResponse | null>(null)
  const [isPasswordVisible, setIsPasswordVisible] = useState(false)
  const [connectionFields, setConnectionFields] = useState<ConnectionFields>({
    host: '',
    port: '',
    database: '',
    username: '',
    password: '',
  })
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>('idle')
  const [connectionMessage, setConnectionMessage] = useState(
    'Pendiente de comprobación',
  )
  const [auditStatus, setAuditStatus] = useState<AuditStatus>('idle')
  const [auditMessage, setAuditMessage] = useState(
    'Se habilitará con checklist válido y conexión verificada.',
  )
  const [auditStartedAt, setAuditStartedAt] = useState(0)
  const [progressEvents, setProgressEvents] = useState<AuditProgressEvent[]>([])
  const [progressStage, setProgressStage] = useState('Obteniendo evidencias PostgreSQL')
  const [auditResult, setAuditResult] =
    useState<AuditExecutionResponse | null>(null)
  const connectionAttempt = useRef(0)
  const [elevatedPrivileges, setElevatedPrivileges] = useState<string[] | null>(null)
  const [elevatedConfirmed, setElevatedConfirmed] = useState(false)
  const [continuationAllowed, setContinuationAllowed] = useState(true)
  const auditAttempt = useRef(0)
  const displayedImportStatus: ImportStatus = importedChecklist
    ? 'success'
    : importStatus
  const canStartAudit =
    importedChecklist !== null && connectionStatus === 'success'

  const resetAuditExecution = () => {
    auditAttempt.current += 1
    setAuditStatus('idle')
    setAuditResult(null)
    setAuditMessage(
      'Se habilitará con checklist válido y conexión verificada.',
    )
  }

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    setSelectedFileName(file?.name ?? '')
    setImportedChecklist(null)
    setImportError('')
    resetAuditExecution()

    if (!file) {
      setImportStatus('idle')
      return
    }

    setImportStatus('loading')
    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('/api/checklists/import', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrfToken },
        body: formData,
      })

      if (!response.ok) {
        const errorBody = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null
        if (response.status === 401) onUnauthorized()
        throw new Error(
          errorBody?.detail ?? 'No fue posible importar el checklist.',
        )
      }

      const result = (await response.json()) as ChecklistImportResponse
      setImportedChecklist(result)
      setImportStatus('success')
      if (connectionStatus === 'success') {
        setAuditMessage(
          'Checklist y conexión listos para ejecutar el motor técnico.',
        )
      }
    } catch (error) {
      setImportStatus('error')
      setImportError(
        error instanceof TypeError
          ? 'No se pudo contactar al servidor de importación.'
          : error instanceof Error
          ? error.message
          : 'No fue posible importar el checklist.',
      )
    }
  }

  const handleConnectionFieldChange = (event: ChangeEvent<HTMLInputElement>) => {
    setElevatedConfirmed(false)
    setElevatedPrivileges(null)
    const field = event.target.name as keyof ConnectionFields
    connectionAttempt.current += 1
    setConnectionFields((current) => ({
      ...current,
      [field]: event.target.value,
    }))
    setConnectionStatus('idle')
    setConnectionMessage('Pendiente de comprobación')
    resetAuditExecution()
  }

  const handleConnectionTest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await checkConnection(false)
  }

  const checkConnection = async (confirmElevated: boolean) => {
    setElevatedConfirmed(false)
    const attempt = connectionAttempt.current + 1
    connectionAttempt.current = attempt
    setConnectionStatus('testing')
    setConnectionMessage('Comprobando…')

    try {
      const response = await fetch('/api/connections/test', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({
          ...connectionFields,
          port: Number(connectionFields.port),
          confirmar_privilegios_elevados: confirmElevated,
        }),
      })

      if (!response.ok) {
        const errorBody = (await response.json().catch(() => null)) as
          | { detail?: string | { code?: string; message?: string; privileges?: string[]; continuation_allowed?: boolean } }
          | null
        if (attempt !== connectionAttempt.current) return
        if (response.status === 409 && typeof errorBody?.detail === 'object' && errorBody.detail.code === 'elevated_privileges_confirmation_required') {
          setConnectionStatus('idle')
          setConnectionMessage('La cuenta requiere confirmación por sus privilegios elevados.')
          setElevatedPrivileges(errorBody.detail.privileges ?? [])
          setContinuationAllowed(errorBody.detail.continuation_allowed !== false)
          return
        }
        if (response.status === 401) onUnauthorized()
        throw new Error(
          typeof errorBody?.detail === 'string'
            ? errorBody.detail
            : 'No fue posible comprobar la conexión.',
        )
      }

      const result = (await response.json()) as ConnectionTestResponse
      if (attempt !== connectionAttempt.current) return
      setElevatedConfirmed(result.verified && confirmElevated)
      setConnectionStatus(result.verified ? 'success' : 'error')
      setConnectionMessage(
        result.verified
          ? result.message
          : 'No fue posible comprobar la conexión.',
      )
      if (result.verified && importedChecklist) {
        setAuditMessage(
          'Checklist y conexión listos para ejecutar el motor técnico.',
        )
      }
    } catch (error) {
      if (attempt !== connectionAttempt.current) return
      setConnectionStatus('error')
      setConnectionMessage(
        error instanceof TypeError
          ? 'No se pudo contactar al servidor de comprobación.'
          : error instanceof Error
            ? error.message
            : 'No fue posible comprobar la conexión.',
      )
    }
  }

  const handleStartAudit = async () => {
    if (!importedChecklist || connectionStatus !== 'success') return

    const attempt = auditAttempt.current + 1
    auditAttempt.current = attempt
    setAuditStartedAt(Date.now())
    setProgressEvents([])
    setProgressStage('Obteniendo evidencias PostgreSQL')
    setAuditResult(null)
    setAuditStatus('running')
    setAuditMessage('Ejecutando actividades técnicas configuradas…')

    const activities = importedChecklist.fases.flatMap((phase) =>
      phase.actividades.map((activity) => ({
        numero: activity.numero,
        actividad: activity.actividad,
        fase: phase.nombre,
        entregable_esperado: activity.entregable_esperado,
        prioridad: activity.prioridad,
        numero_hoja: activity.numero_hoja,
      })),
    )

    try {
      const response = await fetch('/api/audits/execute-stream', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({
          conexion: {
            ...connectionFields,
            port: Number(connectionFields.port),
            confirmar_privilegios_elevados: elevatedConfirmed,
          },
          actividades: activities,
          checklist_version: importedChecklist.checklist_version,
        }),
      })

      if (!response.ok) {
        const errorBody = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null
        if (response.status === 401) onUnauthorized()
        throw new Error(
          typeof errorBody?.detail === 'string'
            ? errorBody.detail
            : 'No fue posible ejecutar la auditoría técnica.',
        )
      }

      const result = await readAuditStream(response, (event) => {
        if (attempt !== auditAttempt.current) return
        if (event.tipo === 'actividad') setProgressEvents((previous) => [...previous, event])
        if (event.tipo === 'etapa' && event.etapa) setProgressStage(event.etapa)
      })
      if (attempt !== auditAttempt.current) return
      const unconfigured = result.actividades.filter(
        (activity) =>
          activity.estado_ejecucion === 'sin_automatizacion_configurada',
      ).length
      const technicalErrors = result.actividades.filter(
        (activity) => activity.estado_ejecucion === 'error_tecnico',
      ).length
      const aiErrors = result.actividades.filter(
        (activity) => activity.redaccion_ia.estado === 'error',
      ).length
      const configured = result.actividades.length - unconfigured
      const seconds = (result.duracion_total_ms / 1000).toFixed(2)

      setAuditResult(result)
      setConnectionFields((previous) => ({ ...previous, password: '' }))
      setAuditStatus('success')
      setAuditMessage(
        `Ejecución finalizada: ${result.actividades.length} actividades evaluadas; ` +
          `${configured} con automatización configurada y ${unconfigured} sin automatización configurada. ` +
          `${technicalErrors} errores técnicos y ${aiErrors} errores de IA. Tiempo SQL: ${seconds} s.`,
      )
    } catch (error) {
      if (attempt !== auditAttempt.current) return
      setAuditStatus('error')
      setConnectionStatus('idle')
      setConnectionMessage(
        'Vuelva a introducir la contraseña y compruebe la conexión.',
      )
      setAuditMessage(
        error instanceof TypeError
          ? 'No se pudo contactar al motor de auditoría.'
          : error instanceof Error
            ? error.message
            : 'No fue posible ejecutar la auditoría técnica.',
      )
    } finally {
      setConnectionFields((current) => ({
        ...current,
        password: '',
      }))
    }
  }

  const handleNewAudit = () => {
    setElevatedConfirmed(false)
    setElevatedPrivileges(null)
    auditAttempt.current += 1
    connectionAttempt.current += 1
    setSelectedFileName('')
    setImportedChecklist(null)
    setImportStatus('idle')
    setImportError('')
    setConnectionFields({
      host: '',
      port: '',
      database: '',
      username: '',
      password: '',
    })
    setConnectionStatus('idle')
    setConnectionMessage('Pendiente de comprobación')
    setAuditStatus('idle')
    setAuditResult(null)
    setAuditMessage(
      'Se habilitará con checklist válido y conexión verificada.',
    )
  }

  if (auditStatus === 'running' && importedChecklist) {
    return (
      <AuditProgress
        username={username}
        database={connectionFields.database}
        phases={importedChecklist.fases}
        startedAt={auditStartedAt}
        onLogout={onLogout}
        events={progressEvents}
        stage={progressStage}
      />
    )
  }

  if (auditStatus === 'success' && auditResult) {
    return (
      <AuditResults
        username={username}
        database={connectionFields.database}
        result={auditResult}
        onNewAudit={handleNewAudit}
        onLogout={onLogout}
      />
    )
  }

  return (
    <AppShell
      activePage="new-audit"
      username={username}
      onLogout={onLogout}
      serverLabel={connectionStatus === 'success' ? connectionFields.database : undefined}
      serverConnected={connectionStatus === 'success'}
    >
      <main className="px-5 py-8 sm:px-8 lg:px-10 lg:py-9">
        <div className="mx-auto max-w-[1120px]">
          <header>
            <h1 className="text-[30px] leading-tight font-bold tracking-[-0.02em] text-[#263d64] sm:text-[36px]">Nueva auditoría</h1>
            <p className="mt-1 text-sm text-[#687b99]">Importe el checklist y configure la conexión a PostgreSQL.</p>
          </header>

          <div className="mt-8 grid items-start gap-6 lg:grid-cols-[0.85fr_1.15fr]">
            <section aria-labelledby="checklist-title" className="overflow-hidden rounded-lg bg-white shadow-[0_8px_22px_rgba(38,61,100,0.06)]">
              <div className="flex min-h-14 items-center justify-between gap-3 bg-[#edf3ff] px-5">
                <h2 id="checklist-title" className="flex items-center gap-2 text-[18px] font-semibold text-[#263d64]"><ChecklistIcon /> Importar checklist</h2>
                <span className="rounded bg-[#d9e7ff] px-2 py-1 text-[11px] font-medium tracking-[0.05em] text-[#3568ec] uppercase">Requerido</span>
              </div>

              <div className="p-5">
                <p className="text-sm leading-5 text-[#687b99]">Seleccione la plantilla de control institucional en formato Excel (.xlsx).</p>

                <label className="mt-5 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-lg bg-[#edf3ff] px-5 text-center outline-none transition hover:bg-[#e7effc] focus-within:ring-2 focus-within:ring-[#42658f]">
                  <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-white text-[#3568ec]"><UploadIcon /></span>
                  <span className="mt-3 text-[15px] font-semibold text-[#263d64]">Seleccionar archivo .xlsx</span>
                  <span className="mt-1 text-xs text-[#687b99]">Se validará la hoja Checklist Maestro</span>
                  <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={handleFileChange} disabled={importStatus === 'loading'} className="sr-only" />
                </label>

                <div className="mt-4 rounded-lg bg-[#edf3ff] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="min-w-0 truncate text-sm font-semibold text-[#263d64]">{importedChecklist?.nombre_archivo || selectedFileName || 'Sin archivo seleccionado'}</p>
                    <span className={`shrink-0 rounded bg-white px-2 py-1 text-xs ${displayedImportStatus === 'success' ? 'text-[#167052]' : displayedImportStatus === 'error' ? 'text-[#a33b32]' : 'text-[#687b99]'}`}>
                      {displayedImportStatus === 'loading'
                        ? 'Validando…'
                        : displayedImportStatus === 'success'
                          ? 'Validado'
                          : displayedImportStatus === 'error'
                            ? 'Error'
                            : 'Pendiente'}
                    </span>
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-3 rounded-md bg-white p-3">
                    <div>
                      <dt className="text-[11px] tracking-[0.04em] text-[#687b99] uppercase">Fases detectadas</dt>
                      <dd className="mt-1 text-lg font-semibold text-[#263d64]">{importedChecklist?.cantidad_fases ?? '—'}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] tracking-[0.04em] text-[#687b99] uppercase">Actividades</dt>
                      <dd className="mt-1 text-lg font-semibold text-[#263d64]">{importedChecklist?.cantidad_actividades ?? '—'}</dd>
                    </div>
                  </dl>
                  {importedChecklist && <p className="mt-3 text-xs break-words text-[#687b99]">Versión: {importedChecklist.checklist_version ?? 'Histórica'}{importedChecklist.checklist_huella ? ` · Huella ${importedChecklist.checklist_huella.slice(0,12)}` : ''}</p>}
                  <div className="mt-3 min-h-4 text-xs" aria-live="polite" role="status">
                    {displayedImportStatus === 'success' && <p className="text-[#167052]">Checklist importado y estructura validada.</p>}
                    {displayedImportStatus === 'error' && <p className="text-[#a33b32]">{importError}</p>}
                    {displayedImportStatus === 'idle' && <p className="text-[#687b99]">Seleccione un archivo para obtener los conteos reales.</p>}
                  </div>
                </div>
              </div>
            </section>

            <section aria-labelledby="connection-title" className="overflow-hidden rounded-lg bg-white shadow-[0_8px_22px_rgba(38,61,100,0.06)]">
              <div className="flex min-h-14 flex-wrap items-center justify-between gap-2 bg-[#edf3ff] px-5 py-3">
                <h2 id="connection-title" className="flex items-center gap-2 text-[18px] font-semibold text-[#263d64]"><LinkIcon /> Conexión PostgreSQL</h2>
                <span className="text-xs text-[#687b99]">Conexión de solo lectura</span>
              </div>

              <form className="p-5" onSubmit={handleConnectionTest}>
                <div className="grid gap-5 sm:grid-cols-[1fr_140px]">
                  <label className="block text-sm font-medium text-[#263d64]">
                    Host
                    <input name="host" type="text" autoComplete="off" placeholder="ej. db.interna.local" required maxLength={253} value={connectionFields.host} onChange={handleConnectionFieldChange} className={`${inputClass} mt-2`} />
                  </label>
                  <label className="block text-sm font-medium text-[#263d64]">
                    Puerto
                    <input name="port" type="number" min="1" max="65535" inputMode="numeric" autoComplete="off" placeholder="5432" required value={connectionFields.port} onChange={handleConnectionFieldChange} className={`${inputClass} mt-2`} />
                  </label>
                </div>

                <label className="mt-5 block text-sm font-medium text-[#263d64]">
                  Base de datos
                  <input name="database" type="text" autoComplete="off" placeholder="Nombre de la base de datos" required maxLength={63} value={connectionFields.database} onChange={handleConnectionFieldChange} className={`${inputClass} mt-2`} />
                </label>

                <div className="mt-5 grid gap-5 sm:grid-cols-2">
                  <label className="block text-sm font-medium text-[#263d64]">
                    Usuario
                    <input name="username" type="text" autoComplete="off" placeholder="Usuario de solo lectura" required maxLength={63} value={connectionFields.username} onChange={handleConnectionFieldChange} className={`${inputClass} mt-2`} />
                  </label>
                  <label className="block text-sm font-medium text-[#263d64]">
                    Contraseña
                    <span className="relative mt-2 block">
                      <input name="password" type={isPasswordVisible ? 'text' : 'password'} autoComplete="off" required maxLength={1024} value={connectionFields.password} onChange={handleConnectionFieldChange} className={`${inputClass} pr-11`} />
                      <button type="button" aria-label={isPasswordVisible ? 'Ocultar contraseña' : 'Mostrar contraseña'} aria-pressed={isPasswordVisible} onClick={() => setIsPasswordVisible((visible) => !visible)} className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-[8px] text-[#687b99] outline-none hover:text-[#263d64] focus-visible:ring-2 focus-visible:ring-[#42658f] focus-visible:ring-inset">
                        <EyeIcon crossed={isPasswordVisible} />
                      </button>
                    </span>
                  </label>
                </div>

                <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[#edf3ff] p-4">
                  <button type="submit" disabled={connectionStatus === 'testing'} className="h-10 rounded-lg bg-[#172f50] px-5 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60">{connectionStatus === 'testing' ? 'Comprobando…' : 'Probar conexión'}</button>
                  <p aria-live="polite" role="status" className={`max-w-sm text-xs ${connectionStatus === 'success' ? 'text-[#167052]' : connectionStatus === 'error' ? 'text-[#a33b32]' : 'text-[#687b99]'}`}>{connectionMessage}</p>
                </div>

                <div className="mt-8 flex flex-col items-end">
                  <button type="button" disabled={!canStartAudit || auditStatus === 'running'} onClick={handleStartAudit} className="h-11 rounded-lg bg-[#172f50] px-6 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">{auditStatus === 'running' ? 'Ejecutando…' : 'Iniciar auditoría →'}</button>
                  <p aria-live="polite" role="status" className={`mt-2 max-w-xl text-right text-xs ${auditStatus === 'success' ? 'text-[#167052]' : auditStatus === 'error' ? 'text-[#a33b32]' : 'text-[#687b99]'}`}>{auditMessage}</p>
                </div>
              </form>
            </section>
          </div>
        </div>
      </main>
      {elevatedPrivileges !== null && <ElevatedPrivilegesDialog privileges={elevatedPrivileges} continuationAllowed={continuationAllowed}
        onChangeUser={() => {
          setElevatedPrivileges(null)
          setElevatedConfirmed(false)
          setConnectionStatus('idle')
          setConnectionMessage('Introduzca una cuenta de lectura y vuelva a probar la conexión.')
          requestAnimationFrame(() => document.querySelector<HTMLInputElement>('input[name="username"]')?.focus())
        }}
        onContinue={() => { setElevatedPrivileges(null); void checkConnection(true) }} />}
    </AppShell>
  )
}

export default NewAudit
