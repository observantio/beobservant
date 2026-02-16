import { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { Card } from '../ui'
import { ConnectedServices } from './ConnectedServices'
import { AgentActivitySection } from './AgentActivitySection'
import { DataVolume } from './DataVolume'
import { SystemMetricsCard } from './SystemMetricsCard'

export function DashboardLayout({ dashboardData, agentData }) {
  const [draggedIndex, setDraggedIndex] = useState(null)
  const [layoutOrder, setLayoutOrder] = useState(() => {
    const saved = localStorage.getItem('dashboard-layout-order')
    return saved ? JSON.parse(saved) : [0, 1, 2, 3]
  })

  const layoutComponents = [
    {
      id: 'connected-services',
      title: "Connected Services",
      subtitle: "Observability stack components",
      className: "lg:col-span-2",
      content: <ConnectedServices />
    },
    {
      id: 'active-otel-agents',
      title: "Active OTEL Agents",
      subtitle: "Agents Activity",
      className: "lg:col-span-2",
      content: (
        <AgentActivitySection
          loading={agentData.loadingAgents}
          agents={agentData.agentActivity}
        />
      )
    },
    {
      id: 'data-volume',
      className: "",
      content: (
        <DataVolume
          loadingLogs={dashboardData.loadingLogs}
          logVolumeSeries={dashboardData.logVolumeSeries}
          loadingTempoVolume={dashboardData.loadingTempoVolume}
          tempoVolumeSeries={dashboardData.tempoVolumeSeries}
        />
      )
    },
    {
      id: 'server-metrics',
      title: "Observant Process",
      subtitle: dashboardData.systemMetrics?.stress?.message || "Process resource utilization",
      className: "",
      content: (
        <SystemMetricsCard
          loading={dashboardData.loadingSystemMetrics}
          systemMetrics={dashboardData.systemMetrics}
        />
      )
    }
  ]

  const sanitizedLayoutOrder = (() => {
    const max = layoutComponents.length
    const seen = new Set()
    const parsed = Array.isArray(layoutOrder) ? layoutOrder : []
    const result = []
    for (const idx of parsed) {
      if (typeof idx === 'number' && idx >= 0 && idx < max && !seen.has(idx)) {
        result.push(idx)
        seen.add(idx)
      }
    }
    // Append any missing indices so we always render all sections
    for (let i = 0; i < max; i++) {
      if (!seen.has(i)) result.push(i)
    }
    return result
  })()

  // Persist cleaned order if it differs from current state (run after first render)
  useEffect(() => {
    try {
      const curr = Array.isArray(layoutOrder) ? layoutOrder : []
      if (JSON.stringify(curr) !== JSON.stringify(sanitizedLayoutOrder)) {
        setLayoutOrder(sanitizedLayoutOrder)
        localStorage.setItem('dashboard-layout-order', JSON.stringify(sanitizedLayoutOrder))
      }
    } catch (e) {
      // Silently handle localStorage failure
    }
  }, [layoutComponents.length])

  const handleLayoutDragStart = (e, index) => {
    setDraggedIndex(index)
    e.dataTransfer.effectAllowed = 'move'
  }

  const handleLayoutDrop = (e, dropIndex) => {
    e.preventDefault()
    if (draggedIndex === null || draggedIndex === dropIndex) return

    const newOrder = [...layoutOrder]
    const draggedItem = newOrder[draggedIndex]
    newOrder.splice(draggedIndex, 1)
    newOrder.splice(dropIndex, 0, draggedItem)

    setLayoutOrder(newOrder)
    localStorage.setItem('dashboard-layout-order', JSON.stringify(newOrder))
    setDraggedIndex(null)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const handleDragEnd = () => {
    setDraggedIndex(null)
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {sanitizedLayoutOrder.map((layoutIndex, displayIndex) => {
        const component = layoutComponents[layoutIndex]
        if (!component) return null
        return (
          <div
            key={component.id}
            className={`transition-transform duration-200 ease-out will-change-transform ${
              draggedIndex === displayIndex ? 'opacity-50 scale-95 shadow-xl' : ''
            }`}
          >
            <Card
              title={component.title}
              subtitle={component.subtitle}
              className={`${component.className} cursor-move relative`}
              draggable
              onDragStart={(e) => handleLayoutDragStart(e, displayIndex)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleLayoutDrop(e, displayIndex)}
              onDragEnd={handleDragEnd}
            >
              <div className="absolute top-4 right-4 text-sre-text-muted hover:text-sre-text transition-colors z-10">
                <span className="material-icons text-sm drag-handle" aria-hidden>drag_indicator</span>
              </div>
              {component.content}
            </Card>
          </div>
        )
      })}
    </div>
  )
}

DashboardLayout.propTypes = {
  dashboardData: PropTypes.object.isRequired,
  agentData: PropTypes.object.isRequired,
}