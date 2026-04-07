import { NavLink } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import PropTypes from "prop-types";
import * as api from "../api";
import { APP_VERSION } from "../utils/constants";
import { useToast } from "../contexts/ToastContext";
import { copyToClipboard } from "../utils/helpers";

const OJO_REPO_URL = "https://github.com/observantio/ojo";
const OJO_SERVICES = "https://github.com/observantio/ojo/tree/main/services";
const OJO_RELEASES_URL = `${OJO_REPO_URL}/releases/latest`;
const OJO_RECOMMENDED_RELEASE_TAG = APP_VERSION;
const OJO_RECOMMENDED_RELEASE_URL = `${OJO_REPO_URL}/releases/tag/${OJO_RECOMMENDED_RELEASE_TAG}`;
const OJO_CONFIG_BASE_URL = `${OJO_REPO_URL}/blob/main`;
const RELEASE_FETCH_TIMEOUT_MS = 8000;

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

const hasWindowsMarker = (name) => String(name || "").toLowerCase().includes("windows");

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
        setReleaseError(err?.message || "Unable to load release metadata");
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
  const visibleReleases = releasesList.slice(0, 2);
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

  const selectedToken = String(
    apiKeyTokenMap[selectedApiKeyId] || selectedApiKey?.otlp_token || "",
  ).trim();

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
                {OJO_OS_OPTIONS.map((option) => {
                  const styles = OJO_OS_STYLES[option.key] || {
                    selected: "border-sre-primary bg-sre-primary/10 text-sre-primary",
                    hover: "hover:border-sre-primary/40 hover:text-sre-primary",
                  };
                  return (
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
                          ? styles.selected
                          : `border-sre-border bg-sre-surface ${styles.hover}`
                      }`}
                    >
                      <div className="flex items-center gap-2 text-current">
                        <span className="material-icons text-base" aria-hidden>
                          {option.icon}
                        </span>
                        <span className="font-semibold">{option.label}</span>
                      </div>
                    </button>
                  );
                })}
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
                      <input
                        value={extraServiceSearch}
                        onChange={(event) => setExtraServiceSearch(event.target.value)}
                        placeholder="Search gpu, docker, postgres..."
                        className="w-full rounded-xl border border-sre-border bg-sre-surface px-3 py-2 text-sm text-sre-text focus:border-sre-primary focus:outline-none focus:ring-1 focus:ring-sre-primary"
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
                  Release in use: {" "}
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
                    Selected asset: {" "}
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
                ) : visibleReleases.length ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {visibleReleases.map((releaseItem) => (
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
                    For extra services, refer to repository config examples and use {" "}
                    <span className="font-semibold text-sre-text">
                      {selectedConfigFile}
                    </span>{" "}
                    as your starting file name.
                  </>
                ) : (
                  <>
                    Use this file as {" "}
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
                    example for {" "}
                    <span className="font-semibold text-sre-text">
                      {selectedExtraService?.packageName || "this service"}
                    </span>
                    .
                  </p>
                  <a
                    href={OJO_SERVICES}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex text-xs font-semibold text-sre-primary hover:underline"
                  >
                    Open Ojo repository examples
                  </a>
                </div>
              ) : (
                <div className="rounded-lg border border-sre-border bg-sre-bg-alt p-3 text-sm text-sre-text-muted space-y-2">
                  <p>
                    Use this file as <span className="font-semibold text-sre-text">{selectedConfigFile}</span> for your selected OS.
                  </p>
                  <div className="flex flex-wrap gap-3 text-xs">
                    <a
                      href={`${OJO_CONFIG_BASE_URL}/${selectedConfigFile}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sre-primary hover:underline"
                    >
                      {selectedConfigFile}
                    </a>
                  </div>
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
                4. Create or use an API key and run the collector
              </h3>
              <p className="text-sm text-sre-text-muted">
                Configure your collector for Ojo metric ingest on port
                <span className="font-semibold text-sre-text"> 4355</span> and
                use the selected API key token.
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
                      aria-label={creatingApiKey ? "Creating API key" : "Create API key"}
                      className="inline-flex items-center gap-2 rounded-md border border-sre-primary/40 bg-sre-primary/10 px-3 py-2 text-xs font-medium text-sre-text disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {creatingApiKey ? (
                        <span className="material-icons text-base">hourglass_top</span>
                      ) : (
                        <>
                          <span className="material-icons text-base">add</span>
                          <span className="material-icons text-base">key</span>
                        </>
                      )}
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
                      before using this collector command.
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

              <div className="rounded-lg border border-sre-border bg-sre-bg-alt p-3 space-y-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-sre-text-muted">
                    Ojo collector command
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      copyText(
                        `sudo bash otel/run_otel_collector.sh -t ${selectedToken || '<YOUR_TOKEN_HERE>'} -c otel/configs/ojo.yaml`,
                      )
                    }
                    className="rounded-md border border-sre-border px-2 py-1 text-xs text-sre-text hover:border-sre-primary/40"
                  >
                    Copy command
                  </button>
                </div>
                <div className="overflow-x-auto rounded-md bg-sre-surface p-3 text-xs font-medium text-sre-text">
                  <code className="whitespace-pre-wrap">
                    sudo bash otel/run_otel_collector.sh -t <span className="text-sre-primary">{selectedToken || '<YOUR_TOKEN_HERE>'}</span> -c <span className="text-sre-success">otel/configs/ojo.yaml</span>
                  </code>
                </div>
                <a
                  href="https://github.com/observantio/watchdog/blob/main/otel/OTEL.md"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-medium text-sre-primary hover:underline"
                >
                  Read the OTEL setup instructions
                </a>
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

OjoAgentWizardModal.propTypes = {
  open: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  apiKeys: PropTypes.array,
  onRefreshKeys: PropTypes.func,
};

export default OjoAgentWizardModal;
