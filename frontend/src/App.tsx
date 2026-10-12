import { useState } from 'react'
import type { FormEvent } from 'react'
import Dashboard from './Dashboard'
import NewAudit from './NewAudit'

function App() {
  const [isPasswordVisible, setIsPasswordVisible] = useState(false)
  const [notice, setNotice] = useState('')
  const developmentPath = import.meta.env.DEV ? window.location.pathname : ''

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setNotice('La autenticación todavía no está conectada.')
  }

  if (developmentPath === '/dashboard') {
    return <Dashboard />
  }

  if (developmentPath === '/nueva-auditoria') {
    return <NewAudit />
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-[#f4f7fb] px-4 py-4 font-sans text-[#263d64] sm:px-6">
      <section
        aria-labelledby="login-title"
        className="w-full max-w-[420px] rounded-[16px] bg-white px-5 py-7 shadow-[0_12px_32px_rgba(38,61,100,0.08)] sm:px-10 sm:py-10"
      >
        <header className="text-center">
          <h1
            id="login-title"
            className="text-[26px] leading-tight font-bold tracking-[-0.02em] text-[#263d64]"
          >
            Auditoría BD
          </h1>
          <p className="mx-auto mt-2 max-w-[340px] text-[14px] leading-5 text-[#687b99]">
            Sistema inteligente para auditorías técnicas de bases de datos
          </p>
        </header>

        <form className="mt-8" onSubmit={handleSubmit}>
          <div>
            <label
              className="mb-1.5 block text-[15px] font-medium text-[#263d64]"
              htmlFor="username"
            >
              Usuario
            </label>
            <input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              placeholder="ej. auditor_academico"
              className="h-11 w-full rounded-[10px] border border-[#d6dfec] bg-white px-4 text-[15px] text-[#263d64] outline-none transition placeholder:text-[#687b99] focus:border-[#42658f] focus:ring-2 focus:ring-[#42658f]/20"
            />
          </div>

          <div className="mt-5">
            <label
              className="mb-1.5 block text-[15px] font-medium text-[#263d64]"
              htmlFor="password"
            >
              Contraseña
            </label>
            <div className="relative">
              <input
                id="password"
                name="password"
                type={isPasswordVisible ? 'text' : 'password'}
                autoComplete="current-password"
                className="h-11 w-full rounded-[10px] border border-[#d6dfec] bg-white px-4 pr-11 text-[15px] text-[#263d64] outline-none transition focus:border-[#42658f] focus:ring-2 focus:ring-[#42658f]/20"
              />
              <button
                type="button"
                aria-label={isPasswordVisible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                aria-pressed={isPasswordVisible}
                onClick={() => setIsPasswordVisible((visible) => !visible)}
                className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-[10px] text-[#687b99] outline-none hover:text-[#263d64] focus-visible:ring-2 focus-visible:ring-[#42658f] focus-visible:ring-inset"
              >
                {isPasswordVisible ? (
                  <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
                    <path d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 4.2A10.4 10.4 0 0 1 12 4c5.5 0 9 5 9 5a15.8 15.8 0 0 1-2.1 2.6M6.6 6.6C4.4 8 3 10 3 10s3.5 5 9 5c1.2 0 2.3-.2 3.3-.6" />
                  </svg>
                ) : (
                  <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-2">
                    <path d="M2.5 12s3.5-5.5 9.5-5.5 9.5 5.5 9.5 5.5-3.5 5.5-9.5 5.5S2.5 12 2.5 12Z" />
                    <circle cx="12" cy="12" r="2.5" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="mt-7 h-11 w-full rounded-[10px] bg-[#294469] text-[15px] font-semibold text-white outline-none transition hover:bg-[#203957] focus-visible:ring-2 focus-visible:ring-[#294469] focus-visible:ring-offset-2 active:bg-[#192f4b]"
          >
            Iniciar sesión
          </button>

          <div className="mt-3 min-h-5 text-center" aria-live="polite" role="status">
            {notice && <p className="text-xs text-[#687b99]">{notice}</p>}
          </div>
        </form>

        <p className="mt-3 text-center text-[13px] font-semibold text-[#687b99]">
          Al autenticarse accederá al Dashboard
        </p>
      </section>
    </main>
  )
}

export default App
