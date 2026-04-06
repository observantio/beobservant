import { NavLink, useNavigate } from "react-router-dom";
import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import PropTypes from "prop-types";
import ThemeToggle from "./ThemeToggle";
import { Badge, Button, Input } from "./ui";
import ChangePasswordModal from "./ChangePasswordModal";
import * as api from "../api";
import { NAV_ITEMS } from "../utils/constants";
import { useLayoutMode } from "../contexts/LayoutModeContext";
import { useSharedIncidentSummary } from "../contexts/IncidentSummaryContext";
import { useToast } from "../contexts/ToastContext";
import { copyToClipboard } from "../utils/helpers";

const NAV_ITEM_LIST = Object.values(NAV_ITEMS);
const RELEASE_LABEL = "Wolfmegasaur v0.0.3";
const WATCHDOG_GITHUB_URL = "https://github.com/observantio/watchdog";
const OJO_REPO_URL = "https://github.com/observantio/ojo";
const OJO_RECOMMENDED_RELEASE_TAG = "v0.0.3";
const OJO_RELEASES_URL = `${OJO_REPO_URL}/releases/latest`;
const OJO_RECOMMENDED_RELEASE_URL = `${OJO_REPO_URL}/releases/tag/${OJO_RECOMMENDED_RELEASE_TAG}`;
const RELEASE_FETCH_TIMEOUT_MS = 8000;
const hasWindowsMarker = (name) => String(name || "").toLowerCase().includes("windows");

