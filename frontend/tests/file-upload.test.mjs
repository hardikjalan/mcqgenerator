import assert from 'node:assert/strict'
import { test } from 'node:test'
import { validateFile, validateFileAddition, MAX_CUMULATIVE_SIZE, MAX_FILE_COUNT } from '../lib/file-upload.ts'

const pdf = new File(['A course document'], 'notes.pdf', { type: 'application/pdf' })

test('empty documents fail before upload', () => {
  assert.match(validateFile(new File([], 'empty.pdf', { type: 'application/pdf' })), /empty/)
})

test('unsupported files fail before upload', () => {
  assert.match(validateFile(new File(['text'], 'notes.exe', { type: 'application/octet-stream' })), /Unsupported/)
})

test('the eleventh file is rejected even when it fits the byte budget', () => {
  assert.equal(validateFileAddition(pdf, 100, MAX_FILE_COUNT - 1), null)
  assert.match(validateFileAddition(pdf, 100, MAX_FILE_COUNT), /10 files/)
})

test('combined upload size is checked independently of individual file size', () => {
  assert.equal(validateFileAddition(pdf, MAX_CUMULATIVE_SIZE - pdf.size, 1), null)
  assert.match(validateFileAddition(pdf, MAX_CUMULATIVE_SIZE - pdf.size + 1, 1), /combined 5 MB/)
})
