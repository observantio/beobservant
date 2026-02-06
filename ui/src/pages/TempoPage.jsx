import React, { useEffect, useState, useMemo, useRef } from 'react'
import { fetchTempoServices, searchTraces, getTrace } from '../api'
import { Card, Button, Select, Input, Alert, Badge, Spinner } from '../components/ui'
import ReactFlow, { Background, Controls, MiniMap, Handle, Position, MarkerType } from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from '@dagrejs/dagre'

const ServiceNode = ({ data }) => {
  const { name, stats, colorClass } = data
  return (
    <div className={`rounded-xl border border-sre-border bg-sre-surface px-4 py-3 shadow-lg min-w-[220px] ${colorClass}`}>
      <Handle type="target" position={Position.Left} className="!bg-sre-primary/70 !w-2 !h-2" />
      <Handle type="source" position={Position.Right} className="!bg-sre-primary/70 !w-2 !h-2" />
      <div className="flex items-center gap-2 mb-2">
        <span className="material-icons text-sre-primary">hub</span>
        <div className="font-semibold text-sre-text truncate">{name}</div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-sre-text-muted">
        <div>Traces: <span className="text-sre-text">{stats.traces}</span></div>
        <div>Spans: <span className="text-sre-text">{stats.spans}</span></div>
        <div>P50: <span className="text-sre-text">{stats.p50}</span></div>
        <div>P95: <span className="text-sre-text">{stats.p95}</span></div>
        <div>Error: <span className={stats.errorRateNum > 5 ? 'text-red-400' : 'text-green-400'}>{stats.errorRate}</span></div>
        <div>In/Out: <span className="text-sre-text">{stats.inbound}/{stats.outbound}</span></div>
      </div>
      {stats.pain && (
        <div className="mt-2 text-[10px] px-2 py-1 rounded bg-red-500/10 text-red-400 border border-red-500/30">
          Pain point: high latency or error rate
        </div>
      )}
    </div>
  )
}

