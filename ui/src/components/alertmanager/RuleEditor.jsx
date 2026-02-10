import { useState, useEffect, useMemo } from 'react'
import PropTypes from 'prop-types'
import { Button, Input, Select } from '../ui'
import HelpTooltip from '../HelpTooltip'
import { getGroups, listMetricNames, testAlertRule } from '../../api'

const DURATION_PATTERN = /^(\d+ms|\d+s|\d+m|\d+h|\d+d|\d+w|\d+y)+$/

const RULE_TEMPLATES = [
  {
    id: 'cpu-system',
    name: 'High CPU (system)',
    expr: 'avg without (cpu, state) (rate(system_cpu_time_seconds_total{state="system"}[1m])) * 100 > 80',
    duration: '2m',
    severity: 'warning',
    summary: 'High system CPU',
    description: 'System CPU time above 80% for 2 minutes.'
  },
  {
    id: 'cpu-node',
    name: 'High CPU (node exporter)',
    expr: 'avg by (instance) (rate(node_cpu_seconds_total{mode="system"}[5m])) * 100 > 80',
    duration: '5m',
    severity: 'warning',
    summary: 'High node CPU',
    description: 'Node CPU system time above 80% for 5 minutes.'
  },
  {
    id: 'error-rate',
    name: 'High Error Rate',
    expr: 'sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05',
    duration: '5m',
    severity: 'critical',
    summary: 'Elevated 5xx error rate',
    description: 'More than 5% of requests are failing with 5xx responses.'
  }
]

const DEFAULT_FORM = {
  name: '',
  orgId: '',
  expr: '',
  duration: '1m',
  severity: 'warning',
  labels: {},
  annotations: { summary: '', description: '' },
  enabled: true,
  group: 'default',
  notificationChannels: [],
  visibility: 'private',
  sharedGroupIds: []
}

const VALID_SEVERITIES = new Set(['info', 'warning', 'critical'])

