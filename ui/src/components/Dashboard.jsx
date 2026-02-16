import { useState } from 'react'
import PropTypes from 'prop-types'
import { useDashboardData, useAgentActivity } from '../hooks'
import { getMetricsConfig } from '../constants/dashboard.jsx'
import { MetricsGrid, DashboardLayout } from './dashboard'

export default function Dashboard({ info }) {
  const dashboardData = useDashboardData()
  const agentData = useAgentActivity()

  const [metricOrder, setMetricOrder] = useState(() => {
    const saved = localStorage.getItem('dashboard-metric-order')
    if (saved) {
      const parsed = JSON.parse(saved)
      if (parsed.length < 8) {
        const missingIndices = []
        for (let i = 0; i < 8; i++) {
          if (!parsed.includes(i)) {
            missingIndices.push(i)
          }
        }
        const updated = [...parsed, ...missingIndices]
        localStorage.setItem('dashboard-metric-order', JSON.stringify(updated))
        return updated
      }
      return parsed
    }
    return [0, 1, 2, 3, 4, 5, 6, 7]
  })

  const metrics = getMetricsConfig(dashboardData)

  const handleMetricOrderChange = (newOrder) => {
    setMetricOrder(newOrder)
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-sre-text mb-2 text-left flex items-center gap-3">
          <span className="material-icons text-3xl text-sre-primary" aria-hidden>dashboard</span>
          Observability
        </h1>
        <p className="text-sre-text-muted text-left">
          Monitor and manage your observability infrastructure in real-time
        </p>
      </div>

      <MetricsGrid
        metrics={metrics}
        metricOrder={metricOrder}
        onMetricOrderChange={handleMetricOrderChange}
      />

      <DashboardLayout
        dashboardData={dashboardData}
        agentData={agentData}
      />
    </div>
  )
}

Dashboard.propTypes = {
  info: PropTypes.shape({
    service: PropTypes.string,
    version: PropTypes.string,
  }),
}
