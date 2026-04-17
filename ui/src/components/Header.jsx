import { NavLink, useNavigate } from "react-router-dom";
import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import PropTypes from "prop-types";
import ThemeToggle from "./ThemeToggle";
import { Badge, Button, Input } from "./ui";
import ChangePasswordModal from "./ChangePasswordModal";
import OjoAgentWizardModal from "./OjoAgentWizardModal";
import * as api from "../api";
import { NAV_ITEMS, APP_VERSION } from "../utils/constants";
import { useLayoutMode } from "../contexts/LayoutModeContext";
import { useSharedIncidentSummary } from "../contexts/IncidentSummaryContext";
import { useToast } from "../contexts/ToastContext";
import { copyToClipboard } from "../utils/helpers";

const NAV_ITEM_LIST = Object.values(NAV_ITEMS);
const RELEASE_LABEL = `Wolfmegasaur ${APP_VERSION}`;
const WATCHDOG_GITHUB_URL = "https://github.com/observantio/watchdog";

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
  { key: "linux", label: "Linux", icon: "terminal", color: "success" },
  { key: "windows", label: "Windows", icon: "desktop_windows", color: "primary" },
  { key: "extras", label: "Extra services", icon: "extension", color: "warning" },
];

const OJO_OS_STYLES = {
  linux: {
    selected: "border-sre-success bg-sre-success/10 text-sre-success",
    hover: "hover:border-sre-success/40 hover:text-sre-success",
  },
  windows: {
    selected: "border-sre-primary bg-sre-primary/10 text-sre-primary",
    hover: "hover:border-sre-primary/40 hover:text-sre-primary",
  },
  extras: {
    selected: "border-sre-warning bg-sre-warning/10 text-sre-warning",
    hover: "hover:border-sre-warning/40 hover:text-sre-warning",
  },
};

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
  const [copiedToken, setCopiedToken] = useState(false);
  const copyTimerRef = useRef(null);

  useEffect(() => {
    if (!createdToken) {
      setCopiedToken(false);
      return undefined;
    }
    const timeoutId = window.setTimeout(() => {
      setCreatedToken("");
      setCopiedToken(false);
    }, 30000);
    return () => {
      window.clearTimeout(timeoutId);
      window.clearTimeout(copyTimerRef.current);
    };
  }, [createdToken]);

  const handleCopyToken = async () => {
    if (!createdToken) return;
    const copied = await copyToClipboard(createdToken);
    if (!copied) {
      toast.error("Failed to copy token");
      return;
    }
    setCopiedToken(true);
    toast.success("Copied to clipboard");
    window.clearTimeout(copyTimerRef.current);
    copyTimerRef.current = window.setTimeout(() => {
      setCopiedToken(false);
    }, 2000);
  };

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
                    onClick={handleCopyToken}
                    className="rounded-md border border-sre-border px-2 py-0.5 text-[11px] font-medium text-sre-text hover:border-sre-primary/40"
                  >
                    {copiedToken ? "Copied" : "Copy"}
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
              blur_on
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
                  </span>
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
                  </span>
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
                </span>
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
                </span>
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
                  </span>
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
                  </span>
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
            </span>
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
            </span>
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
