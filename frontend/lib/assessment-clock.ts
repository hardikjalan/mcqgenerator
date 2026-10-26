/** Capture the offset when a server response arrives, not when a view remounts. */
export function serverClockOffset(serverTime: string, receivedAt: number): number {
  return new Date(serverTime).getTime() - receivedAt
}

export function remainingSeconds(expiresAt: string | null, clientNow: number, offset: number): number | null {
  return expiresAt ? Math.max(0, Math.ceil((new Date(expiresAt).getTime() - clientNow - offset) / 1000)) : null
}
