import { useCallback, useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import { getActiveAgents, getAgentMetricVolume, getAgents } from "../api";
import { useAuth } from "../contexts/AuthContext";
import PageHeader from "../components/ui/PageHeader";
import { Badge, Button, Card, Spinner, Sparkline } from "../components/ui";

const ACTIVE_WINDOW_MS = 10 * 60 * 1000;
const VOLUME_DEFAULT = { points: [], current: 0, peak: 0, average: 0 };

function positiveOrFallback(primary, fallback = 0) {
  const value = Number(primary);
  if (Number.isFinite(value) && value > 0) return value;
  const fallbackValue = Number(fallback);
  return Number.isFinite(fallbackValue) ? fallbackValue : 0;
}

function resolveActiveApiKey(user) {
  const keys = user?.api_keys || [];
  return keys.find((key) => key.is_enabled) || keys.find((key) => key.is_default) || null;
}

function formatRelativeTime(value) {
  if (!value) return "No heartbeat yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";

  const deltaMs = Date.now() - date.getTime();
  if (deltaMs < 60_000) return "Just now";

  const minutes = Math.round(deltaMs / 60_000);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function formatTimestamp(value) {
  if (!value) return "No heartbeat";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString();
}

function AgentStatusBadge({ lastSeen }) {
  const isActive =
    lastSeen && Date.now() - new Date(lastSeen).getTime() <= ACTIVE_WINDOW_MS;

  return (
    <Badge variant={isActive ? "success" : "default"}>
      {isActive ? "Active" : "Idle"}
    </Badge>
  );
}

function SummaryStat({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-sre-border bg-sre-surface/70 p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-sre-text-muted">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold text-sre-text">{value}</div>
      <div className="mt-1 text-xs text-sre-text-muted">{hint}</div>
    </div>
  );
}

function AgentCard({ agent }) {
  const hostLabel =
    String(agent?.host_name || "").trim() ||
    String(agent?.attributes?.["host.name"] || "").trim() ||
    String(agent?.attributes?.["host.hostname"] || "").trim() ||
    "Unknown host";
  const signalLabel =
    Array.isArray(agent?.signals) && agent.signals.length > 0
      ? agent.signals.join(", ")
      : "No signal labels";

  return (
    <div className="rounded-2xl border border-sre-border bg-gradient-to-br from-sre-bg-alt to-sre-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-base font-semibold text-sre-text">
            {agent.name}
          </div>
          <div className="mt-1 text-xs text-sre-text-muted">{hostLabel}</div>
        </div>
        <AgentStatusBadge lastSeen={agent.last_seen} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-xl bg-sre-surface/80 p-3">
          <div className="text-[11px] uppercase tracking-wide text-sre-text-muted">
            Last pushed
          </div>
          <div className="mt-1 font-medium text-sre-text">
            {formatRelativeTime(agent.last_seen)}
          </div>
          <div className="mt-1 text-xs text-sre-text-muted">
            {formatTimestamp(agent.last_seen)}
          </div>
        </div>

        <div className="rounded-xl bg-sre-surface/80 p-3">
          <div className="text-[11px] uppercase tracking-wide text-sre-text-muted">
            Signals
          </div>
          <div className="mt-1 font-medium text-sre-text">{signalLabel}</div>
          <div className="mt-1 text-xs text-sre-text-muted">
            Tenant scope: {agent.tenant_id || "default"}
          </div>
        </div>
      </div>
    </div>
  );
}

AgentStatusBadge.propTypes = {
  lastSeen: PropTypes.string,
};

SummaryStat.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.string.isRequired,
  hint: PropTypes.string.isRequired,
};

AgentCard.propTypes = {
  agent: PropTypes.shape({
    id: PropTypes.string.isRequired,
    name: PropTypes.string.isRequired,
    tenant_id: PropTypes.string,
    host_name: PropTypes.string,
    last_seen: PropTypes.string,
    signals: PropTypes.arrayOf(PropTypes.string),
    attributes: PropTypes.object,
  }).isRequired,
};

export default function AgentsPage() {
  const { user } = useAuth();
  const activeApiKey = useMemo(() => resolveActiveApiKey(user), [user]);
  const activeTenantId = String(activeApiKey?.key || "").trim();
  const [agents, setAgents] = useState([]);
  const [activity, setActivity] = useState(null);
  const [volume, setVolume] = useState(VOLUME_DEFAULT);
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  const refresh = useCallback(() => {
    setRefreshTick((value) => value + 1);
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    (async () => {
      if (active) setLoading(true);
      try {
        const [agentsRes, activeRes, volumeRes] = await Promise.all([
          getAgents({ signal: controller.signal, maxRetries: 0 }),
          getActiveAgents({ signal: controller.signal, maxRetries: 0 }),
          getAgentMetricVolume({
            tenantId: activeTenantId,
            stepSeconds: 60,
            signal: controller.signal,
            maxRetries: 0,
          }),
        ]);

        if (!active) return;

        const knownAgents = Array.isArray(agentsRes) ? agentsRes : [];
        const scopedAgents = activeTenantId
          ? knownAgents.filter(
              (agent) => String(agent?.tenant_id || "").trim() === activeTenantId,
            )
          : knownAgents;

        const activityList = Array.isArray(activeRes) ? activeRes : [];
        const scopedActivity = activityList.find(
          (item) => String(item?.tenant_id || "").trim() === activeTenantId,
        );

        setAgents(scopedAgents);
        setActivity(scopedActivity || null);
        setVolume(
          volumeRes && typeof volumeRes === "object"
            ? volumeRes
            : VOLUME_DEFAULT,
        );
      } catch (_error) {
        if (!active) return;
        setAgents([]);
        setActivity(null);
        setVolume(VOLUME_DEFAULT);
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
      controller.abort();
    };
  }, [activeTenantId, refreshTick]);

  const activeAgents = agents.filter((agent) => {
    const lastSeen = new Date(agent?.last_seen || 0).getTime();
    return Number.isFinite(lastSeen) && Date.now() - lastSeen <= ACTIVE_WINDOW_MS;
  });
  const hasMetricActivity = Boolean(activity?.active || (activity?.metrics_count || 0) > 0);
  const latestHeartbeat = agents[0]?.last_seen || null;
  const hostCount = useMemo(() => {
    const hosts = new Set([
      ...agents
        .map((agent) => String(agent?.host_name || "").trim())
        .filter(Boolean),
      ...((activity?.host_names || [])
        .map((host) => String(host || "").trim())
        .filter(Boolean)),
    ]);
    return hosts.size;
  }, [activity?.host_names, agents]);
  const rawVolumePoints = Array.isArray(volume?.points)
    ? volume.points
        .map((point) => Number(point?.value || 0))
        .filter((value) => Number.isFinite(value))
    : [];
  const volumePoints =
    rawVolumePoints.length > 0
      ? rawVolumePoints
      : hasMetricActivity && (activity?.metrics_count || 0) > 0
        ? [activity.metrics_count, activity.metrics_count]
        : [];
  const activityCount = Number(activity?.metrics_count) || 0;
  const estimatedAgentCount = Number(activity?.agent_estimate) || 0;
  const estimatedHostCount = Number(activity?.host_estimate) || 0;
  const currentVolume = positiveOrFallback(volume?.current, activityCount);
  const peakVolume = positiveOrFallback(volume?.peak, currentVolume);
  const averageVolume = positiveOrFallback(volume?.average, currentVolume);
  const lastPushedValue = latestHeartbeat
    ? formatRelativeTime(latestHeartbeat)
    : hasMetricActivity
      ? "Metrics active"
      : "No heartbeat yet";
  const lastPushedHint = latestHeartbeat
    ? formatTimestamp(latestHeartbeat)
    : hasMetricActivity
      ? "Metric activity detected, but no heartbeat registry entry has arrived yet"
      : "No heartbeat";
  const resolvedActiveAgentCount =
    activeAgents.length > 0
      ? activeAgents.length
      : estimatedAgentCount > 0
        ? estimatedAgentCount
        : hasMetricActivity
          ? 1
          : 0;
  const resolvedHostCount =
    hostCount > 0
      ? hostCount
      : activity?.host_names?.length
        ? activity.host_names.length
        : estimatedHostCount > 0
          ? estimatedHostCount
        : hasMetricActivity
          ? 1
          : 0;
  const activeAgentsHint =
    hasMetricActivity && agents.length === 0
      ? estimatedAgentCount > 0
        ? `Estimated from metric labels: ${estimatedAgentCount.toLocaleString()} active metric source${estimatedAgentCount === 1 ? "" : "s"} (no heartbeat entries yet)`
        : "At least one agent is publishing metrics in this scope, but no heartbeat entries are registered yet"
      : `${agents.length.toLocaleString()} known in this scope`;
  const hostHint =
    activity?.host_names?.length
      ? `${activity.host_names.length} host names discovered by activity checks`
      : estimatedHostCount > 0
        ? `Estimated from metric labels: ${estimatedHostCount.toLocaleString()} host${estimatedHostCount === 1 ? "" : "s"} (heartbeat host details pending)`
      : hasMetricActivity && resolvedHostCount > 0
        ? "A metric source is active in this scope, but host details have not been reported yet"
        : "Heartbeat registry host names";

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Sidebar observability"
        title="Agents"
        subtitle="Track the currently selected API key scope with live heartbeats, metric-count trends, and the latest push details."
      >
        <Button type="button" variant="secondary" onClick={refresh}>
          Refresh
        </Button>
      </PageHeader>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)]">
        <Card
          title="Metric Volume"
          subtitle={
            activeApiKey?.name
              ? `Mimir metric count trend for ${activeApiKey.name}`
              : "Mimir metric count trend for the active scope"
          }
        >
          {loading ? (
            <div className="flex min-h-[220px] items-center justify-center">
              <Spinner size="md" />
            </div>
          ) : (
            <div>
              <div className="mb-4 overflow-hidden rounded-2xl border border-sre-border bg-gradient-to-r from-sre-primary/10 to-transparent p-4">
                <Sparkline
                  data={volumePoints}
                  width={480}
                  height={140}
                  stroke="rgb(var(--sre-primary-light-rgb))"
                  strokeWidth={2}
                  fill="rgb(var(--sre-primary-light-rgb) / 0.24)"
                  className="h-[140px] w-full"
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <SummaryStat
                  label="Current"
                  value={currentVolume.toLocaleString()}
                  hint="Latest sampled metric count"
                />
                <SummaryStat
                  label="Peak"
                  value={peakVolume.toLocaleString()}
                  hint="Highest sampled metric count"
                />
                <SummaryStat
                  label="Average"
                  value={averageVolume.toLocaleString()}
                  hint="Average metric count"
                />
              </div>
            </div>
          )}
        </Card>

        <Card
          title="Scope Snapshot"
          subtitle="Quick facts for the enabled API key"
        >
          {loading ? (
            <div className="flex min-h-[220px] items-center justify-center">
              <Spinner size="md" />
            </div>
          ) : (
            <div className="space-y-3">
              <SummaryStat
                label="Active agents"
                value={resolvedActiveAgentCount.toLocaleString()}
                hint={activeAgentsHint}
              />
              <SummaryStat
                label="Hosts"
                value={resolvedHostCount.toLocaleString()}
                hint={hostHint}
              />
              <SummaryStat
                label="Last pushed"
                value={lastPushedValue}
                hint={lastPushedHint}
              />
              <div className="rounded-xl border border-sre-border bg-sre-surface/70 p-4 text-sm text-sre-text-muted">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-sre-text">
                    {activeApiKey?.name || "No active API key"}
                  </span>
                  {activity ? (
                    <Badge variant={hasMetricActivity ? "success" : "default"}>
                      {hasMetricActivity ? "Metrics detected" : "No metrics detected"}
                    </Badge>
                  ) : null}
                </div>
                <div className="mt-2">
                  Metric names right now:{" "}
                  <span className="font-medium text-sre-text">
                    {(activity?.metrics_count || 0).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>

      <Card
        title="Known Agents"
        subtitle="Recent heartbeats for the enabled API key scope"
        className="mt-6"
      >
        {loading ? (
          <div className="flex min-h-[160px] items-center justify-center">
            <Spinner size="md" />
          </div>
        ) : agents.length === 0 ? (
          hasMetricActivity ? (
            <div className="rounded-2xl border border-sre-primary/30 bg-gradient-to-r from-sre-primary/10 to-transparent p-6 text-sm text-sre-text-muted">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-sre-text">
                  Metrics are active for this API key scope
                </span>
                <Badge variant="success">Heartbeat optional</Badge>
              </div>
              <div className="mt-2">
                The selected scope is publishing metric names in Mimir, but no
                heartbeat registry entries have arrived yet. OTEL export is
                working and the optional heartbeat endpoint may not be enabled
                for this agent process yet.
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-sre-border bg-sre-bg-alt p-6 text-sm text-sre-text-muted">
              No agents have pushed a heartbeat yet for this API key.
            </div>
          )
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {agents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
