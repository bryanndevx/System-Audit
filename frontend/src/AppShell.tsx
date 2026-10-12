import type { ReactNode } from 'react'

type AppShellProps = {
  activePage: 'dashboard' | 'new-audit'
  children: ReactNode
}

function HomeIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
      <path d="m3 11 9-8 9 8v9H7v-7h10v7" />
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

function UserIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
      <circle cx="12" cy="8" r="3" />
      <path d="M5 20v-2c0-3 3.1-5 7-5s7 2 7 5v2H5Z" />
    </svg>
  )
}

const navigationClass = (isActive: boolean) =>
  `flex h-12 items-center gap-4 rounded-md px-4 text-[16px] font-medium ${
    isActive ? 'bg-[#f4f7fb] text-[#263d64]' : 'text-white/90'
  }`

function AppShell({ activePage, children }: AppShellProps) {
  const mobilePageLabel = activePage === 'dashboard' ? 'Dashboard' : 'Nueva auditoría'

  return (
    <div className="min-h-dvh bg-[#f4f7fb] font-sans text-[#263d64]">
      <aside className="fixed inset-y-0 left-0 z-10 hidden w-60 flex-col bg-[#172f50] text-white md:flex">
        <div className="px-8 py-7 text-[22px] font-semibold">Auditoría BD</div>

        <nav aria-label="Navegación principal" className="mt-10 space-y-2 px-4">
          <a
            href="/dashboard"
            aria-current={activePage === 'dashboard' ? 'page' : undefined}
            className={navigationClass(activePage === 'dashboard')}
          >
            <HomeIcon />
            Dashboard
          </a>
          <a
            href="/nueva-auditoria"
            aria-current={activePage === 'new-audit' ? 'page' : undefined}
            className={navigationClass(activePage === 'new-audit')}
          >
            <PlusIcon />
            Nueva auditoría
          </a>
        </nav>

        <div className="mt-auto px-8 pb-8 text-[#8495ad]">
          <button
            type="button"
            disabled
            title="No existe una sesión real"
            className="cursor-not-allowed text-[15px]"
          >
            Cerrar sesión
          </button>
          <p className="mt-7 text-xs">Interfaz demostrativa</p>
        </div>
      </aside>

      <div className="md:pl-60">
        <header className="border-b border-[#edf1f7] bg-white">
          <div className="flex min-h-[72px] items-center justify-between gap-4 px-5 sm:px-8 lg:px-10">
            <div className="flex min-w-0 items-center gap-3">
              <span className="hidden text-xs tracking-[0.08em] text-[#687b99] uppercase sm:inline">
                Servidor de auditoría
              </span>
              <span className="rounded bg-[#eef3fb] px-2 py-1 text-xs font-medium text-[#536984]">
                No conectado
              </span>
            </div>

            <div className="flex items-center gap-3 text-right">
              <div className="hidden sm:block">
                <p className="text-sm font-medium text-[#263d64]">Usuario de demostración</p>
                <p className="text-xs text-[#687b99]">Sin sesión real</p>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#314a70] text-white">
                <UserIcon />
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between bg-[#172f50] px-5 py-3 text-white md:hidden">
            <span className="font-semibold">Auditoría BD</span>
            <span className="flex items-center gap-2 text-sm">
              {activePage === 'dashboard' ? <HomeIcon /> : <PlusIcon />}
              {mobilePageLabel}
            </span>
          </div>
        </header>

        {children}
      </div>
    </div>
  )
}

export default AppShell
