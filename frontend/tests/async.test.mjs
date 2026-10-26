import assert from 'node:assert/strict'
import { test } from 'node:test'
import { withTimeout } from '../lib/async.ts'

test('bounds an operation that never settles, even when it ignores the abort signal', async () => {
  let signal
  await assert.rejects(withTimeout(value => {
    signal = value
    return new Promise(() => {})
  }, 10), /timed out/)
  assert.equal(signal.aborted, true)
})

test('preserves synchronous failures and cleans up the deadline', async () => {
  const failure = new Error('Session lookup failed')
  let signal
  await assert.rejects(withTimeout(value => {
    signal = value
    throw failure
  }, 10), error => error === failure)
  await new Promise(resolve => setTimeout(resolve, 20))
  assert.equal(signal.aborted, false)
})
