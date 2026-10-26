import assert from 'node:assert/strict'
import { test } from 'node:test'
import { completeOnboarding } from '../lib/onboarding.ts'

test('returns the database role, including a role assigned earlier', async () => {
  assert.equal(await completeOnboarding(() => Promise.resolve({ data: 'faculty', error: null })), 'faculty')
})

test('times out even when session lookup never reaches the network', async () => {
  let signal
  await assert.rejects(completeOnboarding(value => {
    signal = value
    return new Promise(() => {})
  }, 10), /Account setup took too long/)
  assert.equal(signal.aborted, true)
})

test('surfaces PostgREST errors that are plain objects rather than Error instances', async () => {
  await assert.rejects(completeOnboarding(() => Promise.resolve({
    data: null, error: { message: 'Session expired', code: 'PGRST301' },
  })), /Session expired/)
})

test('rejects empty or unexpected roles before constructing a dashboard URL', async () => {
  for (const data of [null, undefined, '', 'javascript:alert(1)']) {
    await assert.rejects(completeOnboarding(() => Promise.resolve({ data, error: null })), /role did not save/)
  }
})

test('successful requests cancel their deadline without aborting the completed operation', async () => {
  let signal
  await completeOnboarding(value => {
    signal = value
    return Promise.resolve({ data: 'student', error: null })
  }, 10)
  await new Promise(resolve => setTimeout(resolve, 20))
  assert.equal(signal.aborted, false)
})
