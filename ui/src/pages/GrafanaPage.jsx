import { useState, useEffect, useCallback, useRef } from "react";
import {
  searchDashboards,
  createDashboard,
  updateDashboard,
  deleteDashboard,
  getDatasources,
  createDatasource,
  updateDatasource,
  deleteDatasource,
  getFolders,
  createFolder,
  updateFolder,
  deleteFolder,
  toggleFolderHidden,
  getGroups,
  toggleDashboardHidden,
  toggleDatasourceHidden,
  getDashboard,
  createGrafanaBootstrapSession,
  listMetricNames,
} from "../api";
import { Button, ConfirmDialog, Modal, Spinner } from "../components/ui";
import PageHeader from "../components/ui/PageHeader";
import DashboardEditorModal from "../components/grafana/DashboardEditorModal";
import DatasourceEditorModal from "../components/grafana/DatasourceEditorModal";
import FolderCreatorModal from "../components/grafana/FolderCreatorModal";
import { useToast } from "../contexts/ToastContext";
import GrafanaTabs from "../components/grafana/GrafanaTabs";
import GrafanaContent from "../components/grafana/GrafanaContent";
import { useAuth } from "../contexts/AuthContext";
import { APP_ORG_KEY, MIMIR_PROMETHEUS_URL } from "../utils/constants";
import {
  GRAFANA_DATASOURCE_TYPES as DATASOURCE_TYPES,
  overrideDashboardDatasource,
  resolveToUid,
} from "../utils/grafanaUtils";
import { buildGrafanaLaunchUrl } from "../utils/grafanaLaunchUtils";

const DEFAULT_GRAFANA_FILTERS = {
  teamId: "",
  folderKey: "",
  showHidden: false,
};
const GRAFANA_ORDER_STORAGE_PREFIX = "grafana:list-order:v1";
const GRAFANA_ORDER_TYPES = {
  dashboards: "dashboards",
  datasources: "datasources",
  folders: "folders",
};

function moveItemByIds(items, sourceId, targetId, getId) {
  const fromId = String(sourceId || "");
  const toId = String(targetId || "");
  if (!fromId || !toId || fromId === toId) return items;
  const fromIndex = items.findIndex((item) => getId(item) === fromId);
  const toIndex = items.findIndex((item) => getId(item) === toId);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return items;
  const next = [...items];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

function dashboardOrderId(item) {
  return String(item?.uid || "");
}

function datasourceOrderId(item) {
  return String(item?.uid || "");
}

function folderOrderId(item) {
  if (item?.uid) return `uid:${String(item.uid)}`;
  if (item?.id != null) return `id:${String(item.id)}`;
  return `title:${String(item?.title || "")}`;
}

function collectDatasourceReferences(node, refs) {
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) {
    node.forEach((item) => collectDatasourceReferences(item, refs));
    return;
  }

  Object.entries(node).forEach(([key, value]) => {
    if (key === "datasourceUid" && value) {
      refs.add(String(value));
    }

    if (key === "datasource" && value) {
      if (typeof value === "string") {
        refs.add(value);
      } else if (typeof value === "object") {
        if (value.uid) refs.add(String(value.uid));
        if (value.value) refs.add(String(value.value));
        if (value.name) refs.add(String(value.name));
        if (value.text) refs.add(String(value.text));
      }
    }

    if (value && typeof value === "object") {
      collectDatasourceReferences(value, refs);
    }
  });
}

function getDatasourceJsonData(datasource) {
  if (!datasource || typeof datasource !== "object") return {};
  if (datasource.jsonData && typeof datasource.jsonData === "object") {
    return datasource.jsonData;
  }
  if (datasource.json_data && typeof datasource.json_data === "object") {
    return datasource.json_data;
  }
  return {};
}

function findApiKeyById(apiKeys, candidateId) {
  const id = String(candidateId || "").trim();
  if (!id) return null;
  return (
    (Array.isArray(apiKeys) ? apiKeys : []).find(
      (k) => String(k?.id || "").trim() === id,
    ) || null
  );
}

