/** Bound session lookup as well as the network operation that follows it. */
export async function withTimeout<T>(
  operation: (signal: AbortSignal) => PromiseLike<T>,
  timeoutMs = 15000,
  message = 'This request timed out. Check your connection and try again.',
): Promise<T> {
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new Error(message))
      controller.abort()
    }, timeoutMs)
  })
  try {
    return await Promise.race([Promise.resolve().then(() => operation(controller.signal)), deadline])
  } finally {
    clearTimeout(timer)
  }
}

/** Supabase accepts a custom fetch for bounded Auth and database calls. */
export const boundedFetch: typeof fetch = (input, init) => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  // A permitted 5 MB upload can take longer than an Auth lookup on a slow link.
  const timeoutMs = new URL(url).pathname.startsWith('/storage/v1/') ? 120000 : 15000
  return withTimeout(signal => fetch(input, {
    ...init,
    signal: init?.signal ? AbortSignal.any([init.signal, signal]) : signal,
  }), timeoutMs)
}
