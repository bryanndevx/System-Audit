import { useEffect, useRef } from 'react'

export default function ElevatedPrivilegesDialog({ privileges, onChangeUser, onContinue, continuationAllowed = true }: {
  privileges: string[]
  onChangeUser: () => void
  onContinue: () => void
  continuationAllowed?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    const focus = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => {
      dialog?.close()
      document.body.style.overflow = overflow
      if (focus instanceof HTMLElement && focus.isConnected) focus.focus()
    }
  }, [])

  return <dialog ref={ref} aria-labelledby="elevated-title" aria-describedby="elevated-description" onCancel={(event) => { event.preventDefault(); onChangeUser() }}
    className="m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-lg overflow-auto rounded-2xl border border-[#dce5f2] bg-white p-6 text-[#263d64] shadow-xl backdrop:bg-[#102541]/60">
    <h2 id="elevated-title" className="text-xl font-semibold">Este usuario tiene privilegios elevados</h2>
    <p id="elevated-description" className="mt-3 text-sm leading-6 text-[#536984]">{continuationAllowed ? 'Recomendamos cambiar a una cuenta de solo lectura. Si continúa, el sistema mantendrá las consultas en transacciones de lectura, pero la cuenta conservará sus privilegios administrativos.' : 'La auditoría requiere una cuenta de lectura. No se permite continuar con una cuenta superusuario.'}</p>
    <ul className="mt-4 list-inside list-disc rounded-lg bg-[#fff7e6] p-4 text-sm leading-6 text-[#886326]">
      {privileges.map((privilege) => <li key={privilege}>{privilege}</li>)}
    </ul>
    {continuationAllowed && <p className="mt-4 text-sm leading-6 text-[#536984]">Continuar confirma que conoce esta condición y está autorizado para auditar con esa cuenta. No se habilitarán consultas de escritura.</p>}
    <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-end">
      <button autoFocus type="button" onClick={onChangeUser} className="rounded-lg border border-[#d6dfec] px-4 py-2.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2">Cambiar usuario</button>
      {continuationAllowed && <button type="button" onClick={onContinue} className="rounded-lg bg-[#172f50] px-4 py-2.5 text-sm font-medium text-white focus-visible:outline-2 focus-visible:outline-offset-2">Entiendo, continuar en lectura</button>}
    </div>
  </dialog>
}
