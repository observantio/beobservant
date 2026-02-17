import { describe, expect, it } from 'vitest'
import { normalizeGrafanaPath, buildGrafanaLaunchUrl } from '../grafanaLaunchUtils'

describe('grafana launch utilities', () => {
  it('normalizes absolute grafana URLs into a safe path', () => {
    const path = normalizeGrafanaPath('https://example.com/grafana/d/abc123?orgId=1')
    expect(path).toBe('/d/abc123?orgId=1')
  })

  it('keeps default fallback path for invalid input', () => {
    const path = normalizeGrafanaPath('')
    expect(path).toBe('/dashboards')
  })

  it('builds proxy launch URL without exposing tokens', () => {
    const url = buildGrafanaLaunchUrl({
      path: '/grafana/d/xyz?var-service=api',
      protocol: 'http:',
      hostname: 'localhost',
    })
    expect(url).toBe('http://localhost:8080/d/xyz?var-service=api')
    expect(url).not.toContain('token=')
  })
})
