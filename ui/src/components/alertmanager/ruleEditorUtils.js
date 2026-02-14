export const DURATION_PATTERN = /^(\d+ms|\d+s|\d+m|\d+h|\d+d|\d+w|\d+y)+$/

export const RULE_TEMPLATES = [
  {
    id: 'cpu-system',
    name: 'High CPU (system)',
    expr: '100 - (avg without (cpu, state) (rate(system_cpu_time_seconds_total{state="idle"}[1m])) * 100) > 80',
    duration: '2m',
    severity: 'warning',
    summary: 'High CPU utilization',
    description: 'CPU busy (non-idle) above 80% for 2 minutes.'
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

export const DEFAULT_FORM = {
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

export function validateRuleForm(data, labelPairs) {
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

export function createLabelPairsFromRule(rule) {
  const entries = Object.entries(rule?.labels || {})
  return entries.map(([key, value], index) => ({
    id: `label-${index}-${key}`,
    key,
    value,
  }))
}
