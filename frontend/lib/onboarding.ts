import type { UserRole } from '@/types/database'

type RoleResult = { data: unknown; error: { message: string; code?: string } | null }

/** Bound the entire operation, including session lookup before the HTTP request. */
export async function completeOnboarding(
  request: (signal: AbortSignal) => PromiseLike<RoleResult>,
  timeoutMs = 15000,
): Promise<UserRole> {
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new Error('Account setup took too long. Check your connection and try again. If it already saved, refresh this page to continue.'))
      controller.abort()
    }, timeoutMs)
  })

  try {
    const { data, error } = await Promise.race([
      Promise.resolve().then(() => request(controller.signal)),
      deadline,
    ])
    if (error) {
      console.error('[onboarding] Role save failed:', error.message, error.code)
      if (error.code === 'PGRST202' || error.code === '42501') {
        throw new Error('Account setup is not configured on this site. Contact the site administrator.')
      }
      throw new Error(error.message || 'Your account could not be saved. Please try again.')
    }
    if (data !== 'student' && data !== 'faculty' && data !== 'admin') {
      throw new Error('Your role did not save. Please try again, or contact support if it keeps happening.')
    }
    return data
  } finally {
    clearTimeout(timer)
  }
}
