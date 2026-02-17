import { describe, expect, it } from 'vitest'
import {
  isValidDuration,
  isValidEmail,
  isValidURL,
  validateLogQL,
  validatePromQL,
  validateRange,
  validateRequired,
} from '../validators'

describe('validators', () => {
  it('validates emails and urls', () => {
    expect(isValidEmail('a@b.com')).toBe(true)
    expect(isValidEmail('not-an-email')).toBe(false)
    expect(isValidURL('https://example.com')).toBe(true)
    expect(isValidURL('notaurl')).toBe(false)
  })

  it('validates LogQL and PromQL basics', () => {
    expect(validateLogQL('{service="api"}').valid).toBe(true)
    expect(validateLogQL('service="api"').valid).toBe(false)
    expect(validatePromQL('rate(http_requests_total[5m])').valid).toBe(true)
    expect(validatePromQL('a < b').valid).toBe(false)
  })

  it('validates required/range/duration', () => {
    expect(validateRequired('').valid).toBe(false)
    expect(validateRequired('x').valid).toBe(true)
    expect(validateRange('10', 1, 20).valid).toBe(true)
    expect(validateRange('x', 1, 20).valid).toBe(false)
    expect(isValidDuration('5m')).toBe(true)
    expect(isValidDuration('5min')).toBe(false)
  })
})
