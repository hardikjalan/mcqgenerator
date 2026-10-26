import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { test } from 'node:test'

function run(script, overrides = {}) {
  return spawnSync(process.execPath, ['--experimental-strip-types', '--input-type=module', '-e', script], {
    cwd: new URL('..', import.meta.url), encoding: 'utf8',
    env: { ...process.env, NEXT_PUBLIC_SUPABASE_URL: ' https://test.supabase.co/rest/v1/ ',
      NEXT_PUBLIC_SUPABASE_ANON_KEY: '', NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: ' publishable-test ',
      NEXT_PUBLIC_API_URL: '', ...overrides },
  })
}

test('blank legacy keys fall back to the publishable key and surrounding spaces are removed', () => {
  const result = run("import assert from 'node:assert/strict'; import { SUPABASE_URL, SUPABASE_ANON_KEY } from './lib/env.ts'; assert.equal(SUPABASE_URL, 'https://test.supabase.co'); assert.equal(SUPABASE_ANON_KEY, 'publishable-test')")
  assert.equal(result.status, 0, result.stderr)
})

test('missing public credentials produce an explicit setup error', () => {
  const result = run("import './lib/env.ts'", { NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: '' })
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /Missing NEXT_PUBLIC_SUPABASE_ANON_KEY/)
})

test('production never silently sends API requests to localhost', () => {
  const result = run("import assert from 'node:assert/strict'; import { apiUrl } from './lib/env.ts'; assert.throws(() => apiUrl('/assessments'), /NEXT_PUBLIC_API_URL is not set/)", { NODE_ENV: 'production' })
  assert.equal(result.status, 0, result.stderr)
})