function getApiKeyColor(apiKeyId) {
  if (!apiKeyId) return "hsl(220, 25%, 65%)";
  let hash = 0;
  for (let i = 0; i < apiKeyId.length; i += 1) {
    hash = apiKeyId.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;

  let lightness = 52;
  let saturation = 62;
  if (typeof document !== "undefined") {
    const theme =
      document.documentElement.getAttribute("data-theme") ||
      document.body.getAttribute("data-theme") ||
      "light";
    if (theme === "dark") {
      lightness = 72;
      saturation = 60;
    } else {
      lightness = 42;
      saturation = 70;
    }
  }

  return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
}
const OJO_OS_OPTIONS = [
  { key: "linux", label: "Linux", icon: "terminal" },
  { key: "windows", label: "Windows", icon: "desktop_windows" },
  { key: "extras", label: "Extra services", icon: "extension" },
];

const OJO_EXTRA_SERVICES = [
  {
    key: "docker",
    label: "Docker",
    icon: "inventory_2",
    packageName: "ojo-docker",
    configFile: "docker.yaml",
    keywords: ["containers", "docker", "runtime", "sidecar"],
    description: "Container runtime inventory, CPU, memory, network, and block IO metrics.",
  },
  {
    key: "gpu",
    label: "GPU",
    icon: "memory",
    packageName: "ojo-gpu",
    configFile: "gpu.yaml",
    keywords: ["gpu", "nvidia", "accelerator", "cuda"],
    description: "GPU utilization, temperature, memory, and power telemetry.",
  },
  {
    key: "sensors",
    label: "Sensors",
    icon: "device_thermostat",
    packageName: "ojo-sensors",
    configFile: "sensors.yaml",
    keywords: ["hardware", "sensors", "temperature", "fans", "voltages"],
    description: "Board sensors, temperatures, fan speeds, and voltage readings.",
  },
  {
    key: "postgres",
    label: "Postgres",
    icon: "storage",
    packageName: "ojo-postgres",
    configFile: "postgres.yaml",
    keywords: ["postgres", "postgresql", "database", "sql"],
    description: "Postgres availability, connection, transaction, and block metrics.",
  },
  {
    key: "mysql",
    label: "MySQL",
    icon: "database",
    packageName: "ojo-mysql",
    configFile: "mysql.yaml",
    keywords: ["mysql", "database", "sql", "mariadb"],
    description: "MySQL availability, connection, query rate, and throughput metrics.",
  },
];

function buildMinimalCollectorConfig(os = "linux", instanceId = "") {
  const normalizedOs = String(os || "linux").trim().toLowerCase();
  const runtimeOs =
    normalizedOs === "windows" || normalizedOs === "solaris"
      ? normalizedOs
      : "linux";
  const resolvedInstanceId =
    String(instanceId || "").trim() || `${runtimeOs}-${Math.random().toString(36).slice(2, 8)}`;
  return `service:
  name: ${runtimeOs}
  instance_id: ${resolvedInstanceId}

collection:
  poll_interval_secs: 5
  include_process_metrics: true
  process_include_pid_label: true
  process_include_command_label: true
  process_include_state_label: true

export:
  otlp:
    endpoint: "http://<ip of the otel collector>:4355/v1/metrics"
    protocol: http/protobuf
    timeout_secs: 10
  batch:
    interval_secs: 5
    timeout_secs: 10

# Optional metric selector. If omitted, Ojo exports all metrics.
# Rules:
# - include/exclude are prefix-based
# - exclude wins over include
# - include omitted/empty means include all
# Example:
# metrics:
#   include: [system., process.]
#   exclude: [process.linux.]
`;
}

export function NavItem({
  item,
  isMobile = false,
  incidentSummary = null,
  variant = "top",
}) {
  const baseClasses =
    variant === "sidebar"
      ? "w-full rounded-lg text-[14px] font-normal flex items-center gap-2.5 transition-colors px-3 py-2.5"
      : isMobile
        ? "rounded-lg text-xs font-medium whitespace-nowrap flex items-center gap-2 transition-all px-3 py-1.5 border border-transparent"
        : "px-3 py-2 text-sm font-medium transition-all duration-200 flex items-center gap-2 border-b-2 border-transparent min-w-0";
  const incidentsWithBadges = item.path === "/incidents" && incidentSummary;
  const classesWithBadges = incidentsWithBadges
    ? `${baseClasses} relative pr-7`
    : baseClasses;
  const activeClasses =
    variant === "sidebar"
      ? "text-black bg-sre-primary/10 dark:text-sre-success dark:bg-sre-success/10"
      : isMobile
        ? "text-sre-primary bg-sre-primary/10 border-sre-primary/50"
        : "text-sre-primary border-sre-primary bg-sre-primary/5";
  const inactiveClasses =
    variant === "sidebar"
      ? "text-black dark:text-sre-text-muted hover:text-black dark:hover:text-sre-text hover:bg-sre-surface-light/60"
      : isMobile
        ? "text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light hover:border-sre-border/70"
        : "text-sre-text-muted hover:text-sre-text hover:border-sre-border";

  return (
    <NavLink
      to={item.path}
      className={({ isActive }) =>
        `${classesWithBadges} ${
          isActive ? activeClasses : inactiveClasses
        }`
      }
    >
      {variant === "sidebar" && (
        <span
          className="material-icons leading-none text-[17px]"
          aria-hidden
        >
          {item.icon}
        </span>
      )}
      {variant === "sidebar" && " "}
      <span
        className={
          variant === "sidebar"
            ? "truncate"
            : "truncate whitespace-nowrap text-left"
        }
        style={{ maxWidth: "11rem" }}
        title={item.label}
      >
        {item.label}
      </span>
      {incidentsWithBadges && (
        <span className="pointer-events-none absolute right-0 top-0 flex items-center gap-1">
          {(incidentSummary.assigned_to_me_open || 0) > 0 && (
            <span
              className="inline-flex h-6 items-center justify-center rounded-full border border-sre-border bg-sre-surface text-emerald-400 text-[10px] font-semibold px-1 shadow-sm"
              title="Assigned to me"
            >
              {incidentSummary.assigned_to_me_open}
            </span>
          )}
        </span>
      )}
    </NavLink>
  );
}

NavItem.propTypes = {
  item: PropTypes.shape({
    label: PropTypes.string.isRequired,
    icon: PropTypes.string.isRequired,
    path: PropTypes.string.isRequired,
    topNavHidden: PropTypes.bool,
  }).isRequired,
  isMobile: PropTypes.bool,
  variant: PropTypes.oneOf(["top", "sidebar"]),
  incidentSummary: PropTypes.shape({
    open_total: PropTypes.number,
    unassigned_open: PropTypes.number,
    assigned_to_me_open: PropTypes.number,
  }),
};

function ApiKeyDropdown({
  apiKeys,
  activeKeyId,
  onSelect,
  disabled,
  compact = false,
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selectableKeys = apiKeys.filter(
    (k) => (!k.is_shared || k.can_use) && !k.is_hidden,
  );

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  const selectedKey = selectableKeys?.find((k) => k.id === activeKeyId);
  const btnClass = compact
    ? "px-2 py-1 text-xs bg-sre-surface border border-sre-border rounded text-sre-text flex items-center justify-between"
    : "px-3 py-2 min-w-[190px] text-xs bg-sre-surface border border-sre-border rounded text-sre-text flex items-center justify-between";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        className={btnClass}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span
          className="truncate"
          style={{
            maxWidth: "70px",
            color: getApiKeyColor(selectedKey?.id),
          }}
        >
          {selectedKey?.name || (compact ? "Select" : "Select API Key")}
        </span>
        <svg
          className={`${compact ? "w-3 h-3" : "w-4 h-4"} text-sre-text-muted`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 011.08 1.04l-4.25 4.25a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute top-full mt-1 w-full bg-sre-bg-card border border-sre-border rounded shadow-lg z-50 py-1 max-h-60 overflow-y-auto"
        >
          {selectableKeys.map((k) => (
            <li key={k.id} role="option" aria-selected={k.id === activeKeyId}>
              <button
                type="button"
                onClick={() => {
                  onSelect(k.id);
                  setOpen(false);
                }}
                className={`w-full text-left ${compact ? "px-2 py-1" : "px-3 py-2"} text-xs ${
                  k.id === activeKeyId ? "font-semibold" : ""
                } text-sre-text hover:bg-sre-surface/50`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="truncate block"
                    style={{
                      maxWidth: "70px",
                      color: getApiKeyColor(k.id),
                    }}
                  >
                    {k.name}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

ApiKeyDropdown.propTypes = {
  apiKeys: PropTypes.array.isRequired,
  activeKeyId: PropTypes.string,
  onSelect: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
  compact: PropTypes.bool,
};

function QuickCreateApiKeyButton({ onCreated }) {
  const toast = useToast();
  const panelRef = useRef(null);
  const triggerRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdToken, setCreatedToken] = useState("");

  useEffect(() => {
    if (!createdToken) return undefined;
    const timeoutId = window.setTimeout(() => {
      setCreatedToken("");
    }, 30000);
    return () => window.clearTimeout(timeoutId);
  }, [createdToken]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event) => {
      const target = event.target;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const trimmed = String(name || "").trim();
    if (!trimmed || creating) return;
    setCreating(true);
    try {
      const created = await api.createApiKey({ name: trimmed });
      if (created?.id) {
        await api.updateApiKey(created.id, { is_enabled: true });
      }
      await onCreated?.(created);
      setName("");
      setCreatedToken(String(created?.otlp_token || "").trim());
      setOpen(true);
      toast.success("API key created");
    } catch (err) {
      toast.error(err?.body?.detail || err?.message || "Failed to create API key");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="relative hidden sm:block">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="group inline-flex h-9 w-9 items-center justify-center rounded-xl border border-sre-border bg-sre-surface/60 text-sre-text-muted backdrop-blur-md transition-all hover:-translate-y-0.5 hover:border-sre-primary/50 hover:bg-sre-surface/80 hover:text-sre-text"
        aria-label="Quick create API key"
        title="Quick create API key"
      >
        <span className="material-icons text-[18px] leading-none">key</span>
        <span className="pointer-events-none absolute -right-0.5 -top-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-sre-primary text-white shadow-sm">
          <span className="material-icons text-[11px] leading-none">add</span>
        </span>
      </button>

      {open && (
        <div
          ref={panelRef}
          className="absolute right-0 top-full z-[70] mt-2 w-[18rem] rounded-2xl border border-sre-border bg-sre-bg-card/95 p-3 shadow-2xl backdrop-blur-xl"
        >
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-sre-primary/10 text-sre-primary">
                  <span className="material-icons text-[16px] leading-none">
                    key
                  </span>
                </span>
                <div>
                  <div className="text-sm font-semibold text-sre-text">
                    Quick Create
                  </div>
                  <div className="text-[11px] text-sre-text-muted">
                    Make a new key and switch to it
                  </div>
                </div>
              </div>
            </div>

            <Input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Production Team"
              className="text-sm"
            />

            {createdToken ? (
              <div className="rounded-xl border border-sre-primary/30 bg-sre-primary/10 p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-sre-primary">
                    This is OTLP token
                  </div>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(createdToken)}
                    className="rounded-md border border-sre-border px-2 py-0.5 text-[11px] font-medium text-sre-text hover:border-sre-primary/40"
                  >
                    Copy
                  </button>
                </div>
                <div className="mt-1.5 break-all rounded-md bg-sre-bg px-2 py-1.5 font-mono text-[11px] text-sre-text">
                  {createdToken}
                </div>
                <div className="mt-1 text-[10px] text-sre-text-muted">
                  Visible temporarily for 30 seconds.
                </div>
              </div>
            ) : null}

            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-xs font-medium text-sre-text-muted transition-colors hover:text-sre-text"
              >
                Cancel
              </button>
              <Button
                type="submit"
                size="sm"
                loading={creating}
                disabled={!String(name || "").trim()}
                className="rounded-xl px-3"
              >
                <span className="material-icons mr-1 text-[15px] leading-none">
                  auto_awesome
                </span>
                Create
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

QuickCreateApiKeyButton.propTypes = {
  onCreated: PropTypes.func,
};

function QuickMetricsQueryButton({ apiKeys = [] }) {
  const toast = useToast();
  const panelRef = useRef(null);
  const triggerRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedKeyId, setSelectedKeyId] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [resultMeta, setResultMeta] = useState(null);

  const selectableKeys = apiKeys.filter(
    (key) => (!key.is_shared || key.can_use) && !key.is_hidden,
  );

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event) => {
      const target = event.target;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!selectableKeys.length) {
      setSelectedKeyId("");
      return;
    }
    const enabledKey = selectableKeys.find((key) => key.is_enabled);
    const fallbackKey = enabledKey || selectableKeys[0];
    setSelectedKeyId((current) => {
      if (current && selectableKeys.some((key) => key.id === current)) {
        return current;
      }
      return fallbackKey?.id || "";
    });
  }, [selectableKeys]);

  const selectedKey = selectableKeys.find((key) => key.id === selectedKeyId);
  const formattedResult = result ? JSON.stringify(result, null, 2) : "";

  const handleSubmit = async (event) => {
    event.preventDefault();
    const trimmedQuery = String(query || "").trim();
    const scope = String(selectedKey?.key || "").trim();
    if (!trimmedQuery || !scope || loading) return;

    setLoading(true);
    try {
      const response = await api.evaluatePromql(trimmedQuery, scope, {
        sampleLimit: 20,
      });
      setResult(response);
      setResultMeta({
        keyName: selectedKey?.name || scope,
        executedAt: new Date().toLocaleTimeString(),
      });
    } catch (err) {
      setResult(null);
      setResultMeta(null);
      toast.error(err?.body?.detail || err?.message || "Metric query failed");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!formattedResult) return;
    const ok = await copyToClipboard(formattedResult);
    if (ok) toast.success("JSON copied");
    else toast.error("Failed to copy JSON");
  };

  return (
    <div className="relative hidden sm:block">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="group inline-flex h-9 w-9 items-center justify-center rounded-xl border border-sre-border bg-sre-surface/60 text-sre-text-muted backdrop-blur-md transition-all hover:-translate-y-0.5 hover:border-sre-primary/50 hover:bg-sre-surface/80 hover:text-sre-text disabled:cursor-not-allowed disabled:opacity-50"
        aria-label="Quick query metrics"
        title="Quick query metrics"
        disabled={selectableKeys.length === 0}
      >
        <span className="material-icons text-[18px] leading-none">query_stats</span>
      </button>

      {open && (
        <div
          ref={panelRef}
          className="absolute right-0 top-full z-[70] mt-2 w-[28rem] rounded-2xl border border-sre-border bg-sre-bg-card/95 p-4 shadow-2xl backdrop-blur-xl"
        >
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-sre-primary/10 text-sre-primary">
                <span className="material-icons text-[18px] leading-none">
                  query_stats
                </span>
              </span>
              <div>
                <div className="text-sm font-semibold text-sre-text">
                  Quick Metrics Query
                </div>
                <div className="text-[11px] text-sre-text-muted">
                  Run a PromQL query against one API key scope and inspect raw JSON.
                </div>
              </div>
            </div>

            <div className="space-y-1">
              <label
                htmlFor="quick-metrics-key"
                className="text-xs font-medium text-sre-text"
              >
                API Key Scope
              </label>
              <select
                id="quick-metrics-key"
                value={selectedKeyId}
                onChange={(event) => setSelectedKeyId(event.target.value)}
                className="w-full rounded-xl border border-sre-border bg-sre-surface px-3 py-2 text-sm text-sre-text focus:border-sre-primary focus:outline-none focus:ring-1 focus:ring-sre-primary"
              >
                {selectableKeys.map((key) => (
                  <option key={key.id} value={key.id}>
                    {key.name}
                  </option>
                ))}
              </select>
            </div>

            <Input
              label="PromQL Query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder='sum(rate(http_requests_total[5m]))'
              className="text-sm"
            />

            <div className="rounded-xl border border-sre-border bg-sre-surface/70 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-medium text-sre-text">JSON Result</div>
                  <div className="text-[11px] text-sre-text-muted">
                    {resultMeta
                      ? `${resultMeta.keyName} at ${resultMeta.executedAt}`
                      : "Results stay local to this quick query panel"}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleCopy}
                  disabled={!formattedResult}
                  className="text-xs font-medium text-sre-text-muted transition-colors hover:text-sre-text disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Copy JSON
                </button>
              </div>
              <pre className="max-h-72 overflow-auto rounded-xl bg-sre-bg px-3 py-3 text-xs leading-5 text-sre-text">
                {formattedResult || "{\n  \"status\": \"ready\",\n  \"message\": \"Run a query to inspect JSON output.\"\n}"}
              </pre>
            </div>

            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] text-sre-text-muted">
                Tip: use this for quick validation before saving dashboards or rules.
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="text-xs font-medium text-sre-text-muted transition-colors hover:text-sre-text"
                >
                  Close
                </button>
                <Button
                  type="submit"
                  size="sm"
                  loading={loading}
                  disabled={!String(query || "").trim() || !selectedKey}
                  className="rounded-xl px-3"
                >
                  <span className="material-icons mr-1 text-[15px] leading-none">
                    play_arrow
                  </span>
                  Run
                </Button>
              </div>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

QuickMetricsQueryButton.propTypes = {
  apiKeys: PropTypes.array,
};

export default function Header() {
  const { user, logout, hasPermission, refreshUser } = useAuth();
  const { sidebarMode, toggleSidebarMode } = useLayoutMode();
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [showOjoWizard, setShowOjoWizard] = useState(false);
  const [activeKeyId, setActiveKeyId] = useState("");
  const [switchingKey, setSwitchingKey] = useState(false);
  const incidentSummary = useSharedIncidentSummary();

  const visibleApiKeys = (user?.api_keys || []).filter(
    (k) => (!k.is_shared || k.can_use) && !k.is_hidden,
  );

  useEffect(() => {
    if (!visibleApiKeys.length) {
      setActiveKeyId("");
      return;
    }
    const enabledKey = visibleApiKeys.find((k) => k.is_enabled);
    setActiveKeyId(enabledKey?.id || "");
  }, [visibleApiKeys]);

  const handleActiveKeyChange = useCallback(
    async (nextId) => {
      if (!nextId || nextId === activeKeyId) return;
      setActiveKeyId(nextId);
      setSwitchingKey(true);
      try {
        await api.updateApiKey(nextId, { is_enabled: true });
        await refreshUser();
      } catch (err) {
        await refreshUser();
      } finally {
        setSwitchingKey(false);
      }
    },
    [activeKeyId, refreshUser],
  );

  const visibleNavItems = NAV_ITEM_LIST.filter(
    (item) =>
      (!item.permission || hasPermission(item.permission)) &&
      !(item.topNavHidden && !sidebarMode),
  );

  const headerBarClass = sidebarMode
    ? "sticky top-0 z-50 border-b-0 shadow-none bg-transparent"
    : "sticky top-0 z-50 border-b-2 border-dashed border-sre-border shadow-none bg-sre-surface/80 backdrop-blur-xl";

  const mobileNavClass = sidebarMode
    ? "md:hidden border-t-0 bg-transparent px-3 py-2 flex gap-2 overflow-x-auto"
    : "md:hidden border-t border-sre-border px-4 py-2 flex gap-2 overflow-x-auto";

  const actionsCluster = (
    <div
      className={`flex items-center justify-end ${sidebarMode ? "gap-1.5" : "gap-3"}`}
    >
      {sidebarMode && (
        <div className="hidden lg:flex items-center gap-2">
          <span className="inline-flex items-center rounded-md border border-sre-border bg-sre-surface px-2 py-1 text-[11px] font-semibold text-sre-text-muted">
            {RELEASE_LABEL}
          </span>
          <a
            href={WATCHDOG_GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center rounded-md border border-sre-border bg-sre-surface px-2 py-1 text-[11px] font-semibold text-sre-text-muted transition-colors hover:border-sre-primary/50 hover:text-sre-text"
          >
            GitHub
          </a>
          <button
            type="button"
            onClick={() => setShowOjoWizard(true)}
            className="inline-flex items-center rounded-md border border-sre-border bg-sre-surface px-2 py-1 text-[11px] font-semibold text-sre-text-muted transition-colors hover:border-sre-primary/50 hover:text-sre-text"
          >
            Download Ojo Agent
          </button>
        </div>
      )}

      <ThemeToggle
        className={
          sidebarMode
            ? "rounded-lg border border-sre-border p-1.5 hover:bg-sre-surface-light/70"
            : ""
        }
      />

      {visibleApiKeys.length > 0 && (
        <div className="hidden sm:flex items-center gap-2">
          <ApiKeyDropdown
            apiKeys={visibleApiKeys}
            activeKeyId={activeKeyId}
            onSelect={handleActiveKeyChange}
            disabled={switchingKey}
          />
          {sidebarMode && <QuickMetricsQueryButton apiKeys={visibleApiKeys} />}
          {sidebarMode && <QuickCreateApiKeyButton onCreated={refreshUser} />}
        </div>
      )}

      <div className="relative">
        <UserMenu
          user={user}
          logout={logout}
          hasPermission={hasPermission}
          openChangePassword={() => setShowChangePassword(true)}
          compact={sidebarMode}
        />
        <ChangePasswordModal
          isOpen={showChangePassword}
          onClose={() => setShowChangePassword(false)}
          userId={user?.id}
        />
      </div>
    </div>
  );

  return (
    <header className={headerBarClass}>
      {sidebarMode ? (
        <div className="flex h-16 w-full items-center justify-between gap-2 pr-3 sm:pr-5 lg:pr-8 md:justify-end">
          <button
            type="button"
            onClick={toggleSidebarMode}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-sre-text-muted transition-colors hover:bg-sre-surface-light/80 hover:text-sre-text md:hidden"
            aria-pressed={sidebarMode}
            aria-label="Use top navigation layout"
            title="Top navigation"
          >
            <span className="material-icons text-[22px] leading-none" aria-hidden>
              view_headline
            </span>
          </button>
          {actionsCluster}
        </div>
      ) : (
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 min-h-16 items-center gap-3">
            <button
              type="button"
              onClick={toggleSidebarMode}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-sre-text-muted transition-colors hover:bg-sre-surface-light/80 hover:text-sre-text md:hidden"
              aria-pressed={sidebarMode}
              aria-label="Use sidebar navigation layout"
              title="Sidebar navigation & dashboard grid"
            >
              <span className="material-icons text-[22px] leading-none" aria-hidden>
                dock_to_left
              </span>
            </button>
            <button
              type="button"
              onClick={toggleSidebarMode}
              className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-lg text-sre-text-muted transition-colors hover:bg-sre-surface-light/80 hover:text-sre-text md:flex"
              aria-pressed={sidebarMode}
              aria-label="Use sidebar navigation layout"
              title="Sidebar navigation & dashboard grid"
            >
              <span className="material-icons text-[22px] leading-none" aria-hidden>
                dock_to_left
              </span>
            </button>
            <div className="flex min-h-16 min-w-0 flex-1 items-center justify-end gap-4 md:justify-between">
              <nav
                className="hidden min-w-0 flex-1 items-center justify-start gap-0.5 overflow-x-auto md:flex"
                aria-label="Main navigation"
              >
                {visibleNavItems.map((item) => (
                  <NavItem
                    key={item.path}
                    item={item}
                    incidentSummary={incidentSummary}
                  />
                ))}
              </nav>
              {actionsCluster}
            </div>
          </div>
        </div>
      )}

      {/* Mobile Navigation */}
      <div className={mobileNavClass}>
        {visibleNavItems.map((item) => (
          <NavItem
            key={item.path}
            item={item}
            isMobile
            incidentSummary={incidentSummary}
          />
        ))}
        {visibleApiKeys.length > 0 && (
          <div className="flex items-center gap-2 ml-auto">
            <ApiKeyDropdown
              apiKeys={visibleApiKeys}
              activeKeyId={activeKeyId}
              onSelect={handleActiveKeyChange}
              disabled={switchingKey}
              compact
            />
          </div>
        )}
      </div>
      <OjoAgentWizardModal
        open={showOjoWizard}
        onClose={() => setShowOjoWizard(false)}
        apiKeys={visibleApiKeys}
        onRefreshKeys={refreshUser}
      />
    </header>
  );
}

function OjoAgentWizardModal({ open, onClose, apiKeys = [], onRefreshKeys }) {
  const toast = useToast();
  const wasOpenRef = useRef(false);
  const [step, setStep] = useState(0);
  const [selectedOs, setSelectedOs] = useState("linux");
  const [selectedExtraServiceKey, setSelectedExtraServiceKey] = useState("docker");
  const [extraServiceSearch, setExtraServiceSearch] = useState("");
  const [instanceIdSuffix, setInstanceIdSuffix] = useState("");
  const [selectedApiKeyId, setSelectedApiKeyId] = useState("");
  const [fetchedApiKeys, setFetchedApiKeys] = useState([]);
  const [apiKeyTokenMap, setApiKeyTokenMap] = useState({});
  const [tokenRegenerating, setTokenRegenerating] = useState(false);
  const [tokenRegenerateError, setTokenRegenerateError] = useState("");
  const [newApiKeyName, setNewApiKeyName] = useState("");
  const [creatingApiKey, setCreatingApiKey] = useState(false);
  const [apiKeyCreateMessage, setApiKeyCreateMessage] = useState("");
  const [selectedAssetUrl, setSelectedAssetUrl] = useState("");
  const [releaseData, setReleaseData] = useState(null);
  const [releasesList, setReleasesList] = useState([]);
  const [releaseFetched, setReleaseFetched] = useState(false);
  const [loadingRelease, setLoadingRelease] = useState(false);
  const [releaseError, setReleaseError] = useState("");
  const [connectStatus, setConnectStatus] = useState("idle");
  const [connectMessage, setConnectMessage] = useState("");
  const effectiveApiKeys = fetchedApiKeys.length ? fetchedApiKeys : apiKeys;

  useEffect(() => {
    if (!open) {
      wasOpenRef.current = false;
      return;
    }
    if (wasOpenRef.current) return;
    wasOpenRef.current = true;
    if (!apiKeys.length) {
      setSelectedApiKeyId("");
    } else {
      const enabled = apiKeys.find((k) => k.is_enabled);
      setSelectedApiKeyId(enabled?.id || apiKeys[0]?.id || "");
    }
    setStep(0);
    setSelectedOs("linux");
    setSelectedExtraServiceKey("docker");
    setExtraServiceSearch("");
    setConnectStatus("idle");
    setConnectMessage("");
    setReleaseFetched(false);
    setReleaseError("");
    setReleaseData(null);
    setReleasesList([]);
    setSelectedAssetUrl("");
    setInstanceIdSuffix((prev) => prev || Math.random().toString(36).slice(2, 8));
    setNewApiKeyName("");
    setCreatingApiKey(false);
    setApiKeyCreateMessage("");
    setApiKeyTokenMap({});
    setFetchedApiKeys([]);
    setTokenRegenerating(false);
    setTokenRegenerateError("");
  }, [apiKeys, open]);

  useEffect(() => {
    if (!open) return;
    let active = true;
    (async () => {
      try {
        const keys = await api.listApiKeys();
        if (!active) return;
        setFetchedApiKeys(Array.isArray(keys) ? keys : []);
      } catch {
        if (!active) return;
        setFetchedApiKeys([]);
      }
    })();
    return () => {
      active = false;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (!effectiveApiKeys.length) {
      setSelectedApiKeyId("");
      return;
    }
    const hasSelected = effectiveApiKeys.some((k) => k.id === selectedApiKeyId);
    if (hasSelected) return;
    const enabled = effectiveApiKeys.find((k) => k.is_enabled);
    setSelectedApiKeyId(enabled?.id || effectiveApiKeys[0]?.id || "");
  }, [open, effectiveApiKeys, selectedApiKeyId]);

  useEffect(() => {
    if (!open) return;
    setApiKeyTokenMap((prev) => {
      const next = { ...prev };
      (effectiveApiKeys || []).forEach((key) => {
        const id = String(key?.id || "").trim();
        const token = String(key?.otlp_token || "").trim();
        if (id && token) next[id] = token;
      });
      return next;
    });
  }, [open, effectiveApiKeys]);

  useEffect(() => {
    if (!open || releaseFetched) {
      return;
    }
    let active = true;
    const timeoutId = setTimeout(() => {
      if (active) {
        setLoadingRelease(false);
        setReleaseFetched(true);
        setReleaseError("Release request timed out. Showing manual links instead.");
      }
    }, RELEASE_FETCH_TIMEOUT_MS);
    (async () => {
      setLoadingRelease(true);
      setReleaseError("");
      try {
        const payload = await api.getOjoReleases({ maxRetries: 0 });
        if (active) {
          const latest = payload?.latest;
          const releases = payload?.releases;
          setReleaseData(latest && typeof latest === "object" ? latest : {});
          setReleasesList(Array.isArray(releases) ? releases : []);
        }
      } catch (err) {
        if (!active) return;
        setReleaseError(
          err?.message || "Unable to load release metadata",
        );
        setReleasesList([]);
      } finally {
        if (active) {
          setLoadingRelease(false);
          setReleaseFetched(true);
        }
        clearTimeout(timeoutId);
      }
    })();
    return () => {
      active = false;
      clearTimeout(timeoutId);
    };
  }, [open, releaseFetched]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const assets = Array.isArray(releaseData?.assets) ? releaseData.assets : [];
  const filteredExtraServices = OJO_EXTRA_SERVICES.filter((service) => {
    const token = String(extraServiceSearch || "").trim().toLowerCase();
    if (!token) return true;
    return [service.label, service.packageName, service.description, ...(service.keywords || [])]
      .join(" ")
      .toLowerCase()
      .includes(token);
  });
  const selectedExtraService =
    OJO_EXTRA_SERVICES.find((service) => service.key === selectedExtraServiceKey) ||
    OJO_EXTRA_SERVICES[0];
  const osAssets = assets.filter((asset) => {
    const name = String(asset?.name || "").toLowerCase();
    if (!name) return false;

    if (selectedOs === "extras") {
      const packageName = String(selectedExtraService?.packageName || "").toLowerCase();
      const serviceKey = String(selectedExtraService?.key || "").toLowerCase();
      return (
        (!!packageName && name.includes(packageName)) ||
        (!!serviceKey && name.includes(serviceKey))
      );
    }

    if (selectedOs === "linux") {
      const isLinux = name.includes("linux");
      const isWindows = hasWindowsMarker(name);
      const isSolaris = name.includes("solaris") || name.includes("sunos");
      return isLinux && !isWindows && !isSolaris;
    }

    if (selectedOs === "windows") {
      return (
        hasWindowsMarker(name) &&
        !name.includes("linux") &&
        !name.includes("solaris")
      );
    }

    if (selectedOs === "solaris") {
      return (
        (name.includes("solaris") || name.includes("sunos") || name.includes("sparc")) &&
        !name.includes("windows") &&
        !name.includes("linux")
      );
    }

    return name.includes("container") || name.includes("docker") || name.includes("oci");
  });
  const selectedAsset =
    osAssets.find(
      (asset) =>
        String(asset?.browser_download_url || "") ===
        String(selectedAssetUrl || ""),
    ) || osAssets[0] || null;
  const binaryUrlPlaceholder = selectedOs === "windows"
    ? `${OJO_REPO_URL}/releases/download/${OJO_RECOMMENDED_RELEASE_TAG}/ojo-${OJO_RECOMMENDED_RELEASE_TAG}-windows-x86_64.exe`
    : selectedOs === "linux"
      ? `${OJO_REPO_URL}/releases/download/${OJO_RECOMMENDED_RELEASE_TAG}/ojo-${OJO_RECOMMENDED_RELEASE_TAG}-linux-x86_64`
      : "<binary-url-from-release>";
  const resolvedBinaryUrl =
    String(selectedAsset?.browser_download_url || "").trim() || binaryUrlPlaceholder;
  const selectedApiKey = effectiveApiKeys.find((k) => k.id === selectedApiKeyId);
  const runtimeOsName =
    selectedOs === "windows" || selectedOs === "solaris" ? selectedOs : "linux";
  const generatedInstanceId = `${runtimeOsName}-${instanceIdSuffix || "xxxxxx"}`;
  const configFileByOs = {
    linux: "linux.yaml",
    windows: "windows.yaml",
    solaris: "solaris.yaml",
    containers: "collector.yaml",
  };
  const selectedConfigFile =
    selectedOs === "extras"
      ? selectedExtraService?.configFile || "service.yaml"
      : configFileByOs[selectedOs] || "collector.yaml";

  const generatedConfig = buildMinimalCollectorConfig(selectedOs, generatedInstanceId);
  const selectedToken = String(
    apiKeyTokenMap[selectedApiKeyId] || selectedApiKey?.otlp_token || "",
  ).trim();
  const otelIngestConfig = `receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4355

processors:
  batch:
    timeout: 10s

exporters:
  prometheusremotewrite/mimir:
    endpoint: "http://<mimir-host>:9009/api/v1/push"
    headers:
      x-otlp-token: "${selectedToken || "<api-key-token>"}"

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheusremotewrite/mimir]`;

  const installCommandByOs = {
    linux: `curl -L ${resolvedBinaryUrl} -o ojo
chmod +x ojo
sudo mv ojo /usr/local/bin/ojo
ojo --config linux.yaml`,
    windows: `Invoke-WebRequest ${resolvedBinaryUrl} -OutFile .\\ojo.exe
.\\ojo.exe --config windows.yaml`,
    solaris: `curl -L ${resolvedBinaryUrl} -o ojo
chmod +x ojo
./ojo --config solaris.yaml`,
    containers: `docker run -d --name ojo-agent \\
  -v $(pwd)/otel-agent.yaml:/etc/otelcol/config.yaml \\
  observantio/ojo:latest`,
  };
  const extraInstallCommand = `curl -L ${resolvedBinaryUrl} -o ${selectedExtraService?.packageName || "ojo-service"}
chmod +x ${selectedExtraService?.packageName || "ojo-service"}
sudo mv ${selectedExtraService?.packageName || "ojo-service"} /usr/local/bin/${selectedExtraService?.packageName || "ojo-service"}
${selectedExtraService?.packageName || "ojo-service"} --config ${selectedConfigFile}`;
  const fallbackReleaseLinks = [
    { name: "Latest release", url: OJO_RELEASES_URL },
    { name: `Recommended ${OJO_RECOMMENDED_RELEASE_TAG}`, url: OJO_RECOMMENDED_RELEASE_URL },
    { name: "All releases", url: "https://github.com/observantio/ojo/releases" },
    { name: "Tags", url: "https://github.com/observantio/ojo/tags" },
  ];
  const releaseTitleText = loadingRelease && !releaseData
    ? "Loading..."
    : releaseData?.name || releaseData?.tag_name || `${OJO_RECOMMENDED_RELEASE_TAG} (recommended)`;

  const runConnectionCheck = async (waitUntilConnected = false) => {
    setConnectStatus("checking");
    setConnectMessage(
      waitUntilConnected
        ? "Waiting for agent to appear..."
        : "Checking agent connectivity...",
    );
    const selectedApiScope = String(selectedApiKey?.key || "").trim();
    let attempts = 0;
    while (attempts < (waitUntilConnected ? 12 : 1)) {
      attempts += 1;
      try {
        const [knownRes, activeRes] = await Promise.all([
          api.getAgents({ maxRetries: 0 }),
          api.getActiveAgents({ maxRetries: 0 }),
        ]);
        const knownAgents = Array.isArray(knownRes) ? knownRes : [];
        const scopedAgents = selectedApiScope
          ? knownAgents.filter(
              (agent) => String(agent?.tenant_id || "").trim() === selectedApiScope,
            )
          : knownAgents;
        const activeScopes = Array.isArray(activeRes) ? activeRes : [];
        const scopedActivity = selectedApiScope
          ? activeScopes.find(
              (item) => String(item?.tenant_id || "").trim() === selectedApiScope,
            )
          : activeScopes[0];
        const hasHeartbeat = scopedAgents.length > 0;
        const hasMetricsActivity = Boolean(scopedActivity?.active || scopedActivity?.metrics_active);

        if (hasHeartbeat || hasMetricsActivity) {
          const detectionLabel = hasHeartbeat
            ? `heartbeat detected for ${scopedAgents.length} agent${scopedAgents.length === 1 ? "" : "s"}`
            : `metrics detected for ${scopedActivity?.name || "the selected API key"}`;
          setConnectStatus("connected");
          setConnectMessage(
            `Connected: ${detectionLabel} in the selected API key scope.`,
          );
          return;
        }
      } catch (err) {
        setConnectStatus("error");
        setConnectMessage(err?.message || "Could not verify connection.");
        return;
      }
      if (!waitUntilConnected) break;
      await new Promise((resolve) => setTimeout(resolve, 5000));
    }
    setConnectStatus(waitUntilConnected ? "timeout" : "idle");
    setConnectMessage(
      waitUntilConnected
        ? "No heartbeat detected yet for the selected API key scope. You can keep running and check again later."
        : "No heartbeat detected yet for the selected API key scope.",
    );
  };

  const copyText = async (value) => {
    const copied = await copyToClipboard(value);
    if (copied) {
      toast.success("Copied to clipboard");
      return;
    }
    toast.error("Failed to copy to clipboard");
  };

  const handleCreateApiKey = async () => {
    const name = String(newApiKeyName || "").trim();
    if (!name || creatingApiKey) return;
    setCreatingApiKey(true);
    setApiKeyCreateMessage("");
    try {
      const created = await api.createApiKey({ name });
      if (created?.id && created?.otlp_token) {
        setApiKeyTokenMap((prev) => ({
          ...prev,
          [created.id]: created.otlp_token,
        }));
      }
      if (created?.id) setSelectedApiKeyId(created.id);
      const refreshed = await api.listApiKeys().catch(() => []);
      setFetchedApiKeys(Array.isArray(refreshed) ? refreshed : []);
      await onRefreshKeys?.();
      setNewApiKeyName("");
      setApiKeyCreateMessage("API key created and selected.");
    } catch (err) {
      setApiKeyCreateMessage(err?.message || "Failed to create API key.");
    } finally {
      setCreatingApiKey(false);
    }
  };

  const handleRegenerateSelectedToken = async () => {
    const keyId = String(selectedApiKeyId || "").trim();
    if (!keyId || tokenRegenerating) return;
    setTokenRegenerating(true);
    setTokenRegenerateError("");
    try {
      const updated = await api.regenerateApiKeyOtlpToken(keyId);
      const token = String(updated?.otlp_token || "").trim();
      if (!token) {
        setTokenRegenerateError(
          "Token regeneration completed but no token was returned.",
        );
        return;
      }
      setApiKeyTokenMap((prev) => ({ ...prev, [keyId]: token }));
    } catch (err) {
      setTokenRegenerateError(
        err?.message || "Failed to regenerate token for selected key.",
      );
    } finally {
      setTokenRegenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/45 p-4 backdrop-blur-xl dark:bg-black/55">
      <div className="w-full max-w-4xl rounded-xl border border-sre-border bg-sre-bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-sre-border px-5 py-3">
          <div>
            <h2 className="text-lg font-semibold text-sre-text">
              Ojo Agent Setup Wizard
            </h2>
            <p className="text-xs text-sre-text-muted">
              Slide {step + 1} of 5
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-sre-text-muted hover:bg-sre-surface-light hover:text-sre-text"
            aria-label="Close setup wizard"
          >
            <span className="material-icons text-lg">close</span>
          </button>
        </div>

        <div className="max-h-[72vh] overflow-y-auto p-5">
          {step === 0 && (
            <div className="space-y-4">
              <h3 className="text-base font-semibold text-sre-text">
                1. Pick your operating system
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {OJO_OS_OPTIONS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    onClick={() => {
                      setSelectedOs(option.key);
                      setSelectedAssetUrl("");
                      if (option.key === "extras" && !selectedExtraServiceKey) {
                        setSelectedExtraServiceKey(OJO_EXTRA_SERVICES[0]?.key || "");
                      }
                    }}
                    className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                      selectedOs === option.key
                        ? "border-sre-primary bg-sre-primary/10"
                        : "border-sre-border bg-sre-surface hover:border-sre-primary/40"
                    }`}
                  >
                    <div className="flex items-center gap-2 text-sre-text">
                      <span className="material-icons text-base" aria-hidden>
                        {option.icon}
                      </span>
                      <span className="font-semibold">{option.label}</span>
                    </div>
                  </button>
                ))}
              </div>

              {selectedOs === "extras" && (
                <div className="rounded-xl border border-sre-border bg-sre-surface/70 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <h4 className="text-sm font-semibold text-sre-text">
                        Extra services
                      </h4>
                      <p className="mt-1 text-sm text-sre-text-muted">
                        Add focused sidecar collectors for Docker, GPU, sensors, Postgres, or MySQL. Each runs as its own binary and sends OTLP metrics to the same collector endpoint.
                      </p>
                    </div>
                    <div className="w-full sm:max-w-xs">
                      <Input
                        value={extraServiceSearch}
                        onChange={(event) => setExtraServiceSearch(event.target.value)}
                        placeholder="Search gpu, docker, postgres..."
                        className="text-sm"
                      />
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
                    {filteredExtraServices.map((service) => (
                      <button
                        key={service.key}
                        type="button"
                        onClick={() => {
                          setSelectedExtraServiceKey(service.key);
                          setSelectedAssetUrl("");
                        }}
                        className={`rounded-xl border p-4 text-left transition-all ${
                          selectedExtraServiceKey === service.key
                            ? "border-sre-primary bg-sre-primary/10 shadow-sm"
                            : "border-sre-border bg-sre-bg hover:border-sre-primary/40"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span
                                className="material-icons inline-flex h-5 w-5 shrink-0 items-center justify-center text-base leading-none text-sre-primary"
                                aria-hidden
                              >
                                {service.icon}
                              </span>
                              <span className="font-semibold text-sre-text">
                                {service.label}
                              </span>
                            </div>
                            <div className="mt-1 text-xs text-sre-text-muted">
                              {service.packageName} · {service.configFile}
                            </div>
                          </div>
                          {selectedExtraServiceKey === service.key ? (
                            <span className="rounded-full border border-sre-primary/30 bg-sre-primary/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-sre-primary">
                              Selected
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-3 text-sm text-sre-text-muted">
                          {service.description}
                        </p>
                      </button>
                    ))}
                  </div>

                  {filteredExtraServices.length === 0 ? (
                    <div className="mt-4 rounded-xl border border-dashed border-sre-border bg-sre-bg p-4 text-sm text-sre-text-muted">
                      No matching extra services found. Try `gpu`, `sensors`, `postgres`, `mysql`, or `docker`.
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <h3 className="text-base font-semibold text-sre-text">
                2. Download the package from GitHub releases
              </h3>
              <div className="rounded-lg border border-sre-border bg-sre-surface p-3 text-sm">
                <div className="text-sre-text">
                  Release in use:{" "}
                  <span className="font-semibold">
                    {releaseTitleText}
                  </span>
                </div>
                {releaseError ? (
                  <p className="text-red-500 text-xs mt-2">{releaseError}</p>
                ) : null}
                <a
                  href={OJO_RELEASES_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex text-xs font-semibold text-sre-primary hover:underline"
                >
                  Open releases page
                </a>
                <p className="mt-2 text-xs text-sre-text-muted">
                  {selectedOs === "extras"
                    ? `Download the ${selectedExtraService?.packageName || "extension"} binary if it is published with the release. If it is missing, build it from source and use the repository config examples in the next step.`
                    : "Download the raw binary or `.exe` asset directly. The suggested command auto-uses the first matching asset if you don't pick one manually."}
                </p>
              </div>

              <div className="rounded-lg border border-sre-border bg-sre-bg-alt p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-sre-text-muted">
                    Suggested install command
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      copyText(
                        selectedOs === "extras"
                          ? extraInstallCommand
                          : installCommandByOs[selectedOs],
                      )
                    }
                    className="rounded-md border border-sre-border px-2 py-1 text-xs text-sre-text hover:border-sre-primary/40"
                  >
                    Copy command
                  </button>
                </div>
                {selectedAsset ? (
                  <p className="mb-2 text-xs text-sre-text-muted">
                    Selected asset:{" "}
                    <span className="font-semibold text-sre-text">
                      {selectedAsset.name}
                    </span>
                  </p>
                ) : null}
                <pre className="rounded-md text-xs text-sre-text overflow-x-auto">
                  <code className="whitespace-pre">
                    {selectedOs === "extras"
                      ? extraInstallCommand
                      : installCommandByOs[selectedOs]}
                  </code>
                </pre>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium text-sre-text">
                  Matching assets ({osAssets.length})
                </p>
                {selectedOs !== "extras" && osAssets.length === 2 ? (
                  <p className="text-xs text-sre-text-muted">
                    This matches the expected core binary pair for the current release.
                  </p>
                ) : null}
                {loadingRelease && !assets.length ? (
                  <p className="text-sm text-sre-text-muted">
                    Loading release assets...
                  </p>
                ) : osAssets.length ? (
                  <div className="space-y-2">
                    {osAssets.map((asset) => (
                      <div
                        key={asset.id || asset.name}
                        className={`rounded-md border px-3 py-2 text-sm ${
                          selectedAssetUrl === asset.browser_download_url
                            ? "border-sre-primary bg-sre-primary/10"
                            : "border-sre-border bg-sre-surface"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 text-sre-text truncate">
                            {asset.name}
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <button
                              type="button"
                              onClick={() =>
                                setSelectedAssetUrl(asset.browser_download_url || "")
                              }
                              className="rounded-md border border-sre-border px-2 py-1 text-xs text-sre-text hover:border-sre-primary/40"
                            >
                              {selectedAssetUrl === asset.browser_download_url
                                ? "Selected"
                                : "Select"}
                            </button>
                            <a
                              href={asset.browser_download_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="rounded-md border border-sre-border px-2 py-1 text-xs text-sre-text hover:border-sre-primary/40"
                            >
                              Download
                            </a>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-sre-text-muted">
                    {selectedOs === "extras"
                      ? `No auto-matched asset found for ${selectedExtraService?.packageName || "this extension"} yet. Build it from source or pick the matching binary from the release list below if your pipeline publishes it.`
                      : `No auto-matched assets yet. Pick the binary/EXE package for ${selectedOs} from the releases list below.`}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium text-sre-text">
                  Recent releases
                </p>
                {loadingRelease && !releasesList.length ? (
                  <p className="text-sm text-sre-text-muted">
                    Loading releases list...
                  </p>
                ) : releasesList.length ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {releasesList.map((releaseItem) => (
                      <a
                        key={releaseItem.id || releaseItem.tag_name}
                        href={releaseItem.html_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="rounded-md border border-sre-border bg-sre-surface px-3 py-2 text-sm text-sre-text hover:border-sre-primary/50"
                      >
                        <div className="font-semibold">
                          {releaseItem.name || releaseItem.tag_name}
                        </div>
                        {String(releaseItem.name || "").trim() !==
                        String(releaseItem.tag_name || "").trim() ? (
                          <div className="text-xs text-sre-text-muted mt-0.5">
                            {releaseItem.tag_name}
                          </div>
                        ) : null}
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-sre-text-muted">
                    Could not load recent releases. Use the releases page link above.
                  </p>
                )}
                {!loadingRelease && releaseError && (
                  <div className="space-y-1.5 mt-2">
                    {fallbackReleaseLinks.map((item) => (
                      <a
                        key={item.url}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block text-xs font-medium text-sre-primary hover:underline"
                      >
                        {item.name}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <h3 className="text-base font-semibold text-sre-text">
                {selectedOs === "extras"
                  ? `3. Configure ${selectedExtraService?.label || "service"} service`
                  : "3. Generate Ojo config file"}
              </h3>
              <div className="rounded-lg border border-sre-border bg-sre-surface p-3 text-sm text-sre-text-muted">
                {selectedOs === "extras" ? (
                  <>
                    For extra services, refer to repository config examples and use{" "}
                    <span className="font-semibold text-sre-text">
                      {selectedConfigFile}
                    </span>{" "}
                    as your starting file name.
                  </>
                ) : (
                  <>
                    Use this file as{" "}
                    <span className="font-semibold text-sre-text">
                      {selectedConfigFile}
                    </span>{" "}
                    for your selected OS.
                  </>
                )}
              </div>

              {selectedOs === "extras" ? (
                <div className="rounded-lg border border-sre-border bg-sre-bg-alt p-3 text-sm text-sre-text-muted space-y-2">
                  <p>
                    Review the Ojo repository for service-specific config examples and copy the
                    example for{" "}
                    <span className="font-semibold text-sre-text">
                      {selectedExtraService?.packageName || "this service"}
                    </span>
                    .
                  </p>
                  <a
                    href={OJO_REPO_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex text-xs font-semibold text-sre-primary hover:underline"
                  >
                    Open Ojo repository examples
                  </a>
                </div>
              ) : (
                <div className="rounded-lg border border-sre-border bg-sre-bg-alt p-3">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-sre-text-muted">
                      Ojo config ({selectedConfigFile})
                    </p>
                    <button
                      type="button"
                      onClick={() => copyText(generatedConfig)}
                      className="rounded-md border border-sre-border px-2 py-1 text-xs text-sre-text hover:border-sre-primary/40"
                    >
                      Copy config
                    </button>
                  </div>
                  <pre className="max-h-72 overflow-auto rounded-md bg-sre-surface p-3 text-xs text-sre-text">
                    <code>{generatedConfig}</code>
                  </pre>
                </div>
              )}
              {selectedOs === "extras" ? (
                <div className="rounded-lg border border-sre-border bg-sre-bg-alt p-3 text-sm text-sre-text-muted">
                  This extension binary still needs the OTEL collector config from the next step. Point its OTLP export to the same collector endpoint and keep the collector listening on port <span className="font-semibold text-sre-text">4355</span>.
                </div>
              ) : null}
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <h3 className="text-base font-semibold text-sre-text">
                4. Create or use an API key and OTEL metric ingest config
              </h3>
              <p className="text-sm text-sre-text-muted">
                Configure your collector to expose metric ingest on port{" "}
                <span className="font-semibold text-sre-text">4355</span> and
                forward metrics with an API key token.
              </p>

              {effectiveApiKeys.length === 0 ? (
                <div className="rounded-lg border border-amber-300/60 bg-amber-50/50 p-3 text-sm text-amber-900 dark:bg-amber-900/20 dark:text-amber-200">
                  No usable API keys found yet. Create one below, then continue.
                  <div className="mt-2">
                    <NavLink
                      to="/apikey"
                      onClick={onClose}
                      className="inline-flex text-xs font-semibold text-sre-primary hover:underline"
                    >
                      Go to API Keys
                    </NavLink>
                  </div>
                </div>
              ) : null}

              <div className="rounded-lg border border-sre-border bg-sre-surface p-3 space-y-3">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wide text-sre-text-muted mb-1.5">
                    Create API Key (Name)
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newApiKeyName}
                      onChange={(e) => setNewApiKeyName(e.target.value)}
                      placeholder="e.g. ojo-metrics-prod"
                      className="w-full rounded-md border border-sre-border bg-sre-bg-card px-3 py-2 text-sm text-sre-text"
                    />
                    <button
                      type="button"
                      onClick={handleCreateApiKey}
                      disabled={creatingApiKey || !String(newApiKeyName || "").trim()}
                      className="rounded-md border border-sre-primary/40 bg-sre-primary/10 px-3 py-2 text-xs font-medium text-sre-text disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {creatingApiKey ? "Creating..." : "Create key"}
                    </button>
                  </div>
                </div>
                {apiKeyCreateMessage ? (
                  <p className="text-xs text-sre-text-muted">{apiKeyCreateMessage}</p>
                ) : null}
              </div>

              <div className="rounded-lg border border-sre-border bg-sre-surface p-3">
                <label className="block text-xs font-semibold uppercase tracking-wide text-sre-text-muted mb-1.5">
                  Use API Key
                </label>
                <select
                  value={selectedApiKeyId}
                  onChange={(e) => {
                    setSelectedApiKeyId(e.target.value);
                    setTokenRegenerateError("");
                  }}
                  className="w-full rounded-md border border-sre-border bg-sre-bg-card px-3 py-2 text-sm text-sre-text"
                >
                  {effectiveApiKeys.length === 0 ? (
                    <option value="">No API keys yet</option>
                  ) : (
                    effectiveApiKeys.map((key) => (
                      <option key={key.id} value={key.id}>
                        {key.name}
                      </option>
                    ))
                  )}
                </select>
                {!selectedToken && selectedApiKeyId ? (
                  <div className="mt-2 rounded-md border border-amber-300/60 bg-amber-50/60 p-2 text-xs text-amber-900 dark:bg-amber-900/20 dark:text-amber-200">
                    <p>
                      This key has no active OTLP token. You must regenerate it
                      before using this config.
                    </p>
                    <p className="mt-1">
                      Existing collectors using the previous token will stop
                      working after regeneration.
                    </p>
                    <button
                      type="button"
                      onClick={handleRegenerateSelectedToken}
                      disabled={tokenRegenerating}
                      className="mt-2 rounded-md border border-amber-400/70 bg-amber-100/80 px-2 py-1 text-xs font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-amber-900/40 dark:text-amber-200"
                    >
                      {tokenRegenerating ? "Regenerating..." : "Click here to regenerate token"}
                    </button>
                    {tokenRegenerateError ? (
                      <p className="mt-1 text-red-500">{tokenRegenerateError}</p>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div className="rounded-lg border border-sre-border bg-sre-bg-alt p-3">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-sre-text-muted">
                    OTEL config (metric ingest 4355)
                  </p>
                  <button
                    type="button"
                    onClick={() => copyText(otelIngestConfig)}
                    className="rounded-md border border-sre-border px-2 py-1 text-xs text-sre-text hover:border-sre-primary/40"
                  >
                    Copy config
                  </button>
                </div>
                <pre className="max-h-72 overflow-auto rounded-md bg-sre-surface p-3 text-xs text-sre-text">
                  <code>{otelIngestConfig}</code>
                </pre>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <h3 className="text-base font-semibold text-sre-text">
                5. Check if the agent is connected
              </h3>
              <p className="text-sm text-sre-text-muted">
                You can check now, wait until connected, or skip and check
                later.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => runConnectionCheck(false)}
                  className="rounded-md border border-sre-border bg-sre-surface px-3 py-2 text-sm text-sre-text hover:border-sre-primary/40"
                >
                  Check now
                </button>
                <button
                  type="button"
                  onClick={() => runConnectionCheck(true)}
                  className="rounded-md border border-sre-primary/40 bg-sre-primary/10 px-3 py-2 text-sm font-medium text-sre-text"
                >
                  Wait until connected
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setConnectStatus("skipped");
                    setConnectMessage("Skipped. You can verify from Dashboard later.");
                  }}
                  className="rounded-md border border-sre-border bg-sre-surface px-3 py-2 text-sm text-sre-text"
                >
                  Skip for later
                </button>
              </div>
              {connectMessage ? (
                <div
                  className={`rounded-lg border p-3 text-sm ${
                    connectStatus === "connected"
                      ? "border-emerald-300 bg-emerald-50/60 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-200"
                      : connectStatus === "error" || connectStatus === "timeout"
                        ? "border-amber-300 bg-amber-50/60 text-amber-900 dark:bg-amber-900/20 dark:text-amber-200"
                        : "border-sre-border bg-sre-bg-alt text-sre-text"
                  }`}
                >
                  {connectMessage}
                </div>
              ) : null}
              {connectStatus === "connected" ? (
                <div className="rounded-xl border border-sre-primary/30 bg-[linear-gradient(135deg,rgba(14,165,233,0.12),rgba(34,197,94,0.08))] p-4">
                  <div className="flex items-start gap-3">
                    <span className="material-icons text-sre-primary">
                      rocket_launch
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-sre-text">
                        Next up: make the data usable
                      </div>
                      <div className="mt-1 text-sm text-sre-text-muted">
                        Once confirmed, create a datasource and then create a
                        dashboard that uses that datasource.
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <NavLink
                          to="/grafana"
                          onClick={onClose}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-sre-primary/40 bg-sre-primary/10 px-3 py-2 text-xs font-semibold text-sre-text transition-colors hover:border-sre-primary/70 hover:bg-sre-primary/15"
                        >
                          <span className="material-icons text-sm leading-none">
                            storage
                          </span>
                          Create datasource
                        </NavLink>
                        <NavLink
                          to="/grafana"
                          onClick={onClose}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-sre-border bg-sre-surface px-3 py-2 text-xs font-semibold text-sre-text transition-colors hover:border-sre-primary/40"
                        >
                          <span className="material-icons text-sm leading-none">
                            dashboard_customize
                          </span>
                          Create dashboard
                        </NavLink>
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          )}

        </div>

        <div className="flex items-center justify-between border-t border-sre-border px-5 py-3">
          <button
            type="button"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="rounded-md border border-sre-border px-3 py-1.5 text-sm text-sre-text disabled:cursor-not-allowed disabled:opacity-50"
          >
            Back
          </button>
          {step < 4 ? (
            <button
              type="button"
              onClick={() => setStep((s) => Math.min(4, s + 1))}
              disabled={selectedOs === "extras" && !selectedExtraServiceKey}
              className="rounded-md border border-sre-primary/40 bg-sre-primary/10 px-3 py-1.5 text-sm font-medium text-sre-text"
            >
              Next
            </button>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-sre-primary/40 bg-sre-primary/10 px-3 py-1.5 text-sm font-medium text-sre-text"
            >
              Finish
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function UserMenu({
  user,
  logout,
  hasPermission,
  openChangePassword,
  compact = false,
}) {
  const [open, setOpen] = useState(false);
  const [mdUp, setMdUp] = useState(false);
  const ref = useRef(null);
  const menuRef = useRef(null);
  const navigate = useNavigate();

  /** Sidebar rail is md+ only; keep account links in this menu on small screens. */
  const hideAccountLinksInMenu = compact && mdUp;

  const username = user?.username || "";
  const role = user?.role || "user";
  const roleRedundant =
    username &&
    role &&
    username.toLowerCase() === role.toLowerCase();

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mq = window.matchMedia("(min-width: 768px)");
    const sync = () => setMdUp(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => menuRef.current?.focus(), 0);
    }
  }, [open]);

  const handleLogout = () => {
    setOpen(false);
    logout();
    navigate("/login");
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex items-center text-sre-text transition-colors ${
          compact
            ? "gap-1.5 rounded-xl border border-sre-border bg-sre-surface/55 px-2 py-1.5 backdrop-blur-xl hover:bg-sre-surface-light/70 dark:bg-sre-surface/45"
            : "gap-2 rounded-lg px-2.5 py-1.5 hover:bg-sre-surface-light/80 sm:px-3"
        }`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`User menu for ${username || "user"}`}
      >
        <span
          className={`material-icons shrink-0 text-sre-text-muted ${compact ? "text-lg" : "text-xl"}`}
          aria-hidden
        >
          account_circle
        </span>
        <span
          className={`hidden max-w-[10rem] truncate text-left text-sm font-medium text-sre-text sm:block ${
            compact ? "max-w-[8rem] text-[13px]" : ""
          }`}
        >
          {username || "Account"}
        </span>
        {!roleRedundant && (
          <Badge
            variant={user?.role === "admin" ? "error" : "info"}
            className="hidden shrink-0 text-[10px] font-semibold uppercase tracking-wide sm:inline-flex"
          >
            {role}
          </Badge>
        )}
        <svg
          className="h-4 w-4 shrink-0 text-sre-text-muted"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 011.08 1.04l-4.25 4.25a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div
          ref={menuRef}
          tabIndex={-1}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
          role="menu"
          className="absolute right-0 z-50 mt-2 w-52 rounded-lg border border-sre-border bg-sre-bg-card py-1 shadow-lg"
        >
          <div className="border-b border-sre-border/80 px-3 py-2">
            <div className="flex items-center gap-2 min-w-0">
              <p className="truncate text-sm font-medium text-sre-text">
                {username || "Signed in"}
              </p>
              {!roleRedundant && (
                <Badge
                  variant={user?.role === "admin" ? "error" : "info"}
                  className="shrink-0 text-[10px] font-semibold uppercase tracking-wide"
                >
                  {role}
                </Badge>
              )}
            </div>
          </div>
          {!hideAccountLinksInMenu && (
            <>
              {hasPermission("manage:users") && (
                <NavLink
                  to="/users"
                  role="menuitem"
                  tabIndex={0}
                  className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50"
                  onClick={() => setOpen(false)}
                >
                  <span
                    className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted"
                    aria-hidden
                  >
                    people
                  </span>{" "}
                  Users
                </NavLink>
              )}
              {hasPermission("manage:groups") && (
                <NavLink
                  to="/groups"
                  role="menuitem"
                  tabIndex={0}
                  className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50"
                  onClick={() => setOpen(false)}
                >
                  <span
                    className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted"
                    aria-hidden
                  >
                    groups
                  </span>{" "}
                  Groups
                </NavLink>
              )}

              <div className="border-t border-sre-border my-1" />

              <NavLink
                to="/apikey"
                role="menuitem"
                tabIndex={0}
                className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50"
                onClick={() => setOpen(false)}
              >
                <span
                  className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted"
                  aria-hidden
                >
                  key
                </span>{" "}
                API Key
              </NavLink>

              <NavLink
                to="/integrations"
                role="menuitem"
                tabIndex={0}
                className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50"
                onClick={() => setOpen(false)}
              >
                <span
                  className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted"
                  aria-hidden
                >
                  integration_instructions
                </span>{" "}
                Integrations
              </NavLink>

              {hasPermission("read:audit_logs") && user?.role === "admin" && (
                <NavLink
                  to="/audit-compliance"
                  role="menuitem"
                  tabIndex={0}
                  className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50"
                  onClick={() => setOpen(false)}
                >
                  <span
                    className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted"
                    aria-hidden
                  >
                    policy
                  </span>{" "}
                  Audit
                </NavLink>
              )}

              {hasPermission("read:agents") && (
                <NavLink
                  to="/quotas"
                  role="menuitem"
                  tabIndex={0}
                  className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50"
                  onClick={() => setOpen(false)}
                >
                  <span
                    className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted"
                    aria-hidden
                  >
                    data_thresholding
                  </span>{" "}
                  Quotas
                </NavLink>
              )}
            </>
          )}

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              openChangePassword?.();
            }}
            className="w-full text-left px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50"
          >
            <span
              className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted"
              aria-hidden
            >
              lock
            </span>{" "}
            Password
          </button>

          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            className="w-full text-left px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50"
          >
            <span
              className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted"
              aria-hidden
            >
              logout
            </span>{" "}
            Logout
          </button>
        </div>
      )}
    </div>
  );
}

UserMenu.propTypes = {
  user: PropTypes.object,
  logout: PropTypes.func.isRequired,
  hasPermission: PropTypes.func.isRequired,
  openChangePassword: PropTypes.func,
  compact: PropTypes.bool,
};

OjoAgentWizardModal.propTypes = {
  open: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  apiKeys: PropTypes.array,
  onRefreshKeys: PropTypes.func,
};