export default function GrafanaPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState("dashboards");
  const [dashboards, setDashboards] = useState([]);
  const [datasources, setDatasources] = useState([]);
  const [folders, setFolders] = useState([]);
  const [groups, setGroups] = useState([]);
  const [dashboardQuery, setDashboardQuery] = useState("");
  const [datasourceQuery, setDatasourceQuery] = useState("");
  const [loading, setLoading] = useState(true);

  const [filters, setFilters] = useState({
    ...DEFAULT_GRAFANA_FILTERS,
  });

  const toast = useToast();
  const lastErrorToastRef = useRef({ key: "", ts: 0 });
  const isMountedRef = useRef(true);
  const query =
    activeTab === "datasources"
      ? datasourceQuery
      : activeTab === "dashboards"
        ? dashboardQuery
        : "";
  const queryRef = useRef(query);
  const filtersRef = useRef(filters);

  const setQuery = useCallback(
    (nextValue) => {
      if (activeTab !== "dashboards" && activeTab !== "datasources") return;
      const prevValue =
        activeTab === "dashboards" ? dashboardQuery : datasourceQuery;
      const resolved =
        typeof nextValue === "function" ? nextValue(prevValue) : nextValue;
      const finalValue = String(resolved ?? "");

      if (activeTab === "dashboards") {
        setDashboardQuery(finalValue);
      } else {
        setDatasourceQuery(finalValue);
      }
    },
    [
      activeTab,
      dashboardQuery,
      datasourceQuery,
      setDashboardQuery,
      setDatasourceQuery,
    ],
  );

  useEffect(
    () => () => {
      isMountedRef.current = false;
    },
    [],
  );

  useEffect(() => {
    queryRef.current = query;
  }, [query]);

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  useEffect(() => {
    setFilters((prev) => {
      if (
        prev.teamId === DEFAULT_GRAFANA_FILTERS.teamId &&
        prev.folderKey === DEFAULT_GRAFANA_FILTERS.folderKey &&
        prev.showHidden === DEFAULT_GRAFANA_FILTERS.showHidden
      ) {
        return prev;
      }
      return { ...DEFAULT_GRAFANA_FILTERS };
    });
  }, [activeTab]);

  const handleApiError = useCallback(
    (e) => {
      if (!e) return;
      const detail =
        typeof e?.body?.detail === "string"
          ? e.body.detail
          : e?.body?.detail?.message;
      const message =
        typeof e?.body?.message === "string" ? e.body.message : null;
      const msg =
        detail ||
        message ||
        e?.message ||
        String(e || "Request failed");
      const key = `${e?.status || "x"}:${msg}`;
      const now = Date.now();
      if (
        lastErrorToastRef.current.key === key &&
        now - lastErrorToastRef.current.ts < 2000
      ) {
        return;
      }
      lastErrorToastRef.current = { key, ts: now };
      toast.error(msg);
    },
    [toast],
  );

  const [showDashboardEditor, setShowDashboardEditor] = useState(false);
  const [editingDashboard, setEditingDashboard] = useState(null);
  const [editorTab, setEditorTab] = useState("form");
  const [jsonContent, setJsonContent] = useState("");
  const [jsonError, setJsonError] = useState("");
  const [fileUploaded, setFileUploaded] = useState(false);
  const [dashboardForm, setDashboardForm] = useState({
    title: "",
    tags: "",
    folderId: 0,
    refresh: "30s",
    datasourceUid: "",
    useTemplating: false,
    visibility: "private",
    sharedGroupIds: [],
  });

  const [showDatasourceEditor, setShowDatasourceEditor] = useState(false);
  const [editingDatasource, setEditingDatasource] = useState(null);
  const [datasourceForm, setDatasourceForm] = useState({
    name: "",
    type: "prometheus",
    url: "",
    isDefault: false,
    access: "proxy",
    visibility: "private",
    sharedGroupIds: [],
    apiKeyId: "",
  });

  const [showFolderCreator, setShowFolderCreator] = useState(false);
  const [editingFolder, setEditingFolder] = useState(null);
  const [folderName, setFolderName] = useState("");
  const [folderVisibility, setFolderVisibility] = useState("private");
  const [folderSharedGroupIds, setFolderSharedGroupIds] = useState([]);
  const [allowDashboardWrites, setAllowDashboardWrites] = useState(false);

  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: "",
    message: "",
    messageTone: "default",
    onConfirm: null,
    onCancel: null,
    variant: "danger",
    confirmText: "Delete",
    cancelText: "Cancel",
  });

  const [grafanaConfirmDialog, setGrafanaConfirmDialog] = useState({
    isOpen: false,
    path: null,
  });
  const [datasourceMetricsDialog, setDatasourceMetricsDialog] = useState({
    isOpen: false,
    datasourceName: "",
    keyName: "",
    loading: false,
    error: "",
    metrics: [],
  });
  const [dashboardKeyNamesByUid, setDashboardKeyNamesByUid] = useState({});

  const orderScope = String(
    user?.id || user?.username || user?.email || "anonymous",
  );

  const storageKeyForOrder = useCallback(
    (type) => `${GRAFANA_ORDER_STORAGE_PREFIX}:${orderScope}:${type}`,
    [orderScope],
  );

  const readPersistedOrder = useCallback(
    (type) => {
      try {
        const raw = globalThis?.localStorage?.getItem(storageKeyForOrder(type));
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return parsed.map((id) => String(id || "")).filter(Boolean);
      } catch {
        return [];
      }
    },
    [storageKeyForOrder],
  );

  const persistOrder = useCallback(
    (type, orderedIds) => {
      try {
        const normalized = (Array.isArray(orderedIds) ? orderedIds : [])
          .map((id) => String(id || ""))
          .filter(Boolean);
        globalThis?.localStorage?.setItem(
          storageKeyForOrder(type),
          JSON.stringify(normalized),
        );
      } catch {
        /* ignore local storage failures */
      }
    },
    [storageKeyForOrder],
  );

  const reconcileWithPersistedOrder = useCallback(
    (type, items, getId) => {
      const incoming = Array.isArray(items) ? items : [];
      const ids = incoming.map((item) => getId(item)).filter(Boolean);
      const idSet = new Set(ids);
      const savedOrder = readPersistedOrder(type);
      const keep = [];
      const seen = new Set();
      savedOrder.forEach((id) => {
        if (idSet.has(id) && !seen.has(id)) {
          keep.push(id);
          seen.add(id);
        }
      });
      ids.forEach((id) => {
        if (!seen.has(id)) keep.push(id);
      });

      const changed =
        keep.length !== savedOrder.length ||
        keep.some((id, idx) => id !== savedOrder[idx]);
      if (changed) {
        persistOrder(type, keep);
      }

      const rank = new Map(keep.map((id, idx) => [id, idx]));
      return [...incoming].sort((a, b) => {
        const ai = rank.get(getId(a));
        const bi = rank.get(getId(b));
        return (ai ?? Number.MAX_SAFE_INTEGER) - (bi ?? Number.MAX_SAFE_INTEGER);
      });
    },
    [persistOrder, readPersistedOrder],
  );

  function openInGrafana(path) {
    setGrafanaConfirmDialog({
      isOpen: true,
      path: path,
    });
  }

  async function confirmOpenInGrafana() {
    const { path } = grafanaConfirmDialog || {};
    try {
      const bootstrap = await createGrafanaBootstrapSession(
        path || "/dashboards",
      );
      const launchUrl = bootstrap?.launch_url
        ? `${window.location.protocol}//${window.location.hostname}:8080${bootstrap.launch_url}`
        : buildGrafanaLaunchUrl({
            path,
            protocol: window.location.protocol,
            hostname: window.location.hostname,
          });
      window.open(launchUrl, "_blank", "noopener,noreferrer");
    } catch {
      const launchUrl = buildGrafanaLaunchUrl({
        path,
        protocol: window.location.protocol,
        hostname: window.location.hostname,
      });
      window.open(launchUrl, "_blank", "noopener,noreferrer");
    }
    setGrafanaConfirmDialog({ isOpen: false, path: null });
  }

  const loadGroups = useCallback(async () => {
    try {
      const groupsData = await getGroups().catch(() => []);
      if (isMountedRef.current) {
        setGroups(groupsData);
      }
    } catch {
      /* silent */
    }
  }, []);

  const resolveDatasourceKeyMeta = useCallback(
    (datasource) => {
      if (!datasource) return { key: "", keyName: "" };

      const rawOrg = String(datasource?.orgId || datasource?.org_id || "").trim();
      const apiKeys = Array.isArray(user?.api_keys) ? user.api_keys : [];
      const jsonData = getDatasourceJsonData(datasource);
      const selectedApiKeyId = String(jsonData.watchdogApiKeyId || "").trim();
      const selectedScopeKey = String(jsonData.watchdogScopeKey || "").trim();
      const selectedApiKeyName = String(
        jsonData.watchdogApiKeyName || "",
      ).trim();
      const bySelectedId = findApiKeyById(apiKeys, selectedApiKeyId);
      const byId = findApiKeyById(apiKeys, rawOrg);
      const byKey = apiKeys.find((k) => String(k?.key || "") === rawOrg);
      const byScopeKey = apiKeys.find(
        (k) => String(k?.key || "") === selectedScopeKey,
      );
      const mappedKey = bySelectedId || byScopeKey || byId || byKey || null;
      const keyCandidate =
        mappedKey?.key ||
        selectedScopeKey ||
        (!/^\d+$/.test(rawOrg) ? rawOrg : "");
      const keyNameCandidate = mappedKey?.name || selectedApiKeyName || "";

      return {
        key: String(keyCandidate || "").trim(),
        keyName: String(keyNameCandidate || "").trim(),
      };
    },
    [user?.api_keys],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadDashboardKeyNames() {
      if (activeTab !== "dashboards" || dashboards.length === 0) {
        setDashboardKeyNamesByUid((prev) => {
          if (prev && Object.keys(prev).length === 0) {
            return prev;
          }
          return {};
        });
        return;
      }

      const entries = await Promise.all(
        dashboards.map(async (dashboard) => {
          try {
            const payload = await getDashboard(dashboard.uid);
            const refs = new Set();
            collectDatasourceReferences(payload?.dashboard || payload || {}, refs);

            const keyNames = Array.from(refs)
              .map((ref) => resolveToUid(ref, datasources) || String(ref))
              .map((uid) =>
                datasources.find(
                  (datasource) => String(datasource?.uid || "") === String(uid),
                ),
              )
              .filter(Boolean)
              .map((datasource) => resolveDatasourceKeyMeta(datasource).keyName)
              .filter(Boolean);

            return [dashboard.uid, Array.from(new Set(keyNames)).sort()];
          } catch {
            return [dashboard.uid, []];
          }
        }),
      );

      if (!cancelled) {
        setDashboardKeyNamesByUid(Object.fromEntries(entries));
      }
    }

    loadDashboardKeyNames();

    return () => {
      cancelled = true;
    };
  }, [activeTab, dashboards, datasources, resolveDatasourceKeyMeta]);

  const loadData = useCallback(async () => {
    const currentQuery = queryRef.current;
    const currentFilters = filtersRef.current || {};
    if (isMountedRef.current) {
      setLoading(true);
    }
    try {
      if (activeTab === "dashboards") {
        const [dashboardsData, foldersData, datasourcesData] =
          await Promise.all([
            searchDashboards({
              query: currentQuery || undefined,
              teamId: currentFilters.teamId || undefined,
              folderId:
                currentFilters.folderKey === "__general__" ? 0 : undefined,
              folderUid:
                currentFilters.folderKey &&
                currentFilters.folderKey !== "__general__"
                  ? currentFilters.folderKey
                  : undefined,
              showHidden: currentFilters.showHidden,
            }).catch(() => []),
            getFolders({ showHidden: currentFilters.showHidden }).catch(() => []),
            getDatasources().catch(() => []),
          ]);
        if (!isMountedRef.current) return;
        setDashboards(
          reconcileWithPersistedOrder(
            GRAFANA_ORDER_TYPES.dashboards,
            dashboardsData,
            dashboardOrderId,
          ),
        );
        setFolders(
          reconcileWithPersistedOrder(
            GRAFANA_ORDER_TYPES.folders,
            foldersData,
            folderOrderId,
          ),
        );
        setDatasources(
          reconcileWithPersistedOrder(
            GRAFANA_ORDER_TYPES.datasources,
            datasourcesData,
            datasourceOrderId,
          ),
        );
      } else if (activeTab === "datasources") {
        const [datasourcesData] = await Promise.all([
          getDatasources({
            query: currentQuery || undefined,
            teamId: currentFilters.teamId || undefined,
            showHidden: currentFilters.showHidden,
          }).catch(() => []),
        ]);
        if (!isMountedRef.current) return;
        setDatasources(
          reconcileWithPersistedOrder(
            GRAFANA_ORDER_TYPES.datasources,
            datasourcesData,
            datasourceOrderId,
          ),
        );
      } else if (activeTab === "folders") {
        const foldersData = await getFolders({
          showHidden: currentFilters.showHidden,
        }).catch(() => []);
        if (!isMountedRef.current) return;
        setFolders(
          reconcileWithPersistedOrder(
            GRAFANA_ORDER_TYPES.folders,
            foldersData,
            folderOrderId,
          ),
        );
      }
    } catch (e) {
      handleApiError(e);
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [activeTab, handleApiError, reconcileWithPersistedOrder]);

  const handleReorderDashboards = useCallback(
    (sourceId, targetId) => {
      setDashboards((prev) => {
        const next = moveItemByIds(prev, sourceId, targetId, dashboardOrderId);
        if (next === prev) return prev;
        persistOrder(
          GRAFANA_ORDER_TYPES.dashboards,
          next.map((item) => dashboardOrderId(item)).filter(Boolean),
        );
        return next;
      });
    },
    [persistOrder],
  );

  const handleReorderDatasources = useCallback(
    (sourceId, targetId) => {
      setDatasources((prev) => {
        const next = moveItemByIds(prev, sourceId, targetId, datasourceOrderId);
        if (next === prev) return prev;
        persistOrder(
          GRAFANA_ORDER_TYPES.datasources,
          next.map((item) => datasourceOrderId(item)).filter(Boolean),
        );
        return next;
      });
    },
    [persistOrder],
  );

  const handleReorderFolders = useCallback(
    (sourceId, targetId) => {
      setFolders((prev) => {
        const next = moveItemByIds(prev, sourceId, targetId, folderOrderId);
        if (next === prev) return prev;
        persistOrder(
          GRAFANA_ORDER_TYPES.folders,
          next.map((item) => folderOrderId(item)).filter(Boolean),
        );
        return next;
      });
    },
    [persistOrder],
  );

  useEffect(() => {
    loadData();
    loadGroups();
  }, [activeTab, loadData, loadGroups]);

  async function onSearch(e) {
    e.preventDefault();
    loadData();
  }

  function clearFilters() {
    setFilters({ ...DEFAULT_GRAFANA_FILTERS });
    if (activeTab === "dashboards") {
      setDashboardQuery("");
    } else if (activeTab === "datasources") {
      setDatasourceQuery("");
    }
  }

  async function handleToggleDashboardHidden(dashboard) {
    const nowHidden = !dashboard.is_hidden;
    setConfirmDialog({
      isOpen: true,
      title: nowHidden ? "Hide Dashboard" : "Unhide Dashboard",
      confirmText: nowHidden ? "Hide" : "Unhide",
      message: nowHidden
        ? `Are you sure you want to hide "${dashboard.title}"? This will hide the dashboard for your account.`
        : `Are you sure you want to unhide "${dashboard.title}"? This will make the dashboard visible again for your account.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await toggleDashboardHidden(dashboard.uid, nowHidden);
          toast.success(nowHidden ? "Dashboard hidden" : "Dashboard visible");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  async function handleToggleDatasourceHidden(datasource) {
    const nowHidden = !datasource.is_hidden;
    setConfirmDialog({
      isOpen: true,
      title: nowHidden ? "Hide Datasource" : "Unhide Datasource",
      confirmText: nowHidden ? "Hide" : "Unhide",
      message: nowHidden
        ? `Are you sure you want to hide "${datasource.name}"? This will hide the datasource for your account.`
        : `Are you sure you want to unhide "${datasource.name}"? This will make the datasource visible again for your account.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await toggleDatasourceHidden(datasource.uid, nowHidden);
          toast.success(nowHidden ? "Datasource hidden" : "Datasource visible");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  function openDashboardEditor(dashboard = null) {
    setEditorTab("form");
    setJsonContent("");
    setJsonError("");
    setFileUploaded(false);

    if (dashboard) {
      setEditingDashboard(dashboard);

      setDashboardForm({
        title: dashboard.title || dashboard?.dashboard?.title || "",
        tags:
          dashboard.tags?.join(", ") ||
          (dashboard?.dashboard?.tags || []).join(", ") ||
          "",
        folderId: dashboard.folderId || dashboard?.dashboard?.folderId || 0,
        refresh: dashboard.refresh || dashboard?.dashboard?.refresh || "30s",
        datasourceUid: "",
        useTemplating: false,
        visibility: dashboard.visibility || "private",
        sharedGroupIds:
          dashboard.sharedGroupIds || dashboard.shared_group_ids || [],
      });

      const lightDashboardObj = dashboard?.dashboard || dashboard;
      if (lightDashboardObj) {
        try {
          setJsonContent(JSON.stringify(lightDashboardObj, null, 2));
        } catch (e) {
          /* ignore */
        }
      }

      if (dashboard?.uid) {
        (async () => {
          try {
            const full = await getDashboard(dashboard.uid).catch(() => null);
            if (full?.dashboard) {
              try {
                setJsonContent(JSON.stringify(full.dashboard, null, 2));
                setJsonError("");
                setFileUploaded(false);
              } catch (err) {
                // ignore stringify errors
              }
            }
          } catch (e) {
            /* ignore - leave datasource blank */
          }
        })();
      }
    } else {
      setEditingDashboard(null);
      setDashboardForm({
        title: "",
        tags: "",
        folderId: 0,
        refresh: "30s",
        datasourceUid: "",
        visibility: "private",
        sharedGroupIds: [],
      });
      setJsonContent(JSON.stringify({ title: "", panels: [] }, null, 2));
    }
    setShowDashboardEditor(true);
  }

  async function saveDashboard(jsonOverride = null, options = {}) {
    const selectedDatasource = datasources.find(
      (ds) => ds.uid === dashboardForm.datasourceUid,
    );
    const canSyncDatasourceVisibility =
      Boolean(selectedDatasource?.is_owned) && !Boolean(selectedDatasource?.isDefault);
    const normalizeGroupIds = (ids) =>
      Array.from(
        new Set((Array.isArray(ids) ? ids : []).map((id) => String(id).trim()).filter(Boolean)),
      ).sort();
    const dashboardGroupIds = normalizeGroupIds(dashboardForm.sharedGroupIds);
    const datasourceVisibility = String(
      selectedDatasource?.visibility || "private",
    ).trim();
    const datasourceGroupIds = normalizeGroupIds(
      selectedDatasource?.sharedGroupIds || selectedDatasource?.shared_group_ids,
    );
    const visibilityNeedsSync =
      canSyncDatasourceVisibility &&
      (dashboardForm.visibility !== datasourceVisibility ||
        (dashboardForm.visibility === "group" &&
          JSON.stringify(dashboardGroupIds) !== JSON.stringify(datasourceGroupIds)));

    const {
      syncDatasourceVisibility = false,
      skipVisibilitySyncPrompt = false,
    } = options;

    if (!dashboardForm.datasourceUid) {
      toast.error("Select a default datasource before saving the dashboard");
      return;
    }

    if (!skipVisibilitySyncPrompt && visibilityNeedsSync) {
      const visibilityLabel = (visibility) =>
        visibility === "group"
          ? "Group Shared Workspace"
          : visibility === "tenant"
            ? "Tenant Public Workspace"
            : "Personal Workspace";
      setConfirmDialog({
        isOpen: true,
        title: "Sync Datasource Visibility?",
        message: `Dashboard visibility is set to "${visibilityLabel(
          dashboardForm.visibility,
        )}". Do you want to apply the same visibility to datasource "${
          selectedDatasource?.name || "selected datasource"
        }" as well?`,
        variant: "primary",
        confirmText: "Yes, sync datasource",
        cancelText: "No, dashboard only",
        onConfirm: async () => {
          await saveDashboard(jsonOverride, {
            syncDatasourceVisibility: true,
            skipVisibilitySyncPrompt: true,
          });
        },
        onCancel: async () => {
          await saveDashboard(jsonOverride, {
            syncDatasourceVisibility: false,
            skipVisibilitySyncPrompt: true,
          });
        },
      });
      return;
    }

    try {
      let payload = null;
      if (jsonOverride) {
        let parsed;
        try {
          parsed = JSON.parse(jsonOverride);
          setJsonError("");
        } catch (err) {
          setJsonError(err.message);
          toast.error("Invalid JSON — please fix and try again");
          return;
        }

        payload = {
          dashboard: parsed.dashboard || parsed,
          folderId:
            parsed.folderId || Number.parseInt(dashboardForm.folderId, 10) || 0,
          overwrite:
            parsed.overwrite !== undefined
              ? !!parsed.overwrite
              : !!editingDashboard,
        };
      } else if (editorTab === "json") {
        if (!jsonContent || !jsonContent.trim()) {
          toast.error("JSON content is empty");
          return;
        }
        let parsed;
        try {
          parsed = JSON.parse(jsonContent);
          setJsonError("");
        } catch (err) {
          setJsonError(err.message);
          toast.error("Invalid JSON — please fix and try again");
          return;
        }

        if (parsed.dashboard || parsed?.meta || parsed?.orgId) {
          if (parsed.dashboard) {
            payload = {
              dashboard: parsed.dashboard,
              folderId:
                parsed.folderId ||
                Number.parseInt(dashboardForm.folderId, 10) ||
                0,
              overwrite:
                parsed.overwrite !== undefined
                  ? !!parsed.overwrite
                  : !!editingDashboard,
            };
          } else if (parsed?.meta && parsed.dashboard === undefined) {
            payload = {
              dashboard: parsed,
              folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
              overwrite: !!editingDashboard,
            };
          } else {
            payload = {
              dashboard: parsed,
              folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
              overwrite: !!editingDashboard,
            };
          }
        } else {
          payload = {
            dashboard: parsed,
            folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
            overwrite: !!editingDashboard,
          };
        }
      } else {
        const tags = dashboardForm.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);

        payload = {
          dashboard: {
            title: dashboardForm.title,
            tags,
            refresh: dashboardForm.refresh,
            panels: [],
            timezone: "browser",
            schemaVersion: 16,
            editable: true,
            templating:
              selectedDatasource && dashboardForm.useTemplating
                ? {
                    list: [
                      {
                        name: "ds_default",
                        label: "Datasource",
                        type: "datasource",
                        query: selectedDatasource.type,
                        current: {
                          text: selectedDatasource.name,
                          value: selectedDatasource.uid,
                        },
                      },
                    ],
                  }
                : { list: [] },
          },
          folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
          overwrite: !!editingDashboard,
        };
      }

      if (payload && payload.dashboard && dashboardForm.datasourceUid) {
        payload.dashboard = overrideDashboardDatasource(
          payload.dashboard,
          dashboardForm.datasourceUid,
          datasources,
          Boolean(dashboardForm.useTemplating),
        );
      }

      if (payload && payload.dashboard) {
        const tagsFromForm = dashboardForm.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);
        if (tagsFromForm.length) payload.dashboard.tags = tagsFromForm;
      }

      const params = new URLSearchParams({
        visibility: dashboardForm.visibility,
      });
      if (
        dashboardForm.visibility === "group" &&
        dashboardForm.sharedGroupIds?.length > 0
      ) {
        dashboardForm.sharedGroupIds.forEach((gid) =>
          params.append("shared_group_ids", gid),
        );
      }

      if (editingDashboard) {
        if (payload.dashboard) {
          payload.dashboard.uid = editingDashboard.uid;
          payload.dashboard.id = null;
        }
        await updateDashboard(editingDashboard.uid, payload, params.toString());
        toast.success("Dashboard updated successfully");
      } else {
        if (payload.dashboard) {
          delete payload.dashboard.id;

          if (payload.dashboard.uid) {
            const suffix = Math.random().toString(36).slice(2, 8);
            payload.dashboard.uid = `${String(payload.dashboard.uid)}-${suffix}`;
          } else {
            delete payload.dashboard.uid;
          }
        }

        await createDashboard(payload, params.toString());
        toast.success("Dashboard created successfully");
      }

      if (syncDatasourceVisibility && selectedDatasource?.uid) {
        const dsParams = new URLSearchParams({
          visibility: dashboardForm.visibility,
        });
        if (
          dashboardForm.visibility === "group" &&
          dashboardForm.sharedGroupIds?.length > 0
        ) {
          dashboardForm.sharedGroupIds.forEach((gid) =>
            dsParams.append("shared_group_ids", gid),
          );
        }
        try {
          await updateDatasource(selectedDatasource.uid, {}, dsParams.toString());
          toast.success("Datasource visibility synced with dashboard");
        } catch (syncErr) {
          toast.error(
            "Dashboard saved, but datasource visibility sync did not complete.",
          );
          handleApiError(syncErr);
        }
      }

      setShowDashboardEditor(false);
      loadData();
    } catch (e) {
      handleApiError(e);
    }
  }

  function handleDeleteDashboard(dashboard) {
    setConfirmDialog({
      isOpen: true,
      title: "Delete Dashboard",
      message: `Are you sure you want to delete "${dashboard.title}"? This action cannot be undone.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await deleteDashboard(dashboard.uid);
          toast.success("Dashboard deleted successfully");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  function openDatasourceEditor(datasource = null) {
    if (datasource) {
      const jsonData = getDatasourceJsonData(datasource);
      const selectedApiKeyId = String(jsonData.watchdogApiKeyId || "").trim();
      const selectedScopeKey = String(jsonData.watchdogScopeKey || "").trim();
      const currentOrg = datasource.orgId || datasource.org_id || "";
      const byScopeKey = (user?.api_keys || []).find(
        (k) => String(k.key || "") === selectedScopeKey,
      );
      const matchedKey = (user?.api_keys || []).find(
        (k) => String(k.key) === String(currentOrg),
      );
      const matchedById = findApiKeyById(user?.api_keys || [], currentOrg);
      setEditingDatasource(datasource);
      setDatasourceForm({
        name: datasource.name || "",
        type: datasource.type || "prometheus",
        url: datasource.url || "",
        isDefault: datasource.isDefault || false,
        access: datasource.access || "proxy",
        visibility: datasource.visibility || datasource.visibility || "private",
        sharedGroupIds:
          datasource.sharedGroupIds || datasource.shared_group_ids || [],
        apiKeyId:
          selectedApiKeyId ||
          byScopeKey?.id ||
          matchedKey?.id ||
          matchedById?.id ||
          "",
      });
    } else {
      const dk =
        (user?.api_keys || []).find((k) => k.is_default) ||
        (user?.api_keys || [])[0];
      setEditingDatasource(null);
      setDatasourceForm({
        name: "Mimir",
        type: "prometheus",
        url: MIMIR_PROMETHEUS_URL,
        isDefault: false,
        access: "proxy",
        visibility: "private",
        sharedGroupIds: [],
        apiKeyId: dk?.id || "",
      });
    }
    setShowDatasourceEditor(true);
  }

  async function saveDatasource() {
    const isMultiTenantType = ["prometheus", "loki", "tempo"].includes(
      datasourceForm.type,
    );
    if (isMultiTenantType && !datasourceForm.apiKeyId) {
      toast.error(
        "API key is required for Prometheus, Loki, and Tempo datasources",
      );
      return;
    }

    try {
      const payload = {
        name: datasourceForm.name,
        type: datasourceForm.type,
        url: datasourceForm.url,
        access: datasourceForm.access,
        isDefault: datasourceForm.isDefault,
        jsonData: {},
      };

      if (isMultiTenantType) {
        const selectedKey = (user?.api_keys || []).find(
          (k) => String(k?.id || "") === String(datasourceForm.apiKeyId || ""),
        );
        payload.org_id = selectedKey?.key || user?.org_id || "default";
        payload.jsonData = {
          ...payload.jsonData,
          watchdogApiKeyId: datasourceForm.apiKeyId,
          watchdogApiKeyName: String(selectedKey?.name || "").trim(),
          watchdogScopeKey: payload.org_id,
        };
      }

      const params = new URLSearchParams({
        visibility: datasourceForm.visibility,
      });
      if (
        datasourceForm.visibility === "group" &&
        datasourceForm.sharedGroupIds?.length > 0
      ) {
        datasourceForm.sharedGroupIds.forEach((gid) =>
          params.append("shared_group_ids", gid),
        );
      }

      if (editingDatasource) {
        await updateDatasource(
          editingDatasource.uid,
          payload,
          params.toString(),
        );
        toast.success("Datasource updated successfully");
      } else {
        await createDatasource(payload, params.toString());
        toast.success("Datasource created successfully");
      }

      setShowDatasourceEditor(false);
      loadData();
    } catch (e) {
      handleApiError(e);
    }
  }

  async function findDatasourceLinkedDashboards(datasource) {
    const targetUid = String(datasource?.uid || "");
    if (!targetUid) return [];

    const dashboardSummaries = await searchDashboards({
      showHidden: true,
    }).catch(() => []);
    if (!Array.isArray(dashboardSummaries) || dashboardSummaries.length === 0) {
      return [];
    }

    const details = await Promise.allSettled(
      dashboardSummaries
        .filter((dashboard) => dashboard?.uid)
        .map(async (dashboard) => {
          const full = await getDashboard(dashboard.uid);
          const dashboardBody = full?.dashboard || full;
          const refs = new Set();
          collectDatasourceReferences(dashboardBody, refs);
          const normalizedRefs = new Set(
            Array.from(refs).map(
              (ref) => resolveToUid(ref, datasources) || String(ref),
            ),
          );

          if (!normalizedRefs.has(targetUid)) return null;

          return {
            uid: dashboard.uid,
          };
        }),
    );

    return details
      .filter((result) => result.status === "fulfilled" && result.value)
      .map((result) => result.value);
  }

  async function handleDeleteDatasource(datasource) {
    let linkedDashboards = [];
    let linkageCheckFailed = false;

    try {
      linkedDashboards = await findDatasourceLinkedDashboards(datasource);
    } catch {
      linkageCheckFailed = true;
    }

    const linkedCount = linkedDashboards.length;

    setConfirmDialog({
      isOpen: true,
      title:
        linkedCount > 0
          ? "Datasource Linked to Dashboards"
          : "Delete Datasource",
      confirmText: linkedCount > 0 ? "Delete Anyway" : "Delete",
      message: linkageCheckFailed
        ? `Could not verify whether "${datasource.name}" is linked to dashboards. Dashboards will not be deleted, but they may become dangling and queries may fail. Do you still want to continue?`
        : linkedCount > 0
          ? `"${datasource.name}" is linked to dashboard${linkedCount !== 1 ? "s" : ""}. Dashboards won't be deleted, but they will be dangling and queries can break. Do you still want to continue?`
          : `Are you sure you want to delete "${datasource.name}"? This action cannot be undone.`,
      messageTone: linkedCount > 0 || linkageCheckFailed ? "danger" : "default",
      variant: "danger",
      onConfirm: async () => {
        try {
          await deleteDatasource(datasource.uid);
          toast.success("Datasource deleted successfully");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  async function handleViewDatasourceMetrics(datasource) {
    const datasourceName = String(datasource?.name || "Datasource");
    const { key: resolvedKey, keyName } = resolveDatasourceKeyMeta(datasource);
    const resolvedKeyName = keyName || "Default";

    setDatasourceMetricsDialog({
      isOpen: true,
      datasourceName,
      keyName: resolvedKeyName,
      loading: true,
      error: "",
      metrics: [],
    });

    try {
      const resp = await listMetricNames(resolvedKey || undefined);
      const metrics = Array.isArray(resp?.metrics) ? resp.metrics : [];
      setDatasourceMetricsDialog((prev) => ({
        ...prev,
        loading: false,
        metrics: metrics.slice().sort((a, b) => a.localeCompare(b)),
      }));
    } catch (e) {
      const msg =
        e?.body?.detail ||
        e?.body?.message ||
        e?.message ||
        "Failed to load metric names";
      setDatasourceMetricsDialog((prev) => ({
        ...prev,
        loading: false,
        error: msg,
      }));
    }
  }

  function openFolderEditor(folder = null) {
    if (folder) {
      setEditingFolder(folder);
      setFolderName(folder.title || "");
      setFolderVisibility(folder.visibility || "private");
      setFolderSharedGroupIds(folder.sharedGroupIds || folder.shared_group_ids || []);
      setAllowDashboardWrites(
        Boolean(
          folder.allowDashboardWrites ?? folder.allow_dashboard_writes ?? false,
        ),
      );
    } else {
      setEditingFolder(null);
      setFolderName("");
      setFolderVisibility("private");
      setFolderSharedGroupIds([]);
      setAllowDashboardWrites(false);
    }
    setShowFolderCreator(true);
  }

  async function handleCreateFolder() {
    if (!folderName.trim()) return;
    try {
      const params = new URLSearchParams({
        visibility: folderVisibility,
      });
      if (folderVisibility === "group" && folderSharedGroupIds.length > 0) {
        folderSharedGroupIds.forEach((gid) =>
          params.append("shared_group_ids", gid),
        );
      }
      if (editingFolder?.uid) {
        await updateFolder(
          editingFolder.uid,
          {
            title: folderName.trim(),
            allowDashboardWrites: allowDashboardWrites,
          },
          params.toString(),
        );
        toast.success("Folder updated successfully");
      } else {
        await createFolder(
          folderName.trim(),
          params.toString(),
          allowDashboardWrites,
        );
        toast.success("Folder created successfully");
      }
      setShowFolderCreator(false);
      setEditingFolder(null);
      setFolderName("");
      setFolderVisibility("private");
      setFolderSharedGroupIds([]);
      setAllowDashboardWrites(false);
      loadData();
    } catch (e) {
      handleApiError(e);
    }
  }

  function handleDeleteFolder(folder) {
    setConfirmDialog({
      isOpen: true,
      title: "Delete Folder",
      message: `Are you sure you want to delete "${folder.title}"? All dashboards in this folder will be moved to General.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await deleteFolder(folder.uid);
          toast.success("Folder deleted successfully");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  async function handleToggleFolderHidden(folder) {
    const nowHidden = !folder.is_hidden;
    setConfirmDialog({
      isOpen: true,
      title: nowHidden ? "Hide Folder" : "Unhide Folder",
      confirmText: nowHidden ? "Hide" : "Unhide",
      message: nowHidden
        ? `Are you sure you want to hide "${folder.title}"? This will hide the folder and its dashboards for your account.`
        : `Are you sure you want to unhide "${folder.title}"? This will make the folder visible again for your account.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await toggleFolderHidden(folder.uid, nowHidden);
          toast.success(nowHidden ? "Folder hidden" : "Folder visible");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  function getDatasourceIcon(type) {
    const found = DATASOURCE_TYPES.find((t) => t.value === type);
    return found ? found.icon : "🔧";
  }

  const hasActiveFilters = Boolean(
    String(filters?.teamId || "").trim() ||
      (activeTab === "dashboards" &&
        String(filters?.folderKey || "").trim() &&
        String(filters?.folderKey || "").trim() !== "__general__") ||
      Boolean(filters?.showHidden),
  );

  return (
    <div className="animate-fade-in grafana-page">
      <PageHeader
        icon="stacked_bar_chart"
        title="Grafana"
        subtitle={`Create and manage dashboards, datasources, and folders.`}
      >
        <Button
          onClick={() => openInGrafana("/")}
          size="sm"
          className="flex items-center gap-2"
          title="Open Grafana in new tab"
        >
          <span className="material-icons text-sm">open_in_new</span>
          Open Grafana
        </Button>
      </PageHeader>

      <GrafanaTabs activeTab={activeTab} onChange={setActiveTab} />

      <GrafanaContent
        loading={loading}
        activeTab={activeTab}
        dashboards={dashboards}
        datasources={datasources}
        folders={folders}
        groups={groups}
        query={query}
        setQuery={setQuery}
        filters={filters}
        setFilters={setFilters}
        onSearch={onSearch}
        onClearFilters={clearFilters}
        hasActiveFilters={hasActiveFilters}
        openDashboardEditor={openDashboardEditor}
        onOpenGrafana={openInGrafana}
        onDeleteDashboard={handleDeleteDashboard}
        onToggleDashboardHidden={handleToggleDashboardHidden}
        onReorderDashboards={handleReorderDashboards}
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={handleDeleteDatasource}
        onToggleDatasourceHidden={handleToggleDatasourceHidden}
        onViewDatasourceMetrics={handleViewDatasourceMetrics}
        onReorderDatasources={handleReorderDatasources}
        getDatasourceIcon={getDatasourceIcon}
        getDatasourceKeyName={(datasource) =>
          resolveDatasourceKeyMeta(datasource).keyName
        }
        dashboardKeyNamesByUid={dashboardKeyNamesByUid}
        onCreateFolder={() => openFolderEditor(null)}
        onEditFolder={openFolderEditor}
        onDeleteFolder={handleDeleteFolder}
        onToggleFolderHidden={handleToggleFolderHidden}
        onReorderFolders={handleReorderFolders}
      />

      <DashboardEditorModal
        isOpen={showDashboardEditor}
        onClose={() => setShowDashboardEditor(false)}
        editingDashboard={editingDashboard}
        dashboardForm={dashboardForm}
        setDashboardForm={setDashboardForm}
        editorTab={editorTab}
        setEditorTab={setEditorTab}
        jsonContent={jsonContent}
        setJsonContent={setJsonContent}
        jsonError={jsonError}
        setJsonError={setJsonError}
        fileUploaded={fileUploaded}
        setFileUploaded={setFileUploaded}
        folders={folders}
        datasources={datasources}
        groups={groups}
        onSave={saveDashboard}
      />

      <DatasourceEditorModal
        isOpen={showDatasourceEditor}
        onClose={() => setShowDatasourceEditor(false)}
        editingDatasource={editingDatasource}
        datasourceForm={datasourceForm}
        setDatasourceForm={setDatasourceForm}
        user={user}
        groups={groups}
        onSave={saveDatasource}
      />

      <FolderCreatorModal
        isOpen={showFolderCreator}
        onClose={() => {
          setShowFolderCreator(false);
          setEditingFolder(null);
          setFolderName("");
          setFolderVisibility("private");
          setFolderSharedGroupIds([]);
          setAllowDashboardWrites(false);
        }}
        editingFolder={editingFolder}
        folderName={folderName}
        setFolderName={setFolderName}
        folderVisibility={folderVisibility}
        setFolderVisibility={setFolderVisibility}
        folderSharedGroupIds={folderSharedGroupIds}
        setFolderSharedGroupIds={setFolderSharedGroupIds}
        allowDashboardWrites={allowDashboardWrites}
        setAllowDashboardWrites={setAllowDashboardWrites}
        groups={groups}
        onCreate={handleCreateFolder}
      />

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        onClose={() => {
          const onCancel = confirmDialog.onCancel;
          setConfirmDialog((prev) => ({
            ...prev,
            isOpen: false,
            onConfirm: null,
            onCancel: null,
          }));
          if (typeof onCancel === "function") {
            void onCancel();
          }
        }}
        onConfirm={confirmDialog.onConfirm || (() => {})}
        title={confirmDialog.title}
        message={confirmDialog.message}
        messageTone={confirmDialog.messageTone || "default"}
        variant={confirmDialog.variant || "danger"}
        confirmText={confirmDialog.confirmText || "Delete"}
        cancelText={confirmDialog.cancelText || "Cancel"}
      />

      <ConfirmDialog
        isOpen={grafanaConfirmDialog.isOpen}
        onClose={() => setGrafanaConfirmDialog({ isOpen: false, path: null })}
        onConfirm={confirmOpenInGrafana}
        title="Open in Grafana"
        message="This will proxy through Watchdog to get a secure, scoped, authenticated, and restricted view of what you can view and share under Grafana. If you want full admin access, please contact an admin and you can log into Grafana directly with a different username and password."
        variant="primary"
        confirmText="Continue to Grafana"
        cancelText="Cancel"
      />

      <Modal
        isOpen={datasourceMetricsDialog.isOpen}
        onClose={() =>
          setDatasourceMetricsDialog({
            isOpen: false,
            datasourceName: "",
            keyName: "",
            loading: false,
            error: "",
            metrics: [],
          })
        }
        title={`Metrics: ${datasourceMetricsDialog.datasourceName}`}
        size="md"
        footer={
          <div className="flex justify-end">
            <Button
              variant="ghost"
              onClick={() =>
                setDatasourceMetricsDialog({
                  isOpen: false,
                  datasourceName: "",
                  keyName: "",
                  loading: false,
                  error: "",
                  metrics: [],
                })
              }
            >
              Close
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-400/45 bg-indigo-500/15 px-2.5 py-1 text-xs font-semibold text-indigo-300">
              <span className="material-icons text-[13px] leading-none">
                key
              </span>
              Key: {datasourceMetricsDialog.keyName || "Default"}
            </span>
          </div>
          {datasourceMetricsDialog.loading ? (
            <div className="py-6">
              <Spinner size="md" />
            </div>
          ) : datasourceMetricsDialog.error ? (
            <div className="text-sm text-red-500">{datasourceMetricsDialog.error}</div>
          ) : datasourceMetricsDialog.metrics.length === 0 ? (
            <div className="text-sm text-sre-text-muted">No metrics found.</div>
          ) : (
            <div className="max-h-80 overflow-auto border border-sre-border rounded-lg bg-sre-bg-alt">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-sre-surface border-b border-sre-border">
                  <tr>
                    <th className="text-left px-3 py-2 text-sre-text-muted font-semibold w-16">
                      #
                    </th>
                    <th className="text-left px-3 py-2 text-sre-text-muted font-semibold">
                      Metric Name
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {datasourceMetricsDialog.metrics.map((name, index) => (
                    <tr
                      key={name}
                      className="border-b border-sre-border/40 hover:bg-sre-surface/50"
                    >
                      <td className="px-3 py-2 text-sre-text-subtle tabular-nums">
                        {index + 1}
                      </td>
                      <td className="px-3 py-2 font-mono text-sre-text break-all">
                        {name}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
