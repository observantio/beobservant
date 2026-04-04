export const DURATION_PATTERN = /^(\d+ms|\d+s|\d+m|\d+h|\d+d|\d+w|\d+y)+$/;

export const RULE_TEMPLATES = [
  {
    id: "high-cpu",
    name: "High CPU",
    expr: '100 - (100 * (((sum by (instance) (rate(system_cpu_time_seconds_total{cpu_mode="idle"}[5m]))) or (sum by (instance) (rate(system_cpu_time_seconds_total{state="idle"}[5m])))) / clamp_min(sum by (instance) (rate(system_cpu_time_seconds_total[5m])), 1e-9))) > 80',
    duration: "2m",
    severity: "warning",
    summary: "High CPU utilization",
    description: "CPU busy (non-idle) above 80% for 2 minutes.",
  },
  {
    id: "high-memory",
    name: "High Memory",
    expr: "100 * ((avg by (instance) (system_memory_utilization)) or (avg by (instance) (system_memory_used_ratio)) or (avg by (instance) ((system_memory_total_bytes - system_memory_available_bytes) / clamp_min(system_memory_total_bytes, 1)))) > 90",
    duration: "5m",
    severity: "critical",
    summary: "High memory utilization",
    description: "Memory usage ratio above 90% for 5 minutes.",
  },
  {
    id: "high-disk",
    name: "High Disk Usage",
    expr: '100 * ((max by (instance, mountpoint) (system_filesystem_utilization)) or ((max by (instance, mountpoint) (system_filesystem_usage{key="used_bytes_user_visible"})) / clamp_min(max by (instance, mountpoint) (system_filesystem_usage{key="total_bytes"}), 1))) > 90',
    duration: "10m",
    severity: "warning",
    summary: "High filesystem utilization",
    description: "One or more filesystems are above 90% usage.",
  },
  {
    id: "high-load-average",
    name: "High CPU Load Average",
    expr: "max by (instance) (system_cpu_load_average_1m) > 4",
    duration: "5m",
    severity: "warning",
    summary: "Host load average is high",
    description: "1-minute load average has been above 4 for 5 minutes.",
  },
  {
    id: "process-cpu-hot",
    name: "Top Process CPU Saturation",
    expr: "topk(1, avg_over_time(process_cpu_utilization[5m]) * 100) > 85",
    duration: "5m",
    severity: "warning",
    summary: "A process is saturating CPU",
    description: "Top process CPU utilization is above 85% for 5 minutes.",
  },
  {
    id: "blocked-processes-high",
    name: "Blocked Processes High",
    expr: "max by (instance) (system_processes_blocked) > 10",
    duration: "3m",
    severity: "warning",
    summary: "Blocked process count is high",
    description: "More than 10 blocked processes can indicate IO or lock contention.",
  },
  {
    id: "host-metrics-missing",
    name: "Host Metrics Missing",
    expr: "absent_over_time(system_cpu_time_seconds_total[10m]) == 1",
    duration: "10m",
    severity: "critical",
    summary: "Host metrics are missing",
    description: "Host CPU metrics have stopped arriving for at least 10 minutes.",
  },
];

export const DEFAULT_FORM = {
  name: "",
  orgId: "",
  expr: "",
  duration: "1m",
  severity: "warning",
  labels: {},
  annotations: { summary: "", description: "" },
  enabled: true,
  group: "default",
  notificationChannels: [],
  visibility: "private",
  sharedGroupIds: [],
};

const VALID_SEVERITIES = new Set(["info", "warning", "critical"]);

export function normalizeRuleOrChannelVisibility(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "tenant" || normalized === "public") return "public";
  if (normalized === "group") return "group";
  return "private";
}

function _normalizedSet(values) {
  return new Set((values || []).map((value) => String(value || "").trim()).filter(Boolean));
}

export function isChannelSelectableForRuleVisibility(
  ruleVisibility,
  channelVisibility,
  {
    ruleSharedGroupIds = [],
    channelSharedGroupIds = [],
  } = {},
) {
  const ruleScope = normalizeRuleOrChannelVisibility(ruleVisibility);
  const channelScope = normalizeRuleOrChannelVisibility(channelVisibility);
  if (ruleScope === "private") return channelScope === "private";
  if (ruleScope === "group") {
    if (channelScope === "private") return true;
    if (channelScope !== "group") return false;
    const ruleGroups = _normalizedSet(ruleSharedGroupIds);
    const channelGroups = _normalizedSet(channelSharedGroupIds);
    for (const groupId of ruleGroups) {
      if (channelGroups.has(groupId)) return true;
    }
    return false;
  }
  return channelScope === "private" || channelScope === "group";
}

export function filterSelectableChannels(
  channels,
  ruleVisibility,
  {
    ruleSharedGroupIds = [],
  } = {},
) {
  return (channels || []).filter((channel) =>
    isChannelSelectableForRuleVisibility(ruleVisibility, channel?.visibility, {
      ruleSharedGroupIds,
      channelSharedGroupIds:
        channel?.sharedGroupIds || channel?.shared_group_ids || [],
    }),
  );
}

export function validateRuleForm(data, labelPairs) {
  const errors = {};
  const warnings = [];

  if (!data.name || !data.name.trim()) {
    errors.name = "Rule name is required.";
  } else if (data.name.trim().length > 100) {
    errors.name = "Rule name must be 100 characters or fewer.";
  }

  if (!data.expr || !data.expr.trim()) {
    errors.expr = "PromQL expression is required.";
  }

  if (data.duration && !DURATION_PATTERN.test(data.duration)) {
    errors.duration =
      "Duration must use Prometheus format (e.g., 5m, 1h, 30s).";
  }

  if (!VALID_SEVERITIES.has(data.severity)) {
    errors.severity = "Severity must be info, warning, or critical.";
  }

  const expr = data.expr || "";
  let depth = 0;
  for (const ch of expr) {
    if (ch === "(") depth += 1;
    if (ch === ")") depth -= 1;
    if (depth < 0) break;
  }
  if (depth !== 0) {
    errors.expr = errors.expr || "Unbalanced parentheses in expression.";
  }

  if (!/[<>!=]=?|==/.test(expr)) {
    warnings.push(
      "Expression has no comparison operator; alert may never fire.",
    );
  }
  if (
    /(\brate\s*\(|\birate\s*\(|\bincrease\s*\(|\bdelta\s*\()/.test(expr) &&
    !/\[[0-9]+(ms|s|m|h|d|w|y)\]/.test(expr)
  ) {
    warnings.push(
      "Rate/increase functions usually need a range selector like [5m].",
    );
  }
  if (!data.annotations?.summary) {
    warnings.push("Summary is empty; notifications will be less clear.");
  }

  const labelKeys = new Set();
  const duplicateLabels = [];
  labelPairs.forEach(({ key }) => {
    const trimmed = key.trim();
    if (!trimmed) return;
    if (labelKeys.has(trimmed)) duplicateLabels.push(trimmed);
    labelKeys.add(trimmed);
  });
  if (duplicateLabels.length > 0) {
    errors.labels = `Duplicate label keys: ${duplicateLabels.join(", ")}`;
  }

  return { errors, warnings };
}

export function createLabelPairsFromRule(rule) {
  const entries = Object.entries(rule?.labels || {});
  return entries.map(([key, value], index) => ({
    id: `label-${index}-${key}`,
    key,
    value,
  }));
}
