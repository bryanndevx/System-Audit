import AppShell from './AppShell'

type DemoAudit = {
  database: string
  date: string
  automation: string
  duration: string
}

const DEMO_AUDITS: DemoAudit[] = [
  { database: 'demo_academica', date: '24/10/2024 16:30', automation: '78%', duration: '2 min 14 s' },
  { database: 'demo_ventas', date: '22/10/2024 10:15', automation: '82%', duration: '1 min 58 s' },
  { database: 'demo_estudiantes', date: '18/10/2024 14:02', automation: '65%', duration: '3 min 10 s' },
]

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
}

function Dashboard({ username, onLogout }: DashboardProps) {
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
                <span className="mt-2 inline-block rounded bg-[#eaf0fb] px-2.5 py-1 text-xs font-medium text-[#536984]">Datos demostrativos</span>
              </div>
              <p className="text-sm text-[#687b99]">3 registros de ejemplo</p>
            </div>

            <div className="overflow-hidden rounded-xl bg-white shadow-[0_8px_22px_rgba(38,61,100,0.06)]">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse text-left">
                  <thead className="bg-[#294469] text-white">
                    <tr className="text-xs tracking-[0.05em] uppercase">
                      <th scope="col" className="px-5 py-4 font-medium">Base de datos</th>
                      <th scope="col" className="px-5 py-4 font-medium">Fecha</th>
                      <th scope="col" className="px-5 py-4 text-center font-medium">Automatización</th>
                      <th scope="col" className="px-5 py-4 text-center font-medium">Tiempo</th>
                      <th scope="col" className="px-5 py-4 text-center font-medium">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {DEMO_AUDITS.map((audit, index) => (
                      <tr key={audit.database} className={`border-b border-[#e5ebf4] last:border-b-0 ${index % 2 === 1 ? 'bg-[#f8faff]' : 'bg-white'}`}>
                        <td className="px-5 py-5">
                          <span className="flex items-center gap-3 text-[15px] font-medium text-[#263d64]">
                            <span className="text-[#3568ec]"><DatabaseIcon /></span>
                            {audit.database}
                          </span>
                        </td>
                        <td className="px-5 py-5 text-sm text-[#687b99]">{audit.date}</td>
                        <td className="px-5 py-5 text-center text-sm font-medium text-[#263d64]">{audit.automation}</td>
                        <td className="px-5 py-5 text-center text-sm text-[#687b99]">{audit.duration}</td>
                        <td className="px-5 py-5 text-center">
                          <button type="button" disabled title="El detalle de auditoría todavía no está disponible" className="cursor-not-allowed rounded bg-[#eef3fb] px-4 py-1.5 text-sm text-[#263d64] opacity-70">Ver</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="mt-3 text-xs text-[#687b99]">Esta información pertenece únicamente a la maqueta visual y no proviene del backend.</p>
          </section>
        </div>
      </main>
    </AppShell>
  )
}

export default Dashboard
