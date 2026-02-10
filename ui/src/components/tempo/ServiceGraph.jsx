/**
 * ServiceGraph component for visualizing service dependencies
 * @module components/tempo/ServiceGraph
 */

import { useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import ReactFlow, { Background, Controls, MiniMap, Handle, Position, MarkerType } from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from '@dagrejs/dagre'
import { getServiceName, getSpanAttribute, percentile, hasSpanError as spanHasErrorUtil } from '../../utils/helpers'
import { formatDuration } from '../../utils/formatters'

const PAIN_P95_THRESHOLD_US = 1_000_000
const WARN_P95_THRESHOLD_US = 300_000

/**
 * ServiceNode component for rendering service nodes in the graph
 * @param {object} props - Component props
 * @param {object} props.data - Node data
 */

const ServiceNode = ({ data }) => {
  const { name, stats, colorClass } = data
  const isPain = stats.pain
  const errorRate = stats.errorRateNum

  return (
    <div className={`rounded-xl border-2 bg-gradient-to-br from-sre-surface to-sre-surface/80 px-4 py-3 shadow-lg min-w-[240px] transition-all duration-300 hover:shadow-xl hover:scale-105 ${colorClass} ${isPain ? 'border-red-500/50' : 'border-sre-border'}`}>
      <Handle type="target" position={Position.Left} className="!bg-sre-primary/70 !w-3 !h-3 !border-2 !border-sre-bg hover:!bg-sre-primary hover:!scale-110 transition-all" />
      <Handle type="source" position={Position.Right} className="!bg-sre-primary/70 !w-3 !h-3 !border-2 !border-sre-bg hover:!bg-sre-primary hover:!scale-110 transition-all" />

      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <div className={`w-3 h-3 rounded-full ${isPain ? 'bg-red-500' : errorRate > 1 ? 'bg-yellow-500' : 'bg-green-500'} animate-pulse`}></div>
        <div className="font-bold text-sre-text truncate flex-1">{name}</div>
        {isPain && <span className="material-icons text-red-500 text-sm animate-bounce">warning</span>}
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between">
          <span className="text-sre-text-muted">Traces:</span>
          <span className="text-sre-text font-medium">{stats.traces}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">Spans:</span>
          <span className="text-sre-text font-medium">{stats.spans}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">P50:</span>
          <span className="text-sre-text font-medium">{stats.p50}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">P95:</span>
          <span className={`font-medium ${stats.p95.includes('ms') && parseFloat(stats.p95) > 1000 ? 'text-red-400' : 'text-sre-text'}`}>{stats.p95}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">Error:</span>
          <span className={`font-medium ${errorRate > 5 ? 'text-red-400' : errorRate > 1 ? 'text-yellow-400' : 'text-green-400'}`}>{stats.errorRate}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">I/O:</span>
          <span className="text-sre-text font-medium">{stats.inbound}/{stats.outbound}</span>
        </div>
      </div>

      {/* Pain Point Indicator */}
      {isPain && (
        <div className="mt-3 text-[10px] px-2 py-1.5 rounded-lg bg-gradient-to-r from-red-500/20 to-red-600/20 text-red-300 border border-red-500/30 animate-pulse">
          <span className="material-icons text-xs mr-1 align-middle">local_fire_department</span>
          Pain point: high latency or error rate
        </div>
      )}

      {/* Health Indicator */}
      <div className="mt-2 flex items-center gap-1">
        <div className={`h-1.5 flex-1 rounded-full ${isPain ? 'bg-red-500/20' : errorRate > 1 ? 'bg-yellow-500/20' : 'bg-green-500/20'}`}>
          <div
            className={`h-full rounded-full transition-all duration-1000 ${isPain ? 'bg-red-500' : errorRate > 1 ? 'bg-yellow-500' : 'bg-green-500'}`}
            style={{ width: `${Math.max(10, 100 - errorRate * 2)}%` }}
          ></div>
        </div>
        <span className="text-[10px] text-sre-text-muted">Health</span>
      </div>
    </div>
  )
}

ServiceNode.propTypes = {
  data: PropTypes.shape({
    name: PropTypes.string.isRequired,
    stats: PropTypes.object.isRequired,
    colorClass: PropTypes.string.isRequired,
  }).isRequired,
}

/**
 * Helper: determine if a span indicates an error
 * @param {object} span
 * @returns {boolean}
 */
function spanHasError(span) {
  return spanHasErrorUtil(span)
}

/**
 * Helper: find a parent span by id
 * @param {Array} spans
 * @param {string} parentId
 * @returns {object|undefined}
 */
function findParentSpanById(spans, parentId) {
  return spans.find(s => (s.spanId || s.spanID) === parentId)
}

/**
 * Helper: find the root span in a span list
 * @param {Array} spans
 * @returns {object}
 */
function findRootSpan(spans) {
  return spans.find(s => !(s.parentSpanId || s.parentSpanID)) || spans[0]
}

/**
 * ServiceGraph component
 * @param {object} props - Component props
 * @param {Array} props.traces - Array of trace objects
 */
export default function ServiceGraph({ traces }) {
  const [activeNodeId, setActiveNodeId] = useState(null)
  const [activeEdgeId, setActiveEdgeId] = useState(null)
  const [hoverNodeId, setHoverNodeId] = useState(null)

  const graphData = useMemo(() => {
    const services = new Map()
    const edges = new Map()

    const addEdge = (source, target, duration = 0, hasError = false, count = 1) => {
      if (!source || !target || source === target) return
      const key = `${source}->${target}`
      const edge = edges.get(key) || { count: 0, durations: [], errors: 0 }
      edge.count += count
      if (duration > 0) edge.durations.push(duration)
      if (hasError) edge.errors += 1
      edges.set(key, edge)
    }

    traces.forEach(trace => {
      if (!trace.spans) return
      const spans = trace.spans
      const localEdges = new Map()

      const addLocalEdge = (source, target, duration = 0, hasError = false, count = 1) => {
        if (!source || !target || source === target) return
        const key = `${source}->${target}`
        const edge = localEdges.get(key) || { count: 0, durations: [], errors: 0 }
        edge.count += count
        if (duration > 0) edge.durations.push(duration)
        if (hasError) edge.errors += 1
        localEdges.set(key, edge)
      }

      spans.forEach(span => {
        const serviceName = getServiceName(span)
        if (!services.has(serviceName)) {
          services.set(serviceName, { spans: 0, errors: 0, durations: [], traces: new Set(), inbound: 0, outbound: 0 })
        }
        const stats = services.get(serviceName)
        stats.spans += 1
        stats.traces.add(trace.traceID || trace.traceId || '')
        const duration = Number(span.duration || 0)
        if (duration > 0) stats.durations.push(duration)
        const hasError = spanHasError(span)
        if (hasError) stats.errors += 1

        const parentId = span.parentSpanId || span.parentSpanID
        if (parentId) {
          const parentSpan = findParentSpanById(spans, parentId)
          if (parentSpan) {
            const parentService = getServiceName(parentSpan)
            addLocalEdge(parentService, serviceName, duration, hasError, 1)
          }
        }

        const peerServiceRaw = getSpanAttribute(span, [
          'peer.service',
          'peer.service.name',
          'rpc.service',
          'rpc.system',
          'server.address',
          'server.name'
        ])
        const peerService = peerServiceRaw ? String(peerServiceRaw) : null
        if (peerService && peerService !== serviceName) {
          if (!services.has(peerService)) {
            services.set(peerService, { spans: 0, errors: 0, durations: [], traces: new Set(), inbound: 0, outbound: 0 })
          }
          addLocalEdge(serviceName, peerService, duration, hasError, 1)
        }
      })

      if (localEdges.size === 0 && spans.length > 1) {
        const rootSpan = findRootSpan(spans)
        const rootService = getServiceName(rootSpan)
        const servicesInTrace = new Set(spans.map(s => getServiceName(s)).filter(Boolean))
        servicesInTrace.delete(rootService)
        servicesInTrace.forEach((svc) => {
          addLocalEdge(rootService, svc, 0, false, 1)
        })
      }

      for (const [key, val] of localEdges.entries()) {
        const [src, dst] = key.split('->')
        addEdge(src, dst, 0, false, 0)
        const edge = edges.get(key)
        edge.count += val.count
        edge.durations.push(...val.durations)
        edge.errors += val.errors
        edges.set(key, edge)
      }
    })

    // Compute inbound/outbound
    for (const [key, val] of edges.entries()) {
      const [src, dst] = key.split('->')
      if (services.has(src)) services.get(src).outbound += val.count
      if (services.has(dst)) services.get(dst).inbound += val.count
    }

    return { services, edges }
  }, [traces])

  const nodes = useMemo(() => {
    const nodesArray = []
    const entries = Array.from(graphData.services.entries()).sort((a, b) => a[0].localeCompare(b[0]))
    entries.forEach(([name, stats]) => {
      const p50 = percentile(stats.durations, 0.5)
      const p95 = percentile(stats.durations, 0.95)
      const errorRateNum = stats.spans ? (stats.errors / stats.spans) * 100 : 0
      const pain = p95 > PAIN_P95_THRESHOLD_US || errorRateNum > 5
      let colorClass
      if (pain) {
        colorClass = 'ring-2 ring-red-500/60'
      } else if (p95 > WARN_P95_THRESHOLD_US || errorRateNum > 1) {
        colorClass = 'ring-2 ring-yellow-400/60'
      } else {
        colorClass = 'ring-2 ring-green-500/40'
      }
      const isActive = activeNodeId === name || hoverNodeId === name
      const isConnected = activeNodeId
        ? graphData.edges.has(`${name}->${activeNodeId}`) || graphData.edges.has(`${activeNodeId}->${name}`)
        : true
      nodesArray.push({
        id: name,
        type: 'service',
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        position: { x: 0, y: 0 },
        className: isActive ? 'service-node-active' : '',
        style: {
          opacity: activeNodeId && !isConnected && !isActive ? 0.35 : 1,
          transition: 'opacity 200ms ease'
        },
        data: {
          name,
          colorClass,
          stats: {
            spans: stats.spans,
            traces: stats.traces.size,
            p50: formatDuration(p50),
            p95: formatDuration(p95),
            errorRate: `${errorRateNum.toFixed(1)}%`,
            errorRateNum,
            inbound: stats.inbound,
            outbound: stats.outbound,
            pain
          }
        }
      })
    })
    return nodesArray
  }, [graphData.services, graphData.edges, activeNodeId, hoverNodeId])

  const insights = useMemo(() => {
    const serviceStats = Array.from(graphData.services.entries()).map(([name, stats]) => {
      const p95 = percentile(stats.durations, 0.95)
      const errorRateNum = stats.spans ? (stats.errors / stats.spans) * 100 : 0
      return {
        name,
        p95,
        errorRateNum,
        spans: stats.spans,
        traces: stats.traces.size,
        inbound: stats.inbound,
        outbound: stats.outbound
      }
    })

    const edgeStats = Array.from(graphData.edges.entries()).map(([key, val]) => {
      const [source, target] = key.split('->')
      const p95 = percentile(val.durations, 0.95)
      const errorRateNum = val.count ? (val.errors / val.count) * 100 : 0
      return {
        id: key,
        source,
        target,
        p95,
        errorRateNum,
        count: val.count
      }
    })

    const painServices = serviceStats
      .filter(s => s.p95 > PAIN_P95_THRESHOLD_US || s.errorRateNum > 5)
      .sort((a, b) => (b.p95 + b.errorRateNum) - (a.p95 + a.errorRateNum))
      .slice(0, 3)

    const topCalls = [...edgeStats].sort((a, b) => b.count - a.count).slice(0, 3)
    const topErrors = [...edgeStats].sort((a, b) => b.errorRateNum - a.errorRateNum).slice(0, 3)

    return { serviceStats, edgeStats, painServices, topCalls, topErrors }
  }, [graphData.edges, graphData.services])

  const edges = useMemo(() => {
    return Array.from(graphData.edges.entries()).map(([key, val]) => {
      const [source, target] = key.split('->')
      const p95 = percentile(val.durations, 0.95)
      const errorRateNum = val.count ? (val.errors / val.count) * 100 : 0
      const isPain = p95 > PAIN_P95_THRESHOLD_US || errorRateNum > 5
      const isActive = activeEdgeId === key
      const isConnectedToActive = activeNodeId ? source === activeNodeId || target === activeNodeId : true
      const fade = activeNodeId && !isConnectedToActive && !isActive
      let color
      if (isPain) {
        color = '#ef4444'
      } else if (p95 > WARN_P95_THRESHOLD_US || errorRateNum > 1) {
        color = '#f59e0b'
      } else {
        color = '#10b981'
      }
      const label = `${val.count} calls · p95 ${formatDuration(p95)} · err ${errorRateNum.toFixed(1)}%`

      return {
        id: key,
        source,
        target,
        label,
        animated: true, // Always animate for flow direction
        type: 'smoothstep',
        className: isActive ? 'edge-active' : '',
        style: {
          stroke: color,
          strokeWidth: isActive ? 4 : isPain ? 3 : 2,
          strokeDasharray: isActive ? '6 6' : isPain ? '4 4' : '0',
          opacity: fade ? 0.2 : 1,
          filter: isActive
            ? 'drop-shadow(0 0 6px rgba(59, 130, 246, 0.6))'
            : isPain
              ? 'drop-shadow(0 0 4px rgba(239, 68, 68, 0.5))'
              : 'none'
        },
        labelStyle: {
          fontSize: 11,
          fontWeight: '500',
          fill: fade ? 'var(--sre-text-muted)' : 'var(--sre-text)',
          filter: 'drop-shadow(0 0 2px var(--sre-bg))'
        },
        labelBgStyle: {
          fill: 'var(--sre-surface)',
          fillOpacity: fade ? 0.4 : 0.9,
          stroke: 'var(--sre-border)',
          strokeWidth: 1,
          rx: 4
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
          width: isActive ? 22 : isPain ? 20 : 16,
          height: isActive ? 22 : isPain ? 20 : 16
        }
      }
    })
  }, [graphData.edges, activeEdgeId, activeNodeId])

  const layouted = useMemo(() => {
    const nodeWidth = 260
    const nodeHeight = 140

    const g = new dagre.graphlib.Graph()
    g.setDefaultEdgeLabel(() => ({}))
    g.setGraph({
      rankdir: 'LR',
      ranker: 'tight-tree',
      nodesep: 80,
      ranksep: 140,
      edgesep: 20,
      marginx: 20,
      marginy: 20
    })

    nodes.forEach((n) => {
      g.setNode(n.id, { width: nodeWidth, height: nodeHeight })
    })

    edges.forEach((e) => {
      if (e.source && e.target) g.setEdge(e.source, e.target)
    })

    dagre.layout(g)

    const layoutedNodes = nodes.map((n) => {
      const pos = g.node(n.id)
      return {
        ...n,
        position: { x: pos.x - nodeWidth / 2, y: pos.y - nodeHeight / 2 },
        style: { width: nodeWidth, height: nodeHeight }
      }
    })

    return { nodes: layoutedNodes, edges }
  }, [nodes, edges])

  if (layouted.nodes.length === 0) return null

  const activeNode = insights.serviceStats.find(s => s.name === activeNodeId)
  const activeEdge = insights.edgeStats.find(e => e.id === activeEdgeId)
  const activeDirection = activeEdge ? `${activeEdge.source} → ${activeEdge.target}` : null

  return (
    <div className="bg-gradient-to-br from-sre-surface/30 to-sre-surface/10 border-2 border-sre-border/50 rounded-xl p-6 shadow-lg">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold text-sre-text flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sre-primary to-sre-primary-light flex items-center justify-center">
            <span className="material-icons text-white text-sm">hub</span>
          </div>
          Service Dependency Map
          <span className="text-sm font-normal text-sre-text-muted">(pain points highlighted)</span>
        </h3>
        <div className="flex items-center gap-2">
          <div className="text-xs text-sre-text-muted bg-sre-surface px-2 py-1 rounded-lg border">
            {layouted.nodes.length} services • {layouted.edges.length} connections
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 mb-4">
        <div className="p-4 bg-sre-surface/60 rounded-xl border border-sre-border/60">
          <div className="text-xs text-sre-text-muted mb-2">Insights</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded-lg border border-sre-border/50 bg-sre-surface/60">
              <div className="text-sre-text-muted mb-1">Top Pain Services</div>
              {insights.painServices.length ? insights.painServices.map(s => (
                <div key={s.name} className="flex items-center justify-between text-sre-text">
                  <button
                    type="button"
                    onClick={() => { setActiveNodeId(s.name); setActiveEdgeId(null) }}
                    className="truncate hover:text-sre-primary"
                  >
                    {s.name}
                  </button>
                  <span className="text-red-400">{formatDuration(s.p95)}</span>
                </div>
              )) : (
                <div className="text-sre-text-muted">No pain points</div>
              )}
            </div>
            <div className="p-3 rounded-lg border border-sre-border/50 bg-sre-surface/60">
              <div className="text-sre-text-muted mb-1">Busiest Flows</div>
              {insights.topCalls.length ? insights.topCalls.map(e => (
                <div key={e.id} className="flex items-center justify-between text-sre-text">
                  <button
                    type="button"
                    onClick={() => { setActiveEdgeId(e.id); setActiveNodeId(null) }}
                    className="truncate hover:text-sre-primary"
                  >
                    {e.source} → {e.target}
                  </button>
                  <span className="text-sre-text-muted">{e.count}</span>
                </div>
              )) : (
                <div className="text-sre-text-muted">No flows</div>
              )}
            </div>
            <div className="p-3 rounded-lg border border-sre-border/50 bg-sre-surface/60">
              <div className="text-sre-text-muted mb-1">Highest Error Rate</div>
              {insights.topErrors.length ? insights.topErrors.map(e => (
                <div key={e.id} className="flex items-center justify-between text-sre-text">
                  <button
                    type="button"
                    onClick={() => { setActiveEdgeId(e.id); setActiveNodeId(null) }}
                    className="truncate hover:text-sre-primary"
                  >
                    {e.source} → {e.target}
                  </button>
                  <span className="text-yellow-400">{e.errorRateNum.toFixed(1)}%</span>
                </div>
              )) : (
                <div className="text-sre-text-muted">No errors</div>
              )}
            </div>
          </div>
        </div>
        <div className="p-4 bg-sre-surface/60 rounded-xl border border-sre-border/60">
          <div className="text-xs text-sre-text-muted mb-2">Selection</div>
          {activeNode && (
            <div className="text-sm text-sre-text space-y-1">
              <div className="font-semibold">{activeNode.name}</div>
              <div className="text-xs text-sre-text-muted">Traces: {activeNode.traces} · Spans: {activeNode.spans}</div>
              <div className="text-xs text-sre-text-muted">P95: {formatDuration(activeNode.p95)} · Error: {activeNode.errorRateNum.toFixed(1)}%</div>
              <div className="text-xs text-sre-text-muted">Inbound: {activeNode.inbound} · Outbound: {activeNode.outbound}</div>
            </div>
          )}
          {activeEdge && (
            <div className="text-sm text-sre-text space-y-1">
              <div className="font-semibold">{activeEdge.source} → {activeEdge.target}</div>
              <div className="text-xs text-sre-text-muted">Direction: {activeDirection}</div>
              <div className="text-xs text-sre-text-muted">Calls: {activeEdge.count}</div>
              <div className="text-xs text-sre-text-muted">P95: {formatDuration(activeEdge.p95)} · Error: {activeEdge.errorRateNum.toFixed(1)}%</div>
            </div>
          )}
          {!activeNode && !activeEdge && (
            <div className="text-xs text-sre-text-muted">Click a node or edge to focus and see details.</div>
          )}
        </div>
      </div>

      <div className="h-[600px] rounded-xl overflow-hidden border-2 border-sre-border bg-gradient-to-br from-sre-bg to-sre-surface/20 shadow-inner">
        <ReactFlow
          nodes={layouted.nodes}
          edges={layouted.edges}
          nodeTypes={{ service: ServiceNode }}
          fitView
          minZoom={0.1}
          maxZoom={2}
          defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
          className="react-flow-interactive"
          onPaneClick={() => { setActiveNodeId(null); setActiveEdgeId(null) }}
          onNodeClick={(_, node) => {
            setActiveNodeId(node.id)
            setActiveEdgeId(null)
          }}
          onEdgeClick={(_, edge) => {
            setActiveEdgeId(edge.id)
            setActiveNodeId(null)
          }}
          onNodeMouseEnter={(_, node) => setHoverNodeId(node.id)}
          onNodeMouseLeave={() => setHoverNodeId(null)}
        >
          <MiniMap
            zoomable
            pannable
            nodeColor="#1f2937"
            maskColor="rgba(0, 0, 0, 0.2)"
            style={{ background: 'var(--sre-surface)' }}
          />
          <Controls
            showZoom
            showFitView
            showInteractive
            className="react-flow-controls-custom"
          />
          <Background
            gap={20}
            color="var(--sre-border)"
            variant="dots"
          />
        </ReactFlow>
      </div>

      {/* Legend */}
      <div className="mt-4 p-4 bg-sre-surface/50 rounded-lg border border-sre-border/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse"></div>
              <span className="text-sre-text-muted">Healthy</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-yellow-500 animate-pulse"></div>
              <span className="text-sre-text-muted">Warning</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-red-500 animate-bounce"></div>
              <span className="text-sre-text-muted">Pain Point</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-0.5 bg-gradient-to-r from-green-500 via-yellow-500 to-red-500 rounded"></div>
              <span className="text-sre-text-muted">Flow Direction</span>
            </div>
          </div>
          <div className="text-xs text-sre-text-muted">
            Edge labels: call count • p95 latency • error rate • animated direction
          </div>
        </div>
      </div>
    </div>
  )
}

ServiceGraph.propTypes = {
  traces: PropTypes.arrayOf(PropTypes.object).isRequired,
}
