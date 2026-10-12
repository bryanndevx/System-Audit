export type AuthenticatedUser = {
  id: number
  username: string
}

export type AuthState = {
  user: AuthenticatedUser
  csrf_token: string
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function readError(response: Response, fallback: string) {
  const body = (await response.json().catch(() => null)) as
    | { detail?: string }
    | null
  return body?.detail ?? fallback
}

export async function login(
  username: string,
  password: string,
): Promise<AuthState> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })

  if (!response.ok) {
    throw new ApiError(
      response.status,
      await readError(response, 'No fue posible iniciar sesión.'),
    )
  }
  return (await response.json()) as AuthState
}

export async function restoreSession(): Promise<AuthState | null> {
  const response = await fetch('/api/auth/me', {
    credentials: 'same-origin',
    cache: 'no-store',
  })
  if (response.status === 401) {
    return null
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      await readError(response, 'No fue posible comprobar la sesión.'),
    )
  }
  return (await response.json()) as AuthState
}

export async function logout(csrfToken: string): Promise<void> {
  const response = await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  if (!response.ok && response.status !== 401) {
    throw new ApiError(
      response.status,
      await readError(response, 'No fue posible cerrar la sesión.'),
    )
  }
}
