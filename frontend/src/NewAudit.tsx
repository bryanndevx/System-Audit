import { useState } from 'react'
import type { ChangeEvent } from 'react'
import AppShell from './AppShell'

type ImportedActivity = {
  numero: string
  actividad: string
  entregable_esperado: string | null
  prioridad: string | null
}

type ImportedPhase = {
  nombre: string
  actividades: ImportedActivity[]
}

type ChecklistImportResponse = {
  nombre_archivo: string
  cantidad_fases: number
  cantidad_actividades: number
  fases: ImportedPhase[]
}

type ImportStatus = 'idle' | 'loading' | 'success' | 'error'

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

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    setSelectedFileName(file?.name ?? '')
    setImportedChecklist(null)
    setImportError('')

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

  return (
    <AppShell activePage="new-audit" username={username} onLogout={onLogout}>
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
                    <span className={`shrink-0 rounded bg-white px-2 py-1 text-xs ${importStatus === 'success' ? 'text-[#167052]' : importStatus === 'error' ? 'text-[#a33b32]' : 'text-[#687b99]'}`}>
                      {importStatus === 'loading'
                        ? 'Validando…'
                        : importStatus === 'success'
                          ? 'Validado'
                          : importStatus === 'error'
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
                  <div className="mt-3 min-h-4 text-xs" aria-live="polite" role="status">
                    {importStatus === 'success' && <p className="text-[#167052]">Checklist importado y estructura validada.</p>}
                    {importStatus === 'error' && <p className="text-[#a33b32]">{importError}</p>}
                    {importStatus === 'idle' && <p className="text-[#687b99]">Seleccione un archivo para obtener los conteos reales.</p>}
                  </div>
                </div>
              </div>
            </section>

            <section aria-labelledby="connection-title" className="overflow-hidden rounded-lg bg-white shadow-[0_8px_22px_rgba(38,61,100,0.06)]">
              <div className="flex min-h-14 flex-wrap items-center justify-between gap-2 bg-[#edf3ff] px-5 py-3">
                <h2 id="connection-title" className="flex items-center gap-2 text-[18px] font-semibold text-[#263d64]"><LinkIcon /> Conexión PostgreSQL</h2>
                <span className="text-xs text-[#687b99]">Conexión de solo lectura</span>
              </div>

              <form className="p-5" onSubmit={(event) => event.preventDefault()}>
                <div className="grid gap-5 sm:grid-cols-[1fr_140px]">
                  <label className="block text-sm font-medium text-[#263d64]">
                    Host
                    <input name="host" type="text" autoComplete="off" placeholder="ej. db.interna.local" className={`${inputClass} mt-2`} />
                  </label>
                  <label className="block text-sm font-medium text-[#263d64]">
                    Puerto
                    <input name="port" type="text" inputMode="numeric" autoComplete="off" placeholder="5432" className={`${inputClass} mt-2`} />
                  </label>
                </div>

                <label className="mt-5 block text-sm font-medium text-[#263d64]">
                  Base de datos
                  <input name="database" type="text" autoComplete="off" placeholder="Nombre de la base de datos" className={`${inputClass} mt-2`} />
                </label>

                <div className="mt-5 grid gap-5 sm:grid-cols-2">
                  <label className="block text-sm font-medium text-[#263d64]">
                    Usuario
                    <input name="database-user" type="text" autoComplete="off" placeholder="Usuario de solo lectura" className={`${inputClass} mt-2`} />
                  </label>
                  <label className="block text-sm font-medium text-[#263d64]">
                    Contraseña
                    <span className="relative mt-2 block">
                      <input name="database-password" type={isPasswordVisible ? 'text' : 'password'} autoComplete="new-password" className={`${inputClass} pr-11`} />
                      <button type="button" aria-label={isPasswordVisible ? 'Ocultar contraseña' : 'Mostrar contraseña'} aria-pressed={isPasswordVisible} onClick={() => setIsPasswordVisible((visible) => !visible)} className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-[8px] text-[#687b99] outline-none hover:text-[#263d64] focus-visible:ring-2 focus-visible:ring-[#42658f] focus-visible:ring-inset">
                        <EyeIcon crossed={isPasswordVisible} />
                      </button>
                    </span>
                  </label>
                </div>

                <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[#edf3ff] p-4">
                  <button type="button" disabled title="La conexión PostgreSQL todavía no está implementada" className="h-10 cursor-not-allowed rounded-lg bg-[#172f50] px-5 text-sm font-semibold text-white opacity-60">Probar conexión</button>
                  <p className="text-xs text-[#687b99]">Pendiente de integración con el backend</p>
                </div>

                <div className="mt-8 flex flex-col items-end">
                  <button type="submit" disabled title="Requiere un checklist válido y una conexión verificada" className="h-11 cursor-not-allowed rounded-lg bg-[#172f50] px-6 text-sm font-semibold text-white opacity-50">Iniciar auditoría →</button>
                  <p className="mt-2 text-right text-xs text-[#687b99]">Se habilitará con checklist válido y conexión verificada.</p>
                </div>
              </form>
            </section>
          </div>
        </div>
      </main>
    </AppShell>
  )
}

export default NewAudit