export default function RuleEditor({ rule, channels, apiKeys = [], onSave, onCancel }) {
  const [formData, setFormData] = useState(rule || DEFAULT_FORM)
  const [groups, setGroups] = useState([])
  const [selectedGroups, setSelectedGroups] = useState(new Set(rule?.sharedGroupIds || []))
  const [metricNames, setMetricNames] = useState([])
  const [metricFilter, setMetricFilter] = useState('')
  const [loadingMetrics, setLoadingMetrics] = useState(false)
  const [metricsError, setMetricsError] = useState(null)
  const [labelPairs, setLabelPairs] = useState(() => Object.entries(rule?.labels || {}).map(([key, value]) => ({ key, value })))
  const [validationErrors, setValidationErrors] = useState({})
  const [validationWarnings, setValidationWarnings] = useState([])
  const [saveError, setSaveError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)

  useEffect(() => {
    loadGroups()
  }, [])

  useEffect(() => {
    if (labelPairs.length === 0 && Object.keys(formData.labels || {}).length === 0) return
    const nextLabels = {}
    labelPairs.forEach(({ key, value }) => {
      const trimmed = key.trim()
      if (trimmed) nextLabels[trimmed] = value
    })
    setFormData((prev) => ({ ...prev, labels: nextLabels }))
  }, [labelPairs])

  const loadGroups = async () => {
    try {
      const groupsData = await getGroups()
      setGroups(groupsData)
    } catch {
      // Silently handle
    }
  }

  const validateForm = (data) => {
    const errors = {}
    const warnings = []

    if (!data.name || !data.name.trim()) {
      errors.name = 'Rule name is required.'
    } else if (data.name.trim().length > 100) {
      errors.name = 'Rule name must be 100 characters or fewer.'
    }

    if (!data.expr || !data.expr.trim()) {
      errors.expr = 'PromQL expression is required.'
    }

    if (data.duration && !DURATION_PATTERN.test(data.duration)) {
      errors.duration = 'Duration must use Prometheus format (e.g., 5m, 1h, 30s).'
    }

    if (!VALID_SEVERITIES.has(data.severity)) {
      errors.severity = 'Severity must be info, warning, or critical.'
    }

    const expr = data.expr || ''
    let depth = 0
    for (const ch of expr) {
      if (ch === '(') depth += 1
      if (ch === ')') depth -= 1
      if (depth < 0) break
    }
    if (depth !== 0) {
      errors.expr = errors.expr || 'Unbalanced parentheses in expression.'
    }

    if (!/[<>!=]=?|==/.test(expr)) {
      warnings.push('Expression has no comparison operator; alert may never fire.')
    }
    if (/(\brate\s*\(|\birate\s*\(|\bincrease\s*\(|\bdelta\s*\()/.test(expr) && !/\[[0-9]+(ms|s|m|h|d|w|y)\]/.test(expr)) {
      warnings.push('Rate/increase functions usually need a range selector like [5m].')
    }
    if (!data.annotations?.summary) {
      warnings.push('Summary is empty; notifications will be less clear.')
    }

    const labelKeys = new Set()
    const duplicateLabels = []
    labelPairs.forEach(({ key }) => {
      const trimmed = key.trim()
      if (!trimmed) return
      if (labelKeys.has(trimmed)) duplicateLabels.push(trimmed)
      labelKeys.add(trimmed)
    })
    if (duplicateLabels.length > 0) {
      errors.labels = `Duplicate label keys: ${duplicateLabels.join(', ')}`
    }

    return { errors, warnings }
  }

  useEffect(() => {
    const { errors, warnings } = validateForm(formData)
    setValidationErrors(errors)
    setValidationWarnings(warnings)
  }, [formData, labelPairs])

  const loadMetrics = async () => {
    if (!formData.orgId) {
      // We allow querying without orgId (backend falls back), but if the user
      // explicitly selected a product we honour that preference.
    }
    setLoadingMetrics(true)
    setMetricsError(null)
    try {
      const resp = await listMetricNames(formData.orgId || undefined)
      setMetricNames(Array.isArray(resp.metrics) ? resp.metrics : [])
    } catch (e) {
      setMetricsError(e.message || 'Failed to load metrics from Mimir')
      setMetricNames([])
    } finally {
      setLoadingMetrics(false)
    }
  }

  const filteredMetricNames = useMemo(() => {
    if (!metricFilter) return metricNames
    const q = metricFilter.toLowerCase()
    return metricNames.filter((name) => name.toLowerCase().includes(q))
  }, [metricNames, metricFilter])

  const effectiveLabels = useMemo(() => ({
    ...(formData.labels || {}),
    severity: formData.severity
  }), [formData.labels, formData.severity])

  const toggleGroup = (groupId) => {
    const newGroups = new Set(selectedGroups)
    if (newGroups.has(groupId)) {
      newGroups.delete(groupId)
    } else {
      newGroups.add(groupId)
    }
    setSelectedGroups(newGroups)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const { errors } = validateForm(formData)
    setValidationErrors(errors)
    if (Object.keys(errors).length > 0) return
    setSaveError(null)
    setSaving(true)
    Promise.resolve(onSave({
      ...formData,
      sharedGroupIds: Array.from(selectedGroups)
    })).then((ok) => {
      if (!ok) {
        setSaveError('Failed to save rule. Check the error banner for details.')
      }
    }).catch(() => {
      setSaveError('Failed to save rule. Check the error banner for details.')
    }).finally(() => {
      setSaving(false)
    })
  }

  const applyTemplate = (template) => {
    setFormData((prev) => ({
      ...prev,
      name: template.name,
      expr: template.expr,
      duration: template.duration,
      severity: template.severity,
      annotations: {
        ...prev.annotations,
        summary: template.summary,
        description: template.description
      }
    }))
  }

  const handleTestRule = async () => {
    if (!rule?.id) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testAlertRule(rule.id)
      setTestResult(result?.message || 'Test notification sent.')
    } catch (e) {
      setTestResult(e?.message || 'Failed to send test notification.')
    } finally {
      setTesting(false)
    }
  }

  const hasErrors = Object.keys(validationErrors).length > 0

  return (
    <div className="max-w-6xl mx-auto">
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Rule Configuration */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-sre-text border-b border-sre-border pb-2">Rule Configuration</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Rule Name <HelpTooltip text="Enter a descriptive name for your alert rule that clearly identifies what it monitors." />
              </label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                placeholder="e.g., HighCPUUsage"
                className="w-full"
              />
              {validationErrors.name && (
                <p className="text-xs text-red-400 mt-1 break-words">{validationErrors.name}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Severity <HelpTooltip text="Choose the severity level for this alert. Critical alerts require immediate attention, warnings are less urgent." />
              </label>
              <Select
                value={formData.severity}
                onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
                className="w-full"
              >
                <option value="info">Info</option>
                <option value="warning">Warning</option>
                <option value="critical">Critical</option>
              </Select>
              {validationErrors.severity && (
                <p className="text-xs text-red-400 mt-1 break-words">{validationErrors.severity}</p>
              )}
            </div>
          </div>

          {apiKeys.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Product / API Key <HelpTooltip text="Select the API key to scope this rule to a specific product, or leave empty to monitor all products." />
              </label>
              <Select
                value={formData.orgId || ''}
                onChange={(e) => setFormData({ ...formData, orgId: e.target.value })}
                className="w-full max-w-md"
              >
                <option value="">All products (no scope)</option>
                {apiKeys.map((k) => (
                  <option key={k.id} value={k.key}>
                    {k.name}{k.is_default ? ' (Default)' : ''}{k.is_enabled ? ' — active' : ''}
                  </option>
                ))}
              </Select>
            </div>
          )}
        </div>

        {/* Quick Templates */}
        <div className="bg-sre-surface/40 space-y-4">
          <div className="flex items-center gap-2">
            <span className="material-icons text-sre-primary">auto_awesome</span>
            <h4 className="text-sm font-semibold text-sre-text">Quick Templates</h4>
          </div>
          <p className="text-xs text-sre-text-muted leading-relaxed">
            Start from a known-good template, then tune the expression and thresholds for your environment.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {RULE_TEMPLATES.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => applyTemplate(template)}
                className="text-left p-3 rounded-lg border border-sre-border bg-sre-surface hover:border-sre-primary/40 hover:bg-sre-primary/5 transition-colors group"
              >
                <div className="text-sm font-semibold text-sre-text group-hover:text-sre-primary transition-colors">{template.name}</div>
                <div className="text-xs text-sre-text-muted mt-1 line-clamp-2">{template.summary}</div>
                <div className="text-[11px] text-sre-text-muted mt-2 font-mono break-all line-clamp-3 leading-tight">{template.expr}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Metric Explorer */}
        <div className="bg-sre-surface/40 space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="material-icons text-sre-primary">functions</span>
                <h4 className="text-sm font-semibold text-sre-text">Metric Explorer (optional)</h4>
              </div>
              <p className="text-xs text-sre-text-muted leading-relaxed">
                Load metric names from Mimir for the selected product and click to insert them into your PromQL expression.
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={loadMetrics} disabled={loadingMetrics}>
              {loadingMetrics ? (
                <>
                  <span className="material-icons text-sm mr-2 animate-spin">progress_activity</span>
                  Loading…
                </>
              ) : (
                <>
                  <span className="material-icons text-sm mr-2">refresh</span>
                  Load metrics
                </>
              )}
            </Button>
          </div>

          {metricsError && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400 break-words">
              {metricsError}
            </div>
          )}

          {metricNames.length > 0 && (
            <>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">Filter metrics</label>
                <Input
                  value={metricFilter}
                  onChange={(e) => setMetricFilter(e.target.value)}
                  placeholder="e.g., http_requests_total"
                  className="w-full"
                />
              </div>
              <div className="max-h-40 overflow-y-auto border border-dashed border-sre-border rounded-lg p-3 bg-sre-bg-alt">
                {filteredMetricNames.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {filteredMetricNames.map((name) => (
                      <button
                        key={name}
                        type="button"
                        onClick={() => {
                          const base = formData.expr || ''
                          const template = base ? `${base}\n${name}` : name
                          setFormData({ ...formData, expr: template })
                        }}
                        className="px-2 py-1 text-xs rounded-full border border-sre-border bg-sre-surface hover:bg-sre-primary/10 hover:border-sre-primary text-sre-text transition-colors break-all max-w-full"
                        title={name}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-sre-text-muted">No metrics match this filter.</p>
                )}
              </div>
            </>
          )}
        </div>

        {/* PromQL Expression */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-sre-text border-b border-sre-border pb-2">Alert Condition</h3>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              PromQL Expression <HelpTooltip text="Write a PromQL query that defines when this alert should fire. Use the metric explorer below to help build your query." />
            </label>
            <Input
              value={formData.expr}
              onChange={(e) => setFormData({ ...formData, expr: e.target.value })}
              required
              placeholder="e.g., rate(requests_total[5m]) > 100"
              className="w-full font-mono text-sm"
            />
            {validationErrors.expr && (
              <p className="text-xs text-red-400 mt-1 break-words max-w-full">{validationErrors.expr}</p>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Duration <HelpTooltip text="How long the condition must be true before the alert fires. Use Prometheus duration format (e.g., 5m, 1h)." />
              </label>
              <Input
                value={formData.duration}
                onChange={(e) => setFormData({ ...formData, duration: e.target.value })}
                placeholder="e.g., 5m, 1h"
                className="w-full"
              />
              {validationErrors.duration && (
                <p className="text-xs text-red-400 mt-1 break-words">{validationErrors.duration}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Group <HelpTooltip text="Group name for organizing related alerts. Alerts in the same group are treated as a single notification." />
              </label>
              <Input
                value={formData.group}
                onChange={(e) => setFormData({ ...formData, group: e.target.value })}
                placeholder="default"
                className="w-full"
              />
            </div>
          </div>
        </div>

        {/* Alert Details */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-sre-text border-b border-sre-border pb-2">Alert Details</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Summary <HelpTooltip text="A brief summary of the alert that will be shown in notifications and the UI." />
              </label>
              <Input
                value={formData.annotations.summary}
                onChange={(e) => setFormData({ ...formData, annotations: { ...formData.annotations, summary: e.target.value }})}
                placeholder="Brief alert summary"
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Description <HelpTooltip text="Detailed description of the alert condition and what it means when it fires." />
              </label>
              <Input
                value={formData.annotations.description}
                onChange={(e) => setFormData({ ...formData, annotations: { ...formData.annotations, description: e.target.value }})}
                placeholder="Detailed description"
                className="w-full"
              />
            </div>
          </div>
        </div>

        {/* Alert Labels */}
        <div className="border border-sre-border rounded-lg p-4 bg-sre-surface/40 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h4 className="text-sm font-semibold text-sre-text">Alert Labels</h4>
              <p className="text-xs text-sre-text-muted mt-1">Labels help route and group alerts. Severity is automatically added.</p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setLabelPairs([...labelPairs, { key: '', value: '' }])}
            >
              <span className="material-icons text-sm mr-2">add</span>
              Add Label
            </Button>
          </div>

          {labelPairs.length === 0 ? (
            <p className="text-xs text-sre-text-muted italic">No labels added yet.</p>
          ) : (
            <div className="space-y-3">
              {labelPairs.map((pair, idx) => (
                <div key={`${pair.key}-${idx}`} className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-3 items-center p-3 bg-sre-bg-alt rounded-lg">
                  <Input
                    value={pair.key}
                    onChange={(e) => {
                      const next = [...labelPairs]
                      next[idx] = { ...next[idx], key: e.target.value }
                      setLabelPairs(next)
                    }}
                    placeholder="label_key"
                    className="w-full"
                  />
                  <Input
                    value={pair.value}
                    onChange={(e) => {
                      const next = [...labelPairs]
                      next[idx] = { ...next[idx], value: e.target.value }
                      setLabelPairs(next)
                    }}
                    placeholder="value"
                    className="w-full"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setLabelPairs(labelPairs.filter((_, i) => i !== idx))}
                    className="justify-self-start text-red-400 hover:text-red-300 hover:bg-red-500/10"
                  >
                    <span className="material-icons text-sm">close</span>
                  </Button>
                </div>
              ))}
            </div>
          )}
          {validationErrors.labels && (
            <p className="text-xs text-red-400 break-words">{validationErrors.labels}</p>
          )}
        </div>

        {/* Rule Preview */}
        <div className="bg-sre-surface/40 space-y-4">
          <h4 className="text-sm font-semibold text-sre-text">Rule Preview</h4>

          <div className="space-y-4">
            <div className="space-y-2">
              <div className="text-xs text-sre-text-muted font-medium uppercase tracking-wide">Expression</div>
              <div className="text-xs font-mono text-sre-text break-words bg-sre-bg-alt p-3 rounded border max-h-24 overflow-y-auto">
                {formData.expr || 'No expression set'}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-1">
                <div className="text-xs text-sre-text-muted font-medium uppercase tracking-wide">Duration</div>
                <div className="text-sm text-sre-text font-mono bg-sre-bg-alt px-2 py-1 rounded">{formData.duration || '1m'}</div>
              </div>
              <div className="space-y-1">
                <div className="text-xs text-sre-text-muted font-medium uppercase tracking-wide">Group</div>
                <div className="text-sm text-sre-text font-mono bg-sre-bg-alt px-2 py-1 rounded">{formData.group || 'default'}</div>
              </div>
              <div className="space-y-1">
                <div className="text-xs text-sre-text-muted font-medium uppercase tracking-wide">Target Org</div>
                <div className="text-sm text-sre-text font-mono bg-sre-bg-alt px-2 py-1 rounded break-words">{formData.orgId || 'default org'}</div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-xs text-sre-text-muted font-medium uppercase tracking-wide">Labels</div>
              <div className="flex flex-wrap gap-2 min-h-[2rem] p-2 bg-sre-bg-alt rounded border">
                {Object.entries(effectiveLabels).length > 0 ? (
                  Object.entries(effectiveLabels).map(([key, value]) => (
                    <span key={key} className="text-xs px-2 py-1 bg-sre-surface border border-sre-border rounded text-sre-text break-all">
                      {key}={value}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-sre-text-muted italic">No labels</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Notification Channels */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-sre-text border-b border-sre-border pb-2">Notifications</h3>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Notification Channels {formData.notificationChannels?.length > 0 ? `(${formData.notificationChannels.length} selected)` : '(All channels)'} <HelpTooltip text="Select specific notification channels for this alert, or leave empty to use all enabled channels." />
            </label>
            <div className="space-y-3 max-h-64 overflow-y-auto border border-sre-border rounded-lg p-4 bg-sre-surface">
              {channels?.length > 0 ? (
                <>
                  <div className="flex items-center gap-3 pb-3 border-b border-sre-border">
                    <input
                      type="checkbox"
                      id="channel-all"
                      checked={!formData.notificationChannels || formData.notificationChannels.length === 0}
                      onChange={(e) => {
                        let newChannels = []
                        if (!e.target.checked) {
                          newChannels = channels ? channels.map(c => c.id) : []
                        }
                        setFormData({ ...formData, notificationChannels: newChannels })
                      }}
                      className="w-4 h-4"
                    />
                    <label htmlFor="channel-all" className="text-sm text-sre-text font-medium cursor-pointer">
                      All Channels (default)
                    </label>
                  </div>
                  <div className="space-y-2">
                    {channels.map((channel) => (
                      <div key={channel.id} className="flex items-center gap-3 p-2 rounded hover:bg-sre-bg-alt transition-colors">
                        <input
                          type="checkbox"
                          id={`channel-${channel.id}`}
                          checked={formData.notificationChannels?.includes(channel.id)}
                          onChange={(e) => {
                            const channels = formData.notificationChannels || []
                            const newChannels = e.target.checked
                              ? [...channels, channel.id]
                              : channels.filter(id => id !== channel.id)
                            setFormData({ ...formData, notificationChannels: newChannels })
                          }}
                          className="w-4 h-4"
                        />
                        <label htmlFor={`channel-${channel.id}`} className="text-sm text-sre-text flex items-center gap-2 cursor-pointer flex-1 min-w-0">
                          <span className={`px-2 py-0.5 rounded text-xs flex-shrink-0 ${channel.enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                            {channel.type}
                          </span>
                          <span className="truncate">{channel.name}</span>
                          {!channel.enabled && <span className="text-xs text-gray-500 flex-shrink-0">(disabled)</span>}
                        </label>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-sm text-sre-text-muted italic">No channels configured. Create channels first to assign them to alerts.</p>
              )}
            </div>
            <p className="text-xs text-sre-text-muted mt-2">
              Select specific channels to notify, or leave empty to notify all channels
            </p>
          </div>
        </div>

        {/* Validation & Settings */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-sre-text border-b border-sre-border pb-2">Settings</h3>

          {/* Enable Rule */}
          <div className="flex items-center gap-3 p-3 bg-sre-surface/40 rounded-lg border border-sre-border">
            <input
              type="checkbox"
              id="enabled"
              checked={formData.enabled}
              onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
              className="w-4 h-4"
            />
            <label htmlFor="enabled" className="text-sm text-sre-text cursor-pointer">
              <span className="font-medium">Enable this rule</span> <HelpTooltip text="Only enabled rules will trigger alerts. Disabled rules are saved but won't fire." />
            </label>
          </div>

          {/* Visibility Settings */}
          <div className="space-y-3">
            <label htmlFor="rule-visibility" className="block text-sm font-medium text-sre-text">
              <span className="material-icons text-sm align-middle mr-1">visibility</span> Visibility <HelpTooltip text="Control who can view and edit this alert rule. Private rules are only visible to you." />
            </label>
            <Select
              id="rule-visibility"
              value={formData.visibility || 'private'}
              onChange={(e) => {
                const newVisibility = e.target.value
                setFormData({ ...formData, visibility: newVisibility })
                if (newVisibility !== 'group') {
                  setSelectedGroups(new Set())
                }
              }}
              className="w-full max-w-md"
            >
              <option value="private">Private - Only visible to me</option>
              <option value="group">Group - Share with specific groups</option>
              <option value="tenant">Tenant - Visible to all users in tenant</option>
            </Select>
            <p className="text-xs text-sre-text-muted leading-relaxed">
              {formData.visibility === 'private' && 'Only you can view and edit this rule'}
              {formData.visibility === 'group' && 'Users in selected groups can view this rule'}
              {formData.visibility === 'tenant' && 'All users in your organization can view this rule'}
            </p>
          </div>

          {/* Group Sharing */}
          {formData.visibility === 'group' && groups?.length > 0 && (
            <div>
              <label htmlFor="rule-groups" className="block text-sm font-medium text-sre-text mb-3">
                Share with Groups <HelpTooltip text="Select which user groups can view and edit this alert rule." />
              </label>
              <div id="rule-groups" className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-48 overflow-y-auto p-3 border border-sre-border rounded-lg bg-sre-surface">
                {groups.map((group) => (
                  <label
                    key={group.id}
                    className="flex items-center gap-3 p-2 bg-sre-bg-alt rounded cursor-pointer hover:bg-sre-accent/10 transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={selectedGroups.has(group.id)}
                      onChange={() => toggleGroup(group.id)}
                      className="w-4 h-4"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sre-text truncate">{group.name}</div>
                      {group.description && (
                        <div className="text-xs text-sre-text-muted truncate">{group.description}</div>
                      )}
                    </div>
                  </label>
                ))}
              </div>
              <p className="text-xs text-sre-text-muted mt-2">
                {selectedGroups.size} group{selectedGroups.size === 1 ? '' : 's'} selected
              </p>
            </div>
          )}
        </div>

        {/* Checks and Issues */}
        {(hasErrors || validationWarnings.length > 0 || saveError) && (
          <div className="border border-sre-border rounded-lg p-4 bg-sre-surface/40 space-y-3">
            <h4 className="text-sm font-semibold text-sre-text">Checks and Issues</h4>
            {saveError && (
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400 break-words">
                {saveError}
              </div>
            )}
            {hasErrors && (
              <div className="space-y-2">
                {Object.values(validationErrors).map((msg, idx) => (
                  <div key={`err-${idx}`} className="p-3 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400 break-words">
                    {msg}
                  </div>
                ))}
              </div>
            )}
            {validationWarnings.length > 0 && (
              <div className="space-y-2">
                {validationWarnings.map((msg, idx) => (
                  <div key={`warn-${idx}`} className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs text-yellow-400 break-words">
                    {msg}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Form Actions */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pt-6 border-t border-sre-border">
          <div className="flex gap-3">
            {rule?.id && (
              <Button type="button" variant="outline" onClick={handleTestRule} disabled={testing}>
                <span className="material-icons text-sm mr-2" aria-hidden="true">science</span>{' '}
                {testing ? 'Testing...' : 'Test Notification'}
              </Button>
            )}
            {testResult && (
              <span className="text-xs text-sre-text-muted self-center break-words max-w-xs">{testResult}</span>
            )}
          </div>
          <div className="flex gap-3">
            <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
            <Button type="submit" disabled={saving || hasErrors}>
              <span className="material-icons text-sm mr-2" aria-hidden="true">save</span>{' '}
              {saving ? 'Saving...' : 'Save Rule'}
            </Button>
          </div>
        </div>
      </form>
    </div>
  )
}

RuleEditor.propTypes = {
  rule: PropTypes.shape({
    name: PropTypes.string,
    orgId: PropTypes.string,
    expr: PropTypes.string,
    duration: PropTypes.string,
    severity: PropTypes.string,
    labels: PropTypes.object,
    annotations: PropTypes.shape({
      summary: PropTypes.string,
      description: PropTypes.string,
    }),
    enabled: PropTypes.bool,
    group: PropTypes.string,
    notificationChannels: PropTypes.arrayOf(PropTypes.string),
    sharedGroupIds: PropTypes.arrayOf(PropTypes.string),
  }),
  channels: PropTypes.arrayOf(PropTypes.object),
  apiKeys: PropTypes.arrayOf(PropTypes.object),
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}
