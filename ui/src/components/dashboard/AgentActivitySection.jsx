import PropTypes from "prop-types";
import { Badge, Spinner } from "../ui";

const AgentStatusBadges = ({ agent }) => (
  <div className="flex shrink-0 items-center gap-2">
    {agent.is_enabled && <Badge variant="warning">Focused</Badge>}
    <Badge
      variant={agent.active ? "success" : "default"}
      className={`whitespace-nowrap ${agent.active ? "animate-pulse" : ""}`}
    >
      {agent.active ? "Active" : "Idle"}
    </Badge>
  </div>
);

AgentStatusBadges.propTypes = {
  agent: PropTypes.shape({
    is_enabled: PropTypes.bool,
    active: PropTypes.bool,
    clean: PropTypes.bool,
  }).isRequired,
};

const formatActivityLabel = (agent) => {
  if ((agent.metrics_count || 0) > 0) {
    return {
      hasMetrics: true,
      count: agent.metrics_count,
    };
  }
  return {
    hasMetrics: false,
    count: 0,
  };
};

const AgentCard = ({ agent }) => {
  const hostLabel =
    agent.host_names?.length > 0 ? agent.host_names.join(", ") : null;
  const activityLabel = formatActivityLabel(agent);

  const displayName =
    agent?.name && agent.name.length > 5
      ? agent.name.slice(0, 5) + "..."
      : agent?.name;

  return (
    <div className="rounded-lg border border-sre-border bg-sre-bg-alt px-4 py-3">
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-sre-text text-left">
            {displayName}
          </div>
          {activityLabel.hasMetrics ? (
            <div className="flex w-full items-center justify-start gap-1 whitespace-nowrap text-xs text-sre-text-muted text-left">
              <span>Metrics:</span>{" "}
              <span className="tabular-nums">{activityLabel.count}</span>
            </div>
          ) : (
            <div className="text-xs text-sre-text-muted text-left">
              No activity
            </div>
          )}
          {hostLabel && (
            <div className="text-xs text-sre-text-muted text-left">
              Host: {hostLabel}
            </div>
          )}
        </div>
        <AgentStatusBadges agent={agent} />
      </div>
    </div>
  );
};

AgentCard.propTypes = {
  agent: PropTypes.shape({
    name: PropTypes.string.isRequired,
    host_names: PropTypes.arrayOf(PropTypes.string),
    metrics_count: PropTypes.number,
    is_enabled: PropTypes.bool,
    active: PropTypes.bool,
    clean: PropTypes.bool,
  }).isRequired,
};

const AgentActivityContent = ({ loading, agents }) => {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sre-text-muted text-left">
        <Spinner size="sm" /> Loading activity
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="text-sm text-sre-text-muted text-left">
        No agent activity detected.
      </div>
    );
  }

  return (
    <div className="max-h-72 overflow-y-auto pr-2 space-y-3">
      {agents.map((agent) => (
        <AgentCard key={agent.name} agent={agent} />
      ))}
    </div>
  );
};

AgentActivityContent.propTypes = {
  loading: PropTypes.bool.isRequired,
  agents: PropTypes.array.isRequired,
};

export function AgentActivitySection({ loading, agents }) {
  return <AgentActivityContent loading={loading} agents={agents} />;
}