const ServiceGraph = ({ traces }) => {
  const getServiceName = (span) => {
    if (!span) return 'unknown'
    if (span.serviceName) return span.serviceName
    if (span.process?.serviceName) return span.process.serviceName
    if (Array.isArray(span.tags)) {
      const t = span.tags.find(t => t.key === 'service.name' || t.key === 'service' || t.key?.toLowerCase().includes('service'))
      if (t && (t.value || t.value === 0)) return String(t.value)
    } else if (span.tags && typeof span.tags === 'object') {
      if (span.tags['service.name']) return String(span.tags['service.name'])
      if (span.tags['service']) return String(span.tags['service'])
      const k = Object.keys(span.tags).find(k => k.toLowerCase().includes('service'))
      if (k) return String(span.tags[k])
    }
    if (span.attributes && typeof span.attributes === 'object') {
      if (span.attributes['service.name']) return String(span.attributes['service.name'])
      if (span.attributes['service']) return String(span.attributes['service'])
    }
    return 'unknown'
  }

  const getSpanAttr = (span, keys) => {
    if (!span) return null
    const keyList = Array.isArray(keys) ? keys : [keys]

    if (span.attributes && typeof span.attributes === 'object') {
      for (const k of keyList) {
        if (span.attributes[k] !== undefined && span.attributes[k] !== null) {
          return span.attributes[k]
        }
      }
    }

    if (Array.isArray(span.tags)) {
      for (const k of keyList) {
        const t = span.tags.find(tag => tag?.key === k)
        if (t && t.value !== undefined && t.value !== null) return t.value
      }
    } else if (span.tags && typeof span.tags === 'object') {
      for (const k of keyList) {
        if (span.tags[k] !== undefined && span.tags[k] !== null) return span.tags[k]
      }
    }

    return null
  }

  const formatDuration = (ns) => {
    const safe = Math.max(0, Number(ns || 0))
    const ms = safe / 1000000
    if (ms < 1) return `${(safe / 1000).toFixed(0)}μs`
    if (ms < 1000) return `${ms.toFixed(2)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  const percentile = (arr, p) => {
    if (!arr.length) return 0
    const sorted = [...arr].sort((a, b) => a - b)
    const idx = Math.min(sorted.length - 1, Math.max(0, Math.floor(sorted.length * p)))
    return sorted[idx]
  }

  const graphData = useMemo(() => {
    const services = new Map()
    const edges = new Map()

    const addEdge = (source, target, duration = 0, hasError = false, count = 1) => {
      if (!source || !target) return
      if (source === target) return
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
        if (!source || !target) return
        if (source === target) return
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
        const hasError = span.tags?.find(t => t.key === 'error' && t.value === true) || span.status?.code === 'ERROR'
        if (hasError) stats.errors += 1

        const parentId = span.parentSpanId || span.parentSpanID
        if (parentId) {
          const parentSpan = spans.find(s => (s.spanId || s.spanID) === parentId)
          if (parentSpan) {
            const parentService = getServiceName(parentSpan)
            addLocalEdge(parentService, serviceName, duration, hasError, 1)
          }
        }

        const peerServiceRaw = getSpanAttr(span, [
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
        const rootSpan = spans.find(s => !(s.parentSpanId || s.parentSpanID)) || spans[0]
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

    // compute inbound/outbound
    for (const [key, val] of edges.entries()) {
      const [src, dst] = key.split('->')
      if (services.has(src)) services.get(src).outbound += val.count
      if (services.has(dst)) services.get(dst).inbound += val.count
    }

    return { services, edges }
  }, [traces])

  const nodes = useMemo(() => {
    const nodesArray = []
    const entries = Array.from(graphData.services.entries())
    entries.forEach(([name, stats], idx) => {
      const p50 = percentile(stats.durations, 0.5)
      const p95 = percentile(stats.durations, 0.95)
      const errorRateNum = stats.spans ? (stats.errors / stats.spans) * 100 : 0
      const pain = p95 > 1000000000 || errorRateNum > 5
      const colorClass = pain ? 'ring-2 ring-red-500/60' : errorRateNum > 1 ? 'ring-2 ring-yellow-400/60' : 'ring-2 ring-green-500/40'
      nodesArray.push({
        id: name,
        type: 'service',
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        position: { x: 0, y: 0 },
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
  }, [graphData.services])

  const edges = useMemo(() => {
    return Array.from(graphData.edges.entries()).map(([key, val]) => {
      const [source, target] = key.split('->')
      const p95 = percentile(val.durations, 0.95)
      const errorRateNum = val.count ? (val.errors / val.count) * 100 : 0
      const isPain = p95 > 1000000000 || errorRateNum > 5
      const color = isPain ? '#ef4444' : errorRateNum > 1 ? '#f59e0b' : '#10b981'
      const label = `${val.count} calls · p95 ${formatDuration(p95)} · err ${errorRateNum.toFixed(1)}%`
      return {
        id: key,
        source,
        target,
        label,
        animated: isPain,
        type: 'smoothstep',
        style: { stroke: color, strokeWidth: isPain ? 2.5 : 1.5 },
        labelStyle: { fill: '#cbd5e1', fontSize: 10 },
        labelBgStyle: { fill: '#0f172a', fillOpacity: 0.7 },
        markerEnd: { type: MarkerType.ArrowClosed, color }
      }
    })
  }, [graphData.edges])

  const layouted = useMemo(() => {
    const nodeWidth = 260
    const nodeHeight = 140
    const g = new dagre.graphlib.Graph()
    g.setDefaultEdgeLabel(() => ({}))
    g.setGraph({ rankdir: 'LR', nodesep: 80, ranksep: 140, edgesep: 30 })

    nodes.forEach((n) => {
      g.setNode(n.id, { width: nodeWidth, height: nodeHeight })
    })
    edges.forEach((e) => {
      g.setEdge(e.source, e.target)
    })

    dagre.layout(g)

    const layoutedNodes = nodes.map((n) => {
      const nodeWithPosition = g.node(n.id)
      return {
        ...n,
        position: {
          x: nodeWithPosition.x - nodeWidth / 2,
          y: nodeWithPosition.y - nodeHeight / 2
        },
        style: { width: nodeWidth, height: nodeHeight }
      }
    })

    return { nodes: layoutedNodes, edges }
  }, [nodes, edges])

  if (layouted.nodes.length === 0) return null

  return (
    <div className="bg-sre-surface/30 border border-sre-border rounded-lg p-6">
      <h3 className="text-lg font-semibold text-sre-text mb-4 flex items-center gap-2">
        <span className="material-icons text-sre-primary">hub</span>
        Service Dependency Map (pain points highlighted)
      </h3>
      <div className="h-[520px] rounded-lg overflow-hidden border border-sre-border bg-sre-bg">
        <ReactFlow
          nodes={layouted.nodes}
          edges={layouted.edges}
          nodeTypes={{ service: ServiceNode }}
          fitView
          minZoom={0.2}
          maxZoom={1.5}
        >
          <MiniMap zoomable pannable />
          <Controls />
          <Background gap={16} />
        </ReactFlow>
      </div>
      <div className="mt-3 text-xs text-sre-text-muted">
        Colors: green = healthy, amber = elevated errors, red = pain point (high p95 or error rate). Edge labels show call count, p95 latency, and error rate.
      </div>
    </div>
  )
}

const TraceTimeline = ({ trace, onClose }) => {
  if (!trace || !trace.spans) return null
  
  const traceId = trace.traceId || trace.traceID || trace.id || ''

  const getServiceName = (span) => {
    if (!span) return 'unknown'
    if (span.serviceName) return span.serviceName
    if (span.process?.serviceName) return span.process.serviceName
    if (Array.isArray(span.tags)) {
      const t = span.tags.find(t => t.key === 'service.name' || t.key === 'service' || t.key?.toLowerCase().includes('service'))
      if (t && (t.value || t.value === 0)) return String(t.value)
    } else if (span.tags && typeof span.tags === 'object') {
      if (span.tags['service.name']) return String(span.tags['service.name'])
      if (span.tags['service']) return String(span.tags['service'])
      const k = Object.keys(span.tags).find(k => k.toLowerCase().includes('service'))
      if (k) return String(span.tags[k])
    }
    if (span.attributes && typeof span.attributes === 'object') {
      if (span.attributes['service.name']) return String(span.attributes['service.name'])
      if (span.attributes['service']) return String(span.attributes['service'])
    }
    return 'unknown'
  }

  const spans = [...trace.spans].sort((a, b) => a.startTime - b.startTime)
  const spansWithEndTime = spans.map(s => ({
    ...s,
    endTime: s.startTime + (s.duration || 0),
    serviceName: getServiceName(s)
  }))
  const minTime = Math.min(...spansWithEndTime.map(s => s.startTime))
  const maxTime = Math.max(...spansWithEndTime.map(s => s.endTime))
  const totalDuration = maxTime - minTime
  
  const getSpanPosition = (span) => {
    const start = ((span.startTime - minTime) / totalDuration) * 100
    const width = ((span.endTime - span.startTime) / totalDuration) * 100
    return { left: `${start}%`, width: `${Math.max(width, 0.5)}%` }
  }
  
  const getSpanColor = (span) => {
    const hasError = span.tags?.find(t => t.key === 'error' && t.value === true) || span.status?.code === 'ERROR'
    if (hasError) return 'bg-red-500'
    if (span.serviceName?.includes('payment')) return 'bg-green-500'
    if (span.serviceName?.includes('api')) return 'bg-blue-500'
    if (span.serviceName?.includes('frontend')) return 'bg-purple-500'
    return 'bg-sre-primary'
  }
  
  const formatDuration = (ns) => {
    const ms = ns / 1000000
    if (ms < 1) return `${(ns / 1000).toFixed(0)}μs`
    if (ms < 1000) return `${ms.toFixed(2)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }
  
  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 animate-fade-in" onClick={onClose}>
      <div className="bg-sre-bg w-full max-w-6xl max-h-[90vh] rounded-xl shadow-2xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="bg-sre-surface border-b border-sre-border px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-sre-text flex items-center gap-2">
              <span className="material-icons text-sre-primary">timeline</span>
              Trace Timeline
            </h2>
            <p className="text-sm text-sre-text-muted font-mono mt-1">ID: {traceId}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-sre-bg-alt rounded-lg transition-colors">
            <span className="material-icons text-sre-text-muted hover:text-sre-text">close</span>
          </button>
        </div>
        
        <div className="p-6 overflow-y-auto overflow-x-hidden max-h-[calc(90vh-80px)]">
          <div className="bg-sre-surface/50 border border-sre-border rounded-lg p-4 mb-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <div className="text-sre-text-muted mb-1">Total Duration</div>
                <div className="text-lg font-bold text-sre-text">{formatDuration(totalDuration)}</div>
              </div>
              <div>
                <div className="text-sre-text-muted mb-1">Spans</div>
                <div className="text-lg font-bold text-sre-text">{spans.length}</div>
              </div>
              <div>
                <div className="text-sre-text-muted mb-1">Services</div>
                <div className="text-lg font-bold text-sre-text">
                  {new Set(spans.map(s => s.serviceName)).size}
                </div>
              </div>
              <div>
                <div className="text-sre-text-muted mb-1">Status</div>
                <Badge variant={spans.some(s => s.tags?.find(t => t.key === 'error' && t.value === true) || s.status?.code === 'ERROR') ? 'error' : 'success'}>
                  {spans.some(s => s.tags?.find(t => t.key === 'error' && t.value === true) || s.status?.code === 'ERROR') ? 'ERROR' : 'OK'}
                </Badge>
              </div>
            </div>
          </div>
          
          <div className="space-y-2">
              {spansWithEndTime.map((span, idx) => {
              const position = getSpanPosition(span)
              const duration = span.duration || 0
              const depth = span.parentSpanId || span.parentSpanID ? 
                spansWithEndTime.findIndex(s => (s.spanId || s.spanID) === (span.parentSpanId || span.parentSpanID)) + 1 : 0
              
              return (
                <div key={span.spanId || span.spanID || idx} className="group relative" style={{ paddingLeft: `${depth * 20}px` }}>
                  <div className="flex items-center gap-3">
                    <div className="min-w-[160px] max-w-[220px] break-words whitespace-normal">
                      <div className="text-sm font-semibold text-sre-text break-words whitespace-normal">{span.operationName}</div>
                      <div className="text-xs text-sre-text-muted break-words whitespace-normal">{span.serviceName}</div>
                    </div>
                    
                    <div className="flex-1 relative h-8 bg-sre-surface rounded border border-sre-border">
                      <div 
                        className={`absolute top-0 h-full ${getSpanColor(span)} rounded transition-all group-hover:opacity-80`}
                        style={position}
                        title={`${span.operationName} - ${formatDuration(duration)}`}
                      />
                    </div>
                    
                    <div className="min-w-[80px] text-right text-xs font-mono text-sre-text-muted">
                      {formatDuration(duration)}
                    </div>
                  </div>
                  
                  {span.tags && (
                    <div className="ml-[220px] mt-1 flex flex-wrap gap-1">
                      {Array.isArray(span.tags)
                        ? span.tags.slice(0, 5).map((t, idx2) => {
                            const k = t?.key || t?.k || `tag${idx2}`
                            const v = t?.value ?? t?.v ?? t?.val ?? t
                            return (
                              <span key={k + idx2} className="text-[10px] px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-sre-text-muted break-words whitespace-normal" style={{ maxWidth: 'calc(100% - 240px)' }}>
                                {k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                              </span>
                            )
                          })
                        : Object.entries(span.tags).slice(0, 5).map(([key, value]) => (
                            <span key={key} className="text-[10px] px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-sre-text-muted break-words whitespace-normal" style={{ maxWidth: 'calc(100% - 240px)' }}>
                              {key}: {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                            </span>
                          ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function TempoPage() {
  const [services, setServices] = useState([])
  const [service, setService] = useState('')
  const [operation, setOperation] = useState('')
  const [durationRange, setDurationRange] = useState([100000000, 5000000000]) // 100ms to 5s in nanoseconds
  const [statusFilter, setStatusFilter] = useState('all')
  const [timeRange, setTimeRange] = useState(60)
  const [traces, setTraces] = useState(null)
  const [selectedTrace, setSelectedTrace] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [viewMode, setViewMode] = useState('list')

  const getServiceName = (span) => {
    if (!span) return 'unknown'
    if (span.serviceName) return span.serviceName
    if (span.process?.serviceName) return span.process.serviceName
    if (Array.isArray(span.tags)) {
      const t = span.tags.find(t => t.key === 'service.name' || t.key === 'service' || t.key?.toLowerCase().includes('service'))
      if (t && (t.value || t.value === 0)) return String(t.value)
    } else if (span.tags && typeof span.tags === 'object') {
      if (span.tags['service.name']) return String(span.tags['service.name'])
      if (span.tags['service']) return String(span.tags['service'])
      const k = Object.keys(span.tags).find(k => k.toLowerCase().includes('service'))
      if (k) return String(span.tags[k])
    }
    if (span.attributes && typeof span.attributes === 'object') {
      if (span.attributes['service.name']) return String(span.attributes['service.name'])
      if (span.attributes['service']) return String(span.attributes['service'])
    }
    return 'unknown'
  }

  useEffect(() => {
    loadServices()
  }, [])

  async function loadServices() {
    try {
      const data = await fetchTempoServices()
      setServices(data || [])
    } catch (e) {
      setServices([])
      console.error('Failed to load services:', e)
    }
  }

  async function onSearch(e) {
    if (e) e.preventDefault()
    setError(null)
    setLoading(true)
    
    try {
      const end = Date.now() * 1000
      const start = end - (timeRange * 60 * 1000000)
      
      const res = await searchTraces({ 
        service, 
        operation,
        minDuration: `${Math.floor(Math.max(0, durationRange[0]) / 1000000)}ms`,
        maxDuration: `${Math.floor(Math.max(durationRange[0], durationRange[1]) / 1000000)}ms`,
        start: Math.floor(start),
        end: Math.floor(end),
        limit: 100
      })
      
      setTraces(res)
      
      // Keep user-selected duration range stable after search
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleTraceClick(traceId) {
    try {
      const trace = await getTrace(traceId)
      if (trace && trace.spans) {
        const enrichedTrace = {
          ...trace,
          spans: trace.spans.map(s => ({
            ...s,
            endTime: s.startTime + (s.duration || 0)
          }))
        }
        setSelectedTrace(enrichedTrace)
      } else {
        setError('Trace data is incomplete')
      }
    } catch (e) {
      setError(`Failed to load trace: ${e.message}`)
    }
  }

  const filteredTraces = useMemo(() => {
    if (!traces?.data) return []
    
    return traces.data.filter(trace => {
      if (statusFilter === 'error') {
        return trace.spans?.some(s => s.status?.code === 'ERROR' || s.tags?.error === 'true')
      }
      if (statusFilter === 'ok') {
        return !trace.spans?.some(s => s.status?.code === 'ERROR' || s.tags?.error === 'true')
      }
      return true
    })
  }, [traces, statusFilter])

  const traceStats = useMemo(() => {
    if (!filteredTraces.length) return null
    
    const durations = filteredTraces.map(t => {
      if (!t.spans || t.spans.length === 0) return 0
      const rootSpan = t.spans.find(s => !s.parentSpanId) || t.spans[0]
      return rootSpan?.duration || 0
    })
    
    const errorCount = filteredTraces.filter(t => 
      t.spans?.some(s => s.status?.code === 'ERROR' || s.tags?.error === 'true')
    ).length
    
    return {
      total: filteredTraces.length,
      avgDuration: durations.reduce((a, b) => a + b, 0) / durations.length,
      maxDuration: Math.max(...durations),
      minDuration: Math.min(...durations),
      errorRate: (errorCount / filteredTraces.length * 100).toFixed(1),
      errorCount
    }
  }, [filteredTraces])

  const formatDuration = (ns) => {
    if (ns === null || ns === undefined || isNaN(ns)) return '0ms'
    const safe = Math.max(0, Number(ns))
    const ms = safe / 1000000
    if (ms < 1) return `${(safe / 1000).toFixed(0)}μs`
    if (ms < 1000) return `${ms.toFixed(2)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-sre-text mb-2 flex items-center gap-2">
            <span className="material-icons text-sre-primary text-3xl">timeline</span>
            Tempo — Distributed Tracing
          </h1>
          <p className="text-sre-text-muted">Search and analyze distributed traces across your services</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode('list')}
            className={`px-3 py-2 rounded-lg transition-colors ${viewMode === 'list' ? 'bg-sre-primary text-white' : 'bg-sre-surface text-sre-text hover:bg-sre-surface-light'}`}
          >
            <span className="material-icons text-sm">list</span>
          </button>
          <button
            onClick={() => setViewMode('graph')}
            className={`px-3 py-2 rounded-lg transition-colors ${viewMode === 'graph' ? 'bg-sre-primary text-white' : 'bg-sre-surface text-sre-text hover:bg-sre-surface-light'}`}
          >
            <span className="material-icons text-sm">hub</span>
          </button>
        </div>
      </div>

      {error && (
        <Alert variant="error" className="mb-6">
          <strong>Error:</strong> {error}
        </Alert>
      )}

      {traceStats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Total Traces</div>
            <div className="text-2xl font-bold text-sre-text">{traceStats.total}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Avg Duration</div>
            <div className="text-2xl font-bold text-sre-text">{formatDuration(traceStats.avgDuration)}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Max Duration</div>
            <div className="text-2xl font-bold text-sre-text">{formatDuration(traceStats.maxDuration)}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Error Rate</div>
            <div className={`text-2xl font-bold ${traceStats.errorRate > 5 ? 'text-red-500' : 'text-green-500'}`}>
              {traceStats.errorRate}%
            </div>
          </Card>
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Errors</div>
            <div className="text-2xl font-bold text-red-500">{traceStats.errorCount}</div>
          </Card>
        </div>
      )}

      <Card title="Search Traces" subtitle="Query traces by service, operation, and duration" className="mb-6">
        <form onSubmit={onSearch} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Select
              label="Service"
              value={service}
              onChange={(e) => setService(e.target.value)}
            >
              <option value="">-- All Services --</option>
              {services.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </Select>

            <Input
              label="Operation"
              value={operation}
              onChange={(e) => setOperation(e.target.value)}
              placeholder="e.g., HTTP GET /api"
            />

            <Select
              label="Time Range"
              value={timeRange}
              onChange={(e) => setTimeRange(Number(e.target.value))}
            >
              <option value={5}>Last 5 minutes</option>
              <option value={15}>Last 15 minutes</option>
              <option value={60}>Last 1 hour</option>
              <option value={180}>Last 3 hours</option>
              <option value={360}>Last 6 hours</option>
            </Select>

            <Select
              label="Status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All</option>
              <option value="ok">Success Only</option>
              <option value="error">Errors Only</option>
            </Select>
          </div>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              <span className="material-icons text-sm mr-1 align-middle">schedule</span>
              Duration Range: {formatDuration(durationRange[0])} - {formatDuration(durationRange[1])}
            </label>
            <div className="space-y-2">
              <div>
                <label className="text-xs text-sre-text-muted">Minimum Duration</label>
                <input
                  type="range"
                  min="0"
                  max="10000000000"
                  step="50000000"
                  value={durationRange[0]}
                  onChange={(e) => {
                    const newMin = Math.max(0, Number(e.target.value))
                    const nextMax = Math.max(durationRange[1], newMin + 10000000)
                    setDurationRange([newMin, nextMax])
                  }}
                  className="w-full h-2 bg-sre-surface rounded-lg appearance-none cursor-pointer accent-sre-primary"
                />
              </div>
              <div>
                <label className="text-xs text-sre-text-muted">Maximum Duration</label>
                <input
                  type="range"
                  min="0"
                  max="10000000000"
                  step="50000000"
                  value={durationRange[1]}
                  onChange={(e) => {
                    const newMax = Math.max(0, Number(e.target.value))
                    const nextMin = Math.min(durationRange[0], newMax - 10000000)
                    setDurationRange([Math.max(0, nextMin), newMax])
                  }}
                  className="w-full h-2 bg-sre-surface rounded-lg appearance-none cursor-pointer accent-sre-primary"
                />
              </div>
            </div>
            <div className="flex justify-between text-xs text-sre-text-muted mt-1">
              <span>0ms</span>
              <span>10s</span>
            </div>
            <button
              type="button"
              onClick={() => setDurationRange([100000000, 5000000000])}
              className="text-xs text-sre-primary hover:underline mt-1"
            >
              Reset range
            </button>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => {
              setService('')
              setOperation('')
              setDurationRange([100000000, 5000000000])
              setStatusFilter('all')
            }}>
              Clear Filters
            </Button>
            <Button type="submit" loading={loading}>
              <span className="material-icons text-sm mr-2">search</span>
              Search Traces
            </Button>
          </div>
        </form>
      </Card>

      {viewMode === 'graph' && filteredTraces.length > 0 && (
        <div className="mb-6">
          <ServiceGraph traces={filteredTraces} />
        </div>
      )}

      <Card 
        title="Trace Results" 
        subtitle={filteredTraces.length ? `Found ${filteredTraces.length} traces` : 'Run a search to see results'}
      >
        {loading ? (
          <div className="py-12">
            <Spinner size="lg" />
          </div>
        ) : filteredTraces.length ? (
          <div className="space-y-2">
            {filteredTraces.map((t) => {
              const rootSpan = t.spans?.find(s => !s.parentSpanId && !s.parentSpanID) || t.spans?.[0]
              const duration = rootSpan?.duration || 0
              const hasError = t.spans?.some(s => s.status?.code === 'ERROR' || s.tags?.find(tag => tag.key === 'error' && tag.value === true))
              const allServices = t.spans?.map(s => getServiceName(s)).filter(Boolean) || []
              const serviceCount = new Set(allServices).size
              const rootServiceName = rootSpan ? getServiceName(rootSpan) : 'unknown'
              
              const traceId = t.traceID || t.traceId
              
              return (
                <div
                  key={traceId}
                  onClick={() => handleTraceClick(traceId)}
                  className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/50 transition-all cursor-pointer group"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <span className="material-icons text-sre-primary group-hover:scale-110 transition-transform">
                          {hasError ? 'error' : 'check_circle'}
                        </span>
                        <span className="font-mono text-sm text-sre-text font-semibold">
                          {traceId?.substring(0, 16)}...
                        </span>
                        <Badge variant={hasError ? 'error' : 'success'}>
                          {hasError ? 'ERROR' : 'OK'}
                        </Badge>
                        <Badge variant="info">{t.spans?.length || 0} spans</Badge>
                        <Badge variant="default">{serviceCount} services</Badge>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                          <span className="text-sre-text-muted">Service: </span>
                          <span className="text-sre-text font-semibold">{rootServiceName}</span>
                        </div>
                        {rootSpan?.operationName && (
                          <div>
                            <span className="text-sre-text-muted">Operation: </span>
                            <span className="text-sre-text font-semibold">{rootSpan.operationName}</span>
                          </div>
                        )}
                        <div>
                          <span className="text-sre-text-muted">Duration: </span>
                          <span className="text-sre-text font-semibold font-mono">{formatDuration(duration)}</span>
                        </div>
                        <div>
                          <span className="text-sre-text-muted">Started: </span>
                          <span className="text-sre-text font-semibold">
                            {new Date(rootSpan?.startTime / 1000).toLocaleTimeString()}
                          </span>
                        </div>
                      </div>
                    </div>
                    <span className="material-icons text-sre-text-muted group-hover:text-sre-primary transition-colors">
                      chevron_right
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-center py-12">
            <span className="material-icons text-6xl text-sre-text-subtle mb-4">timeline</span>
            <p className="text-sre-text-muted mb-4">No traces found. Try adjusting your search criteria or time range.</p>
          </div>
        )}
      </Card>

      {selectedTrace && (
        <TraceTimeline trace={selectedTrace} onClose={() => setSelectedTrace(null)} />
      )}
    </div>
  )
}
