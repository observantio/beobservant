import { useEffect, useState } from 'react'
import { fetchHealth, getAlerts, searchTraces, getLogVolume } from '../api'
import { Card, Badge, MetricCard, Spinner } from './ui'
import PropTypes from 'prop-types'

export default function Dashboard({ info }) {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [alertCount, setAlertCount] = useState(null)
  const [loadingAlerts, setLoadingAlerts] = useState(true)
  const [traceCount, setTraceCount] = useState(null)
  const [traceErrorCount, setTraceErrorCount] = useState(null)
  const [loadingTraces, setLoadingTraces] = useState(true)
  const [logVolume, setLogVolume] = useState(null)
  const [loadingLogs, setLoadingLogs] = useState(true)

  useEffect(() => {
    // Health
    ;(async () => {
      try {
        const res = await fetchHealth()
        setHealth(res)
      } catch (e) {
        setHealth(null)
      } finally {
        if (typeof setLoading === 'function') setLoading(false)
      }
    })()

    // Alerts
    ;(async () => {
      try {
        if (typeof setLoadingAlerts === 'function') setLoadingAlerts(true)
        const data = await getAlerts()
        setAlertCount(Array.isArray(data) ? data.length : 0)
      } catch (e) {
        setAlertCount(0)
      } finally {
        if (typeof setLoadingAlerts === 'function') setLoadingAlerts(false)
      }
    })()

    // Fetch recent traces (last 1 hour) and count errors
    ;(async () => {
      try {
        // Tempo expects microseconds for start/end
        const endUs = Date.now() * 1000 // ms -> µs
        const startUs = endUs - (60 * 60 * 1000000) // last 1 hour in µs
        const res = await searchTraces({ start: Math.floor(startUs), end: Math.floor(endUs), limit: 1000 })
        const traces = res?.data || []
        setTraceCount(traces.length)
        const errors = traces.filter(t => (t.spans || []).some(s => s.status?.code === 'ERROR' || s.tags?.some(tag => tag.key === 'error' && tag.value === true))).length
        setTraceErrorCount(errors)
      } catch (e) {
        setTraceCount(0)
        setTraceErrorCount(0)
      } finally {
        if (typeof setLoadingTraces === 'function') setLoadingTraces(false)
      }
    })()

    // Fetch log volume for last 1 hour (use catch-all Loki query)
    ;(async () => {
      try {
        // use nanoseconds for Loki API and request 1h window with 60s step
        const endNs = Date.now() * 1000000 // ms -> ns
        const startNs = endNs - (60 * 60 * 1000000000) // last 1 hour in ns
        const vol = await getLogVolume('{service_name=~".+"}', { start: Math.floor(startNs), end: Math.floor(endNs), step: 60 })
        // vol.data may contain series; try to sum values
        let total = 0
        try {
          if (vol && vol.data && Array.isArray(vol.data.result)) {
            vol.data.result.forEach(series => {
              if (Array.isArray(series.values)) {
                series.values.forEach(v => {
                  const val = Number(v[1])
                  if (!Number.isNaN(val)) total += val
                })
              }
            })
          }
        } catch (ex) {
          total = null
        }
        setLogVolume(total)
      } catch (e) {
        setLogVolume(null)
      } finally {
        if (typeof setLoadingLogs === 'function') setLoadingLogs(false)
      }
    })()
  }, [])

  const statusBadge = (status) => {
    if (!status) return <Badge variant="warning">unknown</Badge>
    if (status === 'Healthy') return <Badge variant="success">Healthy</Badge>
    return <Badge variant="error">{status}</Badge>
  }

  const services = [
    {
      name: 'Tempo',
      description: 'Distributed Tracing',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      status: 'operational',
    },
    {
      name: 'Loki',
      description: 'Log Aggregation',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
      status: 'operational',
    },
    {
      name: 'AlertManager',
      description: 'Alert Management',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
      ),
      status: 'operational',
    },
    {
      name: 'Grafana',
      description: 'Visualization & Dashboards',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
      status: 'operational',
    },
  ]

  const getStatusValue = () => {
    if (loading) return <Spinner size="sm" />
    return health?.status ? health?.status.charAt(0).toUpperCase() + health?.status.slice(1) : 'Unknown'
  }

  const getAlertValue = () => {
    if (loadingAlerts) return <Spinner size="sm" />
    if (alertCount === null) return '0'
    return String(alertCount)
  }

  return (
    <div className="animate-fade-in">
      {/* Hero Section */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-sre-text mb-2">
          Observability Dashboard
        </h1>
        <p className="text-sre-text-muted">
          Monitor and manage your observability infrastructure in real-time
        </p>
      </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <MetricCard
            label="Service Status"
            value={getStatusValue()}
            trend={health?.status === 'Healthy' ? 'All systems operational' : 'Issues detected'}
            status={health?.status === 'Healthy' ? 'success' : 'warning'}
            icon={
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            }
          />
          <MetricCard
            label="Active Alerts"
            value={getAlertValue()}
            trend={alertCount > 0 ? `${alertCount} active` : 'No active alerts'}
            status={alertCount > 0 ? 'warning' : 'success'}
            icon={
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
              </svg>
            }
          />
          <MetricCard
            label="Traces (last 1h)"
            value={loadingTraces ? <Spinner size="sm" /> : (traceCount !== null ? String(traceCount) : 'N/A')}
            trend={traceErrorCount > 0 ? `${traceErrorCount} with errors` : (traceCount > 0 ? 'No errors' : 'No traces')}
            status={traceErrorCount > 0 ? 'warning' : (traceCount > 0 ? 'success' : 'default')}
            icon={
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3v18h18" />
              </svg>
            }
          />
          <MetricCard
            label="Logs (last 1h)"
            value={loadingLogs ? <Spinner size="sm" /> : (logVolume !== null ? String(logVolume) : 'N/A')}
            trend={logVolume > 0 ? 'Log volume detected' : 'No logs'}
            status={logVolume > 0 ? 'success' : 'default'}
            icon={
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12h18M3 6h18M3 18h18" />
              </svg>
            }
          />
          <MetricCard
            label="Active Services"
            value={String(services.length)}
            trend={services.length ? `${services.length} connected` : 'No services connected'}
            status="success"
            icon={
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
            </svg>
            }
          />
        </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Connected Services */}
        <Card
          title="Connected Services"
          subtitle="Observability stack components"
          className="lg:col-span-2"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {services.map((service) => (
              <div
                key={service.name}
                className="flex items-start gap-3 p-4 bg-sre-bg-alt rounded-lg border border-sre-border hover:border-sre-primary/50 transition-all duration-200"
              >
                <div className="flex-shrink-0 w-10 h-10 bg-sre-primary/10 rounded-lg flex items-center justify-center text-sre-primary">
                  {service.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sre-text">{service.name}</div>
                  <div className="text-sm text-sre-text-muted mt-0.5">
                    {service.description}
                  </div>
                  <div className="mt-2">
                    <Badge variant="success" className="text-xs">
                      {service.status}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}

Dashboard.propTypes = {
  info: PropTypes.shape({
    service: PropTypes.string,
    version: PropTypes.string,
  }),
}
