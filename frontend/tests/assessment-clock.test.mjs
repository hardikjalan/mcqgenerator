import assert from 'node:assert/strict'
import { test } from 'node:test'
import { serverClockOffset, remainingSeconds } from '../lib/assessment-clock.ts'

const start = Date.parse('2026-10-26T12:00:00Z')
const expiry = new Date(start + 300000).toISOString()

test('leaving and reopening the quiz view does not reset the countdown', () => {
  const offset = serverClockOffset(new Date(start).toISOString(), start)
  assert.equal(remainingSeconds(expiry, start, offset), 300)
  assert.equal(remainingSeconds(expiry, start + 45000, offset), 255)
})

test('countdown compensates for a client clock that is two minutes ahead', () => {
  const offset = serverClockOffset(new Date(start).toISOString(), start + 120000)
  assert.equal(remainingSeconds(expiry, start + 150000, offset), 270)
})

test('expired and untimed assessments have distinct timer states', () => {
  assert.equal(remainingSeconds(expiry, start + 310000, 0), 0)
  assert.equal(remainingSeconds(null, start, 0), null)
})
