import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import PropTypes from "prop-types";
import { Button, Input, Select, Textarea } from "../ui";
import RuleEditorWizard from "./RuleEditorWizard";
import HelpTooltip from "../HelpTooltip";
import { useAuth } from "../../contexts/AuthContext";
import {
  evaluatePromql,
  getGroups,
  listMetricLabelValues,
  listMetricLabels,
  listMetricNames,
  testAlertRule,
} from "../../api";
import {
  DEFAULT_FORM,
  RULE_TEMPLATES,
  validateRuleForm,
  createLabelPairsFromRule,
} from "./ruleEditorUtils";
import { normalizeRuleOrgId } from "../../utils/alertmanagerRuleUtils";

const CONDITION_OPERATORS = [">", ">=", "<", "<=", "==", "!="];
const CONDITION_JOIN_OPERATORS = ["and", "or"];

export default function RuleEditor({
  rule,
  channels,
  apiKeys = [],
  availableCorrelationIds = [],
  onSave,
  onCancel,
}) {
  const MAX_CORRELATION_ID_LENGTH = 10;
  const { hasPermission, user } = useAuth();
  const canReadChannels = hasPermission("read:channels");
  const AUTO_SCOPE = "__auto__";

  const [formData, setFormData] = useState(rule || DEFAULT_FORM);
  const [groups, setGroups] = useState([]);
  const [selectedGroups, setSelectedGroups] = useState(
    new Set(rule?.sharedGroupIds || rule?.shared_group_ids || []),
  );
  const [metricNames, setMetricNames] = useState([]);
  const [metricLabels, setMetricLabels] = useState([]);
  const [metricFilter, setMetricFilter] = useState("");
  const [loadingMetrics, setLoadingMetrics] = useState(false);
  const [metricsError, setMetricsError] = useState(null);
  const [promqlPreview, setPromqlPreview] = useState({
    loading: false,
    valid: null,
    error: "",
    currentValue: null,
    sampleCount: 0,
    resultType: null,
  });
  const [promqlSuggestions, setPromqlSuggestions] = useState([]);
  const [labelValuesCache, setLabelValuesCache] = useState({});
  const [labelPairs, setLabelPairs] = useState(() =>
    createLabelPairsFromRule(rule),
  );
  const [validationErrors, setValidationErrors] = useState({});
  const [validationWarnings, setValidationWarnings] = useState([]);
  const [saveError, setSaveError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [currentStep, setCurrentStep] = useState(0);
  const totalSteps = 4;
  const [issuesCollapsed, setIssuesCollapsed] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [queryMode, setQueryMode] = useState("promql");
  const [builderUseRate, setBuilderUseRate] = useState(false);
  const [builderRateWindow, setBuilderRateWindow] = useState("5m");
  const [builderConditions, setBuilderConditions] = useState([
    {
      id: Math.random().toString(36).slice(2, 9),
      joinWithPrev: "and",
      metric: "",
      operator: ">",
      value: "",
    },
  ]);
  const [correlationMode, setCorrelationMode] = useState("existing");
  // helper to generate random correlation IDs (uses crypto.randomUUID when available)
  const generateCorrelationId = () => {
    const id = (
      (typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID().replace(/-/g, "")
        : Math.random().toString(36).slice(2))
    ).slice(0, MAX_CORRELATION_ID_LENGTH);
    setCorrelationMode("custom");
    setFormData((prev) => ({ ...prev, group: id }));
  };
  const [selectedApiScopes, setSelectedApiScopes] = useState([AUTO_SCOPE]);
  const isMountedRef = useRef(true);
  const metricsLoadRequestRef = useRef(0);
  const visibleApiKeys = useMemo(
    () =>
      (apiKeys || []).filter(
        (k) => !(k?.is_hidden || k?.isHidden),
      ),
    [apiKeys],
  );
  const visibleApiScopeValues = useMemo(
    () =>
      visibleApiKeys
        .map((k) => String(k?.key || "").trim())
        .filter(Boolean),
    [visibleApiKeys],
  );
  const ruleOwnerId = String(
    rule?.createdBy || rule?.created_by || "",
  ).trim();
  const isRuleOwner = ruleOwnerId && String(user?.id || "").trim() === ruleOwnerId;
  const selectedExplicitApiScopes = selectedApiScopes.filter(
    (id) => id !== AUTO_SCOPE,
  );
  const hasExplicitApiScope = selectedExplicitApiScopes.length > 0;
  const hasHiddenSelectedApiScope = selectedExplicitApiScopes.some(
    (scope) => !visibleApiScopeValues.includes(scope),
  );
  const showOwnerScopeHiddenHint = Boolean(
    rule &&
      ruleOwnerId &&
      !isRuleOwner &&
      (!hasExplicitApiScope || hasHiddenSelectedApiScope),
  );
  const activeApiScope = useMemo(() => {
    const visible = (apiKeys || []).filter((k) => !(k?.is_hidden || k?.isHidden));
    const enabled = visible.find((k) => k?.is_enabled);
    const fallbackDefault = visible.find((k) => k?.is_default);
    const fallbackFirst = visible[0];
    return String(
      enabled?.key || fallbackDefault?.key || fallbackFirst?.key || "",
    ).trim();
  }, [apiKeys]);
  const metricsOrgScope = useMemo(() => {
    const explicitScope = selectedExplicitApiScopes[0];
    if (explicitScope) return String(explicitScope).trim();
    const normalizedRuleOrg = normalizeRuleOrgId(formData.orgId);
    if (normalizedRuleOrg) return normalizedRuleOrg;
    return activeApiScope || undefined;
  }, [selectedExplicitApiScopes, formData.orgId, activeApiScope]);
  const metricsScopeLabel = useMemo(() => {
    if (!metricsOrgScope) return "default";
    const matched = (apiKeys || []).find(
      (k) => String(k?.key || "").trim() === String(metricsOrgScope || "").trim(),
    );
    return matched?.name || `${String(metricsOrgScope).slice(0, 8)}...`;
  }, [metricsOrgScope, apiKeys]);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);
  const promqlFunctionHints = useMemo(
    () => [
      "rate(",
      "irate(",
      "increase(",
      "sum(",
      "sum by (",
      "avg(",
      "avg by (",
      "max(",
      "min(",
      "topk(",
      "bottomk(",
      "histogram_quantile(",
      "clamp_min(",
      "absent_over_time(",
    ],
    [],
  );
  const promqlAutocompleteContext = useMemo(() => {
    const expr = String(formData.expr || "");
    const cursor = expr.length;
    const beforeCursor = expr.slice(0, cursor);
    const tokenMatch = beforeCursor.match(/([a-zA-Z_:][a-zA-Z0-9_:]*)$/);
    const defaultToken = String(tokenMatch?.[1] || "");
    const openBraceIndex = beforeCursor.lastIndexOf("{");
    const closeBraceIndex = beforeCursor.lastIndexOf("}");

    if (openBraceIndex <= closeBraceIndex) {
      return {
        mode: "metricOrFunction",
        token: defaultToken,
        segmentStart: cursor - defaultToken.length,
      };
    }

    const selectorStart = openBraceIndex + 1;
    const selectorText = beforeCursor.slice(selectorStart);
    const lastCommaInSelector = selectorText.lastIndexOf(",");
    const segmentStart = selectorStart + (lastCommaInSelector >= 0 ? lastCommaInSelector + 1 : 0);
    const rawSegment = beforeCursor.slice(segmentStart);
    const leadingWhitespace = rawSegment.length - rawSegment.trimStart().length;
    const segmentTrimmedStart = segmentStart + leadingWhitespace;
    const segmentText = rawSegment.trimStart();

    const metricMatch = beforeCursor
      .slice(0, openBraceIndex)
      .match(/([a-zA-Z_:][a-zA-Z0-9_:]*)\s*$/);
    const metricName = String(metricMatch?.[1] || "");

    const previousSegments = selectorText
      .slice(0, Math.max(lastCommaInSelector, 0))
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    const existingLabelKeys = new Set(
      previousSegments
        .map((part) => {
          const m = part.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\s*(=|!=|=~|!~)/);
          return m ? m[1] : "";
        })
        .filter(Boolean),
    );

    const opMatch = segmentText.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|=|!=)\s*(.*)$/);
    if (opMatch) {
      const labelKey = opMatch[1];
      const operator = opMatch[2];
      const rawValue = String(opMatch[3] || "");
      const valueToken = rawValue
        .replace(/^"/, "")
        .replace(/".*$/, "")
        .trim();
      return {
        mode: "labelValue",
        token: valueToken,
        segmentStart: segmentTrimmedStart,
        labelKey,
        operator,
        metricName,
      };
    }

    const keyTokenMatch = segmentText.match(/^([a-zA-Z_][a-zA-Z0-9_]*)?$/);
    const keyToken = String(keyTokenMatch?.[1] || "");
    return {
      mode: "labelKey",
      token: keyToken,
      segmentStart: segmentTrimmedStart,
      metricName,
      existingLabelKeys,
    };
  }, [formData.expr]);

  useEffect(() => {
    loadGroups();
  }, []);

  useEffect(() => {
    setFormData(rule || DEFAULT_FORM);
    setLabelPairs(createLabelPairsFromRule(rule));
    const incomingGroups = Array.isArray(rule?.sharedGroupIds)
      ? rule.sharedGroupIds
      : Array.isArray(rule?.shared_group_ids)
        ? rule.shared_group_ids
        : [];
    setSelectedGroups(new Set(incomingGroups));
  }, [rule]);

  const buildCompositeExprFromBuilder = useCallback((
    conditions = [],
    useRate = false,
    rateWindow = "5m",
  ) => {
    const normalized = (conditions || [])
      .map((row) => ({
        ...row,
        metric: String(row?.metric || "").trim(),
        operator: String(row?.operator || ">").trim(),
        value: String(row?.value || "").trim(),
        joinWithPrev: String(row?.joinWithPrev || "and").trim().toLowerCase(),
      }))
      .filter((row) => row.metric && row.operator && row.value);

    if (!normalized.length) return "";

    const safeWindow = String(rateWindow || "").trim() || "5m";

    return normalized
      .map((row, index) => {
        const metricExpr = useRate
          ? `rate(${row.metric}[${safeWindow}])`
          : row.metric;
        const exprPart = `(${metricExpr} ${row.operator} ${row.value})`;
        if (index === 0) return exprPart;
        const joiner = CONDITION_JOIN_OPERATORS.includes(row.joinWithPrev)
          ? row.joinWithPrev.toUpperCase()
          : "AND";
        return `${joiner} ${exprPart}`;
      })
      .join(" ");
  }, []);

  useEffect(() => {
    if (queryMode !== "builder") return;
    const nextExpr = buildCompositeExprFromBuilder(
      builderConditions,
      builderUseRate,
      builderRateWindow,
    );
    if (!nextExpr) return;
    setFormData((prev) => (prev.expr === nextExpr ? prev : { ...prev, expr: nextExpr }));
  }, [queryMode, builderConditions, builderUseRate, builderRateWindow, buildCompositeExprFromBuilder]);

  useEffect(() => {
    const rawOrg = String((rule || DEFAULT_FORM)?.orgId || "").trim();
    if (!rawOrg) {
      // default to auto scope only
      setSelectedApiScopes([AUTO_SCOPE]);
      return;
    }
    setSelectedApiScopes([rawOrg]);
  }, [rule, visibleApiScopeValues]);

  useEffect(() => {
    if (labelPairs.length === 0) return;
    const nextLabels = {};
    labelPairs.forEach(({ key, value }) => {
      const trimmed = key.trim();
      if (trimmed) nextLabels[trimmed] = value;
    });
    setFormData((prev) => {
      const prevLabels = prev.labels || {};
      const same =
        Object.keys(prevLabels).length === Object.keys(nextLabels).length &&
        Object.keys(nextLabels).every((k) => prevLabels[k] === nextLabels[k]);
      return same ? prev : { ...prev, labels: nextLabels };
    });
  }, [labelPairs, formData.labels]);

  useEffect(() => {
    const matchingTemplate = RULE_TEMPLATES.find(
      (template) =>
        template.expr === formData.expr &&
        template.duration === formData.duration &&
        template.summary === formData.annotations?.summary &&
        template.description === formData.annotations?.description,
    );
    setSelectedTemplate(matchingTemplate?.id || null);
  }, [formData.expr, formData.duration, formData.annotations]);

  const loadGroups = async () => {
    try {
      const groupsData = await getGroups();
      setGroups(groupsData);
    } catch {
      // Silently handle
    }
  };

  useEffect(() => {
    const { errors, warnings } = validateRuleForm(formData, labelPairs);
    setValidationErrors(errors);
    setValidationWarnings(warnings);
  }, [formData, labelPairs]);

  const loadMetrics = useCallback(async () => {
    const requestId = metricsLoadRequestRef.current + 1;
    metricsLoadRequestRef.current = requestId;
    setLoadingMetrics(true);
    setMetricsError(null);
    try {
      const resp = await listMetricNames(metricsOrgScope);
      if (!isMountedRef.current || requestId !== metricsLoadRequestRef.current) return;
      setMetricNames(Array.isArray(resp.metrics) ? resp.metrics : []);
    } catch (e) {
      if (!isMountedRef.current || requestId !== metricsLoadRequestRef.current) return;
      setMetricsError(e.message || "Failed to load metrics from Mimir");
      setMetricNames([]);
    } finally {
      if (isMountedRef.current && requestId === metricsLoadRequestRef.current) {
        setLoadingMetrics(false);
      }
    }
  }, [metricsOrgScope]);

  useEffect(() => {
    if (queryMode !== "promql") return;
    if (metricNames.length > 0 || loadingMetrics || metricsError) return;
    if (!metricsOrgScope) return;
    loadMetrics();
  }, [queryMode, metricNames.length, loadingMetrics, metricsError, metricsOrgScope, loadMetrics]);

  useEffect(() => {
    if (queryMode !== "promql") return;
    if (metricLabels.length > 0 || !metricsOrgScope) return;
    let cancelled = false;
    (async () => {
      try {
        const resp = await listMetricLabels(metricsOrgScope);
        if (cancelled) return;
        setMetricLabels(Array.isArray(resp?.labels) ? resp.labels : []);
      } catch {
        if (!cancelled) setMetricLabels([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [queryMode, metricLabels.length, metricsOrgScope]);

  useEffect(() => {
    if (queryMode !== "promql") return;
    if (promqlAutocompleteContext.mode !== "labelValue") return;
    if (!metricsOrgScope || !promqlAutocompleteContext.labelKey) return;
    const cacheKey = `${promqlAutocompleteContext.labelKey}::${promqlAutocompleteContext.metricName || "*"}`;
    if (labelValuesCache[cacheKey]) return;

    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const resp = await listMetricLabelValues(
          promqlAutocompleteContext.labelKey,
          metricsOrgScope,
          { metricName: promqlAutocompleteContext.metricName || undefined },
        );
        if (cancelled) return;
        setLabelValuesCache((prev) => ({
          ...prev,
          [cacheKey]: Array.isArray(resp?.values) ? resp.values : [],
        }));
      } catch {
        if (cancelled) return;
        setLabelValuesCache((prev) => ({ ...prev, [cacheKey]: [] }));
      }
    }, 200);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [queryMode, promqlAutocompleteContext, metricsOrgScope, labelValuesCache]);

  useEffect(() => {
    if (queryMode !== "promql") {
      setPromqlSuggestions([]);
      return;
    }

    const token = String(promqlAutocompleteContext.token || "").toLowerCase();

    if (promqlAutocompleteContext.mode === "labelKey") {
      const usedKeys = promqlAutocompleteContext.existingLabelKeys || new Set();
      const keyHints = metricLabels
        .filter((label) => {
          const v = String(label || "");
          if (!v || v === "__name__") return false;
          if (usedKeys.has(v)) return false;
          return token.length === 0 || v.toLowerCase().startsWith(token);
        })
        .slice(0, 12)
        .map((value) => ({ value, type: "labelKey" }));
      setPromqlSuggestions(keyHints);
      return;
    }

    if (promqlAutocompleteContext.mode === "labelValue") {
      const cacheKey = `${promqlAutocompleteContext.labelKey}::${promqlAutocompleteContext.metricName || "*"}`;
      const values = labelValuesCache[cacheKey] || [];
      const valueHints = values
        .filter((value) => {
          const v = String(value || "");
          return token.length === 0 || v.toLowerCase().startsWith(token);
        })
        .slice(0, 12)
        .map((value) => ({ value, type: "labelValue" }));
      setPromqlSuggestions(valueHints);
      return;
    }

    if (!token || token.length < 2) {
      setPromqlSuggestions([]);
      return;
    }
    const metricHints = metricNames
      .filter((name) => name.toLowerCase().startsWith(token))
      .slice(0, 8)
      .map((value) => ({ value, type: "metric" }));
    const fnHints = promqlFunctionHints
      .filter((hint) => hint.toLowerCase().startsWith(token))
      .slice(0, 4)
      .map((value) => ({ value, type: "function" }));
    const merged = Array.from(new Map([...metricHints, ...fnHints].map((s) => [s.value, s])).values()).slice(0, 10);
    setPromqlSuggestions(merged);
  }, [queryMode, promqlAutocompleteContext, metricLabels, labelValuesCache, metricNames, promqlFunctionHints]);

  useEffect(() => {
    if (queryMode !== "promql") {
      setPromqlPreview({
        loading: false,
        valid: null,
        error: "",
        currentValue: null,
        sampleCount: 0,
        resultType: null,
      });
      return;
    }
    const expr = String(formData.expr || "").trim();
    if (!expr || expr.length < 3 || !metricsOrgScope) {
      setPromqlPreview({
        loading: false,
        valid: null,
        error: "",
        currentValue: null,
        sampleCount: 0,
        resultType: null,
      });
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setPromqlPreview((prev) => ({ ...prev, loading: true }));
      try {
        const res = await evaluatePromql(expr, metricsOrgScope, {
          sampleLimit: 5,
          signal: controller.signal,
        });
        setPromqlPreview({
          loading: false,
          valid: Boolean(res?.valid),
          error: String(res?.error || ""),
          currentValue: res?.currentValue ?? null,
          sampleCount: Number(res?.sampleCount || 0),
          resultType: String(res?.resultType || ""),
        });
      } catch (e) {
        if (controller.signal.aborted) return;
        setPromqlPreview({
          loading: false,
          valid: false,
          error: String(e?.message || "Failed to validate query"),
          currentValue: null,
          sampleCount: 0,
          resultType: null,
        });
      }
    }, 500);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [formData.expr, metricsOrgScope, queryMode]);

  const filteredMetricNames = useMemo(() => {
    if (!metricFilter) return metricNames;
    const q = metricFilter.toLowerCase();
    return metricNames.filter((name) => name.toLowerCase().includes(q));
  }, [metricNames, metricFilter]);

  useEffect(() => {
    const explicitScopes = selectedApiScopes.filter((id) => id !== AUTO_SCOPE);
    const hasAutoScope = selectedApiScopes.includes(AUTO_SCOPE);
    setFormData((prev) => {
      const autoResolvedScope = hasAutoScope ? String(activeApiScope || "").trim() : "";
      const nextOrgId = explicitScopes[0] || autoResolvedScope || "";
      const nextOrgIds = explicitScopes.length > 0
        ? explicitScopes
        : autoResolvedScope
          ? [autoResolvedScope]
          : [];
      const prevOrgId = String(prev.orgId || "");
      const prevOrgIds = Array.isArray(prev.orgIds) ? prev.orgIds : [];
      const sameOrgId = prevOrgId === nextOrgId;
      const sameOrgIds =
        prevOrgIds.length === nextOrgIds.length &&
        prevOrgIds.every((value, index) => String(value || "") === String(nextOrgIds[index] || ""));
      if (sameOrgId && sameOrgIds) return prev;
      return { ...prev, orgId: nextOrgId, orgIds: nextOrgIds };
    });
  }, [selectedApiScopes, activeApiScope]);

  const correlationIdOptions = useMemo(
    () => {
      const values = new Set(
        (availableCorrelationIds || [])
          .map((item) => String(item || "").trim())
          .filter(Boolean),
      );
      values.add("default");
      return Array.from(values).sort((a, b) => a.localeCompare(b));
    },
    [availableCorrelationIds],
  );

  useEffect(() => {
    const current = String(formData.group || "").trim();
    if (!current || correlationIdOptions.includes(current)) {
      setCorrelationMode("existing");
      return;
    }
    setCorrelationMode("custom");
  }, [formData.group, correlationIdOptions]);

  const effectiveLabels = useMemo(
    () => ({
      ...(formData.labels || {}),
      severity: formData.severity,
    }),
    [formData.labels, formData.severity],
  );

  const toggleGroup = (groupId) => {
    const newGroups = new Set(selectedGroups);
    if (newGroups.has(groupId)) {
      newGroups.delete(groupId);
    } else {
      newGroups.add(groupId);
    }
    setSelectedGroups(newGroups);
  };

  const toggleApiScope = (scopeId) => {
    const target = String(scopeId || "").trim();
    if (!target) return;
    setSelectedApiScopes((prev) => {
      const current = new Set(prev || []);
      const hasAuto = current.has(AUTO_SCOPE);
      if (target === AUTO_SCOPE) {
        // toggle auto-scope on/off
        if (hasAuto) {
          current.delete(AUTO_SCOPE);
          return Array.from(current);
        } else {
          // enable auto and clear explicit selections
          return [AUTO_SCOPE];
        }
      }
      // toggling an explicit key
      if (hasAuto) {
        // leaving auto scope, start fresh with explicit only
        current.clear();
      }
      if (current.has(target)) {
        current.delete(target);
      } else {
        current.add(target);
      }
      const next = Array.from(current);
      // when nothing left, fall back to auto-scope only
      return next.length > 0 ? next : [AUTO_SCOPE];
    });
  };

  const applyTemplate = (template) => {
    setFormData((prev) => ({
      ...prev,
      expr: template.expr,
      duration: template.duration,
      annotations: {
        ...prev.annotations,
        summary: template.summary,
        description: template.description,
      },
    }));
    setQueryMode("promql");
    setSelectedTemplate(template.id);
  };

  const applyPromqlSuggestion = (suggestion) => {
    const suggestionValue = String(suggestion?.value || "");
    if (!suggestionValue) return;
    const currentExpr = String(formData.expr || "");
    if (promqlAutocompleteContext.mode === "labelKey") {
      const nextSegment = `${suggestionValue}=""`;
      const nextExpr = `${currentExpr.slice(0, promqlAutocompleteContext.segmentStart)}${nextSegment}`;
      setFormData((prev) => ({ ...prev, expr: nextExpr }));
      return;
    }
    if (promqlAutocompleteContext.mode === "labelValue") {
      const key = String(promqlAutocompleteContext.labelKey || "").trim();
      const op = String(promqlAutocompleteContext.operator || "=").trim() || "=";
      if (key) {
        const nextSegment = `${key}${op}"${suggestionValue}"`;
        const nextExpr = `${currentExpr.slice(0, promqlAutocompleteContext.segmentStart)}${nextSegment}`;
        setFormData((prev) => ({ ...prev, expr: nextExpr }));
        return;
      }
    }

    const tokenMatch = currentExpr.match(/([a-zA-Z_:][a-zA-Z0-9_:]*)$/);
    if (tokenMatch?.[1]) {
      const nextExpr = currentExpr.replace(/([a-zA-Z_:][a-zA-Z0-9_:]*)$/, suggestionValue);
      setFormData((prev) => ({ ...prev, expr: nextExpr }));
      return;
    }
    const spacer = currentExpr && !/\s$/.test(currentExpr) ? " " : "";
    setFormData((prev) => ({ ...prev, expr: `${currentExpr}${spacer}${suggestionValue}` }));
  };

  const addBuilderCondition = () => {
    setBuilderConditions((prev) => [
      ...prev,
      {
        id: Math.random().toString(36).slice(2, 9),
        joinWithPrev: "and",
        metric: "",
        operator: ">",
        value: "",
      },
    ]);
  };

  const updateBuilderCondition = (id, field, value) => {
    setBuilderConditions((prev) =>
      prev.map((row) => (row.id === id ? { ...row, [field]: value } : row)),
    );
  };

  const removeBuilderCondition = (id) => {
    setBuilderConditions((prev) => {
      if (prev.length <= 1) {
        return [
          {
            id: Math.random().toString(36).slice(2, 9),
            joinWithPrev: "and",
            metric: "",
            operator: ">",
            value: "",
          },
        ];
      }
      return prev.filter((row) => row.id !== id);
    });
  };

  const handleTestRule = async () => {
    if (!rule?.id) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testAlertRule(rule.id);
      setTestResult(result?.message || "Test notification sent.");
    } catch (e) {
      setTestResult(e?.message || "Failed to send test notification.");
    } finally {
      setTesting(false);
    }
  };

  const canProceedToNextStep = () => {
    const { errors } = validateRuleForm(formData, labelPairs);
    switch (currentStep) {
      case 0: 
        return Boolean(!errors.name && formData.name.trim());
      case 1: 
        return Boolean(
          !errors.expr && !errors.duration && formData.expr.trim(),
        );
      case 2: 
        return true;
      case 3: 
        return true; 
      default:
        return false;
    }
  };

  const handleNext = () => {
    if (canProceedToNextStep() && currentStep < totalSteps - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleStepClick = (stepIndex) => {
    if (typeof stepIndex !== "number") return;
    if (stepIndex < 0 || stepIndex > totalSteps - 1) return;
    setCurrentStep(stepIndex);
  };

  const handleWizardSubmit = async () => {
    const { errors } = validateRuleForm(formData, labelPairs);
    if (Object.keys(errors).length > 0) return;

    setSaving(true);
    setSaveError(null);
    try {
      const success = await onSave({
        ...formData,
        sharedGroupIds: Array.from(selectedGroups),
      });
      if (success) {
        onCancel();
      }
    } catch (e) {
      setSaveError(e.message || "Failed to save rule");
    } finally {
      setSaving(false);
    }
  };

  const hasErrors = Object.keys(validationErrors).length > 0;

  return (
    <div className="max-w-5xl mx-auto overflow-hidden">
      <form onSubmit={(e) => e.preventDefault()} className="space-y-4">
        <RuleEditorWizard
          currentStep={currentStep}
          totalSteps={totalSteps}
          onNext={handleNext}
          onPrevious={handlePrevious}
          onSubmit={handleWizardSubmit}
          onStepClick={handleStepClick}
          canProceed={canProceedToNextStep()}
          isSubmitting={saving}
          hasErrors={hasErrors}
          showButtons={false}
        />
        <div className="min-h-[420px] py-1 overflow-hidden">
          {currentStep === 0 && (
            <>
              <div className="space-y-5 p-1">
                <div className="text-left mb-3">
                  <h2 className="text-lg font-bold text-sre-text mb-1">
                    Basic Setup
                  </h2>
                  <p className="text-xs text-sre-text-muted">
                    Configure the fundamental properties of your alert rule
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="block text-sm font-semibold text-sre-text">
                      Rule Name{" "}
                      <HelpTooltip text="Enter a descriptive name for your alert rule that clearly identifies what it monitors." />
                    </label>
                    <Input
                      value={formData.name}
                      onChange={(e) =>
                        setFormData({ ...formData, name: e.target.value })
                      }
                      required
                      placeholder="CPU Alert"
                      className="w-full text-sm py-2 px-3 border border-sre-border focus:border-sre-primary transition-colors"
                    />
                    {validationErrors.name && (
                      <p className="text-sm text-red-500 dark:text-red-400 font-medium flex items-center gap-1">
                        <span className="material-icons text-sm">error</span>
                        {validationErrors.name}
                      </p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <label className="block text-sm font-semibold text-sre-text">
                      Severity{" "}
                      <HelpTooltip text="Choose the severity level for this alert. Critical alerts require immediate attention, warnings are less urgent." />
                    </label>
                    <Select
                      value={formData.severity}
                      onChange={(e) =>
                        setFormData({ ...formData, severity: e.target.value })
                      }
                      className="w-full text-sm py-2 px-3 border border-sre-border focus:border-sre-primary transition-colors"
                    >
                      <option value="info">Info</option>
                      <option value="warning">Warning</option>
                      <option value="critical">Critical</option>
                    </Select>
                    {validationErrors.severity && (
                      <p className="text-sm text-red-500 dark:text-red-400 font-medium flex items-center gap-1">
                        <span className="material-icons text-sm">error</span>
                        {validationErrors.severity}
                      </p>
                    )}
                  </div>
                </div>

                {apiKeys.length > 0 && (
                  <div className="space-y-2">
                    <label className="block text-sm font-semibold text-sre-text">
                      Product / API Key{" "}
                      <HelpTooltip text="Select one or more API keys to target specific products. Auto scope selects all visible API keys." />
                    </label>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      <button
                        type="button"
                        onClick={() => toggleApiScope(AUTO_SCOPE)}
                          className={`text-left p-2.5 rounded-lg border transition-colors ${
                          selectedApiScopes.includes(AUTO_SCOPE)
                            ? "border-sre-primary bg-sre-primary/10"
                            : "border-sre-border bg-sre-surface hover:border-sre-primary/50"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={selectedApiScopes.includes(AUTO_SCOPE)}
                            readOnly
                            className="pointer-events-none" // let clicks fall through
                          />
                          <span className="material-icons text-base text-sre-primary">
                            auto_awesome
                          </span>
                          <span className="text-sm font-medium text-sre-text">
                            Auto scope
                          </span>
                        </div>
                      </button>
                      {visibleApiKeys.map((k) => {
                        const isAuto = selectedApiScopes.includes(AUTO_SCOPE);
                        const isSelected =
                          !isAuto &&
                          selectedApiScopes.includes(String(k.key || ""));
                        return (
                          <button
                            key={k.id}
                            type="button"
                            onClick={() => toggleApiScope(String(k.key || ""))}
                            disabled={isAuto}
                            className={`text-left p-2.5 rounded-lg border transition-colors ${
                              isSelected
                                ? "border-sre-primary bg-sre-primary/10"
                                : "border-sre-border bg-sre-surface hover:border-sre-primary/50"
                            } ${isAuto ? "opacity-50 cursor-not-allowed" : ""}`}
                          >
                            <div className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                readOnly
                                className="pointer-events-none"
                              />
                              <span className="text-sm font-medium text-sre-text truncate">
                                {k.name}
                                {k.is_default ? " (Default)" : ""}
                                {k.is_enabled ? " — active" : " — inactive"}
                              </span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                    {showOwnerScopeHiddenHint && (
                      <p className="text-xs text-sre-text-muted">
                        The API key selected for this rule has not been shared with you by the owner.
                      </p>
                    )}
                  </div>
                )}

                {/* Quick Templates */}
                <div>
                  <div className="mb-3">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="material-icons text-xl text-sre-primary">
                        auto_awesome
                      </span>
                      <h4 className="text-sm font-semibold text-sre-text">
                        Quick Templates
                      </h4>
                    </div>
                    <p className="text-xs text-sre-text-muted">
                      Start from a known-good template, then tune the expression
                      and thresholds for your environment.
                    </p>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-72 scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-sre-bg-alt scrollbar-thumb-rounded overflow-y-auto pr-1">
                    {RULE_TEMPLATES.map((template) => {
                      const isSelected = selectedTemplate === template.id;
                      return (
                        <button
                          key={template.id}
                          type="button"
                          onClick={() => applyTemplate(template)}
                          className={`text-left p-3 rounded-lg border transition-all duration-200 group shadow-sm hover:shadow-md h-auto relative ${
                            isSelected
                              ? "border-sre-primary bg-sre-primary/10 shadow-md"
                              : "border-sre-border bg-sre-surface hover:border-sre-primary hover:bg-sre-primary/5"
                          }`}
                        >
                          {isSelected && (
                            <div className="absolute top-2 right-2">
                              <span className="material-icons text-base text-sre-primary">
                                auto_awesome
                              </span>
                            </div>
                          )}
                          <div
                            className={`text-sm font-semibold transition-colors mb-1.5 text-left ${
                              isSelected
                                ? "text-sre-primary"
                                : "text-sre-text group-hover:text-sre-primary"
                            }`}
                          >
                            {template.name}
                          </div>
                          <div className="text-xs text-sre-text-muted mb-2 line-clamp-2 text-left">
                            {template.summary}
                          </div>
                          <div className="text-[11px] font-mono text-sre-text-muted bg-sre-bg-alt p-2.5 rounded border text-left whitespace-pre-wrap break-words leading-relaxed min-h-[70px] overflow-hidden">
                            {template.expr}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </>
          )}

          {currentStep === 1 && (
            <>
              {/* Alert Condition */}
              <div className="space-y-5 p-1">
                <div className="text-left mb-3">
                  <h2 className="text-lg font-bold text-sre-text mb-1">
                    Alert Condition
                  </h2>
                  <p className="text-xs text-sre-text-muted">
                    Define when this alert should trigger
                  </p>
                </div>

                <div className="space-y-4">
                  {/* Metric Explorer */}
                  <div className="bg-gradient-to-r from-sre-surface to-sre-surface/80 rounded-lg p-4 border border-sre-border">
                    <div className="flex items-start justify-between gap-4 mb-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-2">
                          <span className="material-icons text-xl text-sre-primary">
                            functions
                          </span>
                          <h4 className="text-base font-semibold text-sre-text">
                            Metric Explorer
                          </h4>
                        </div>
                        <p className="text-sm text-sre-text-muted leading-relaxed">
                          Load metric names from Mimir for the selected product.
                          Click a metric to {queryMode === "builder"
                            ? "fill the latest builder row"
                            : "insert it into PromQL"}.
                        </p>
                        <div className="mt-1.5">
                          <span className="inline-flex items-center gap-1 rounded-full border border-indigo-400/45 bg-indigo-500/15 px-2 py-0.5 text-[11px] font-semibold text-indigo-300">
                            <span className="material-icons text-[13px] leading-none">
                              key
                            </span>
                            Scope: {metricsScopeLabel || "Default"}
                          </span>
                        </div>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={loadMetrics}
                        disabled={loadingMetrics}
                        className="p-1.5 min-w-0 h-8 w-8"
                        title="Load metrics"
                        aria-label="Load metrics"
                      >
                        <span
                          className={`material-icons text-base ${loadingMetrics ? "animate-spin" : ""}`}
                        >
                          {loadingMetrics ? "progress_activity" : "refresh"}
                        </span>
                      </Button>
                    </div>

                    {metricsError && (
                      <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300 font-medium">
                        <span className="material-icons text-base mr-1 align-middle">
                          error
                        </span>
                        {metricsError}
                      </div>
                    )}

                    {metricNames.length > 0 && (
                      <>
                        <div className="mb-4">
                          <label className="block text-sm font-semibold text-sre-text mb-2">
                            Filter metrics
                          </label>
                          <Input
                            value={metricFilter}
                            onChange={(e) => setMetricFilter(e.target.value)}
                            placeholder="http_requests_total"
                            className="w-full py-2 px-3 border border-sre-border focus:border-sre-primary transition-colors"
                          />
                        </div>
                        <div className="max-h-48 overflow-y-auto">
                          {filteredMetricNames.length ? (
                            <div className="flex flex-wrap gap-1.5">
                              {filteredMetricNames.map((name) => (
                                <button
                                  key={name}
                                  type="button"
                                  onClick={() => {
                                    if (queryMode === "builder") {
                                      setBuilderConditions((prev) => {
                                        if (!prev.length) {
                                          return [
                                            {
                                              id: Math.random().toString(36).slice(2, 9),
                                              joinWithPrev: "and",
                                              metric: name,
                                              operator: ">",
                                              value: "",
                                            },
                                          ];
                                        }
                                        const next = [...prev];
                                        let targetIndex = 0;
                                        for (let i = next.length - 1; i >= 0; i -= 1) {
                                          if (!String(next[i]?.metric || "").trim()) {
                                            targetIndex = i;
                                            break;
                                          }
                                        }
                                        next[targetIndex] = {
                                          ...next[targetIndex],
                                          metric: name,
                                        };
                                        return next;
                                      });
                                      return;
                                    }
                                    const base = formData.expr || "";
                                    const template = base ? `${base}\n${name}` : name;
                                    setFormData({ ...formData, expr: template });
                                  }}
                                  className="px-2.5 py-1 text-xs rounded-full border border-sre-border/80 bg-sre-bg-card/80 hover:bg-sre-primary/10 hover:border-sre-primary/60 text-sre-text transition-all duration-150 break-words max-w-full text-left"
                                  title={name}
                                >
                                  {name}
                                </button>
                              ))}
                            </div>
                          ) : (
                            <p className="text-sm text-sre-text-muted italic">
                              No metrics match this filter.
                            </p>
                          )}
                        </div>
                      </>
                    )}
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <label className="block text-sm font-semibold text-sre-text">
                        Alert Query{" "}
                        <HelpTooltip text="Use PromQL mode for direct query input, or Builder mode to compose conditions with AND/OR logic." />
                      </label>
                      <div className="inline-flex rounded-lg border border-sre-border bg-sre-bg-alt p-1">
                        <button
                          type="button"
                          onClick={() => setQueryMode("promql")}
                          className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors ${
                            queryMode === "promql"
                              ? "bg-sre-primary text-white"
                              : "text-sre-text-muted hover:text-sre-text"
                          }`}
                        >
                          PromQL
                        </button>
                        <button
                          type="button"
                          onClick={() => setQueryMode("builder")}
                          className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors ${
                            queryMode === "builder"
                              ? "bg-sre-primary text-white"
                              : "text-sre-text-muted hover:text-sre-text"
                          }`}
                        >
                          Builder
                        </button>
                      </div>
                    </div>

                    {queryMode === "promql" ? (
                      <div className="space-y-2">
                        <Textarea
                          value={formData.expr}
                          onChange={(e) =>
                            setFormData({ ...formData, expr: e.target.value })
                          }
                          required
                          placeholder="rate(requests_total[5m]) > 100"
                          rows={6}
                          className="w-full font-mono text-sm py-2.5 px-3 border border-sre-border focus:border-sre-primary transition-colors whitespace-pre leading-relaxed"
                        />
                        {promqlSuggestions.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {promqlSuggestions.map((suggestion) => (
                              <button
                                key={`${suggestion.type || "hint"}-${suggestion.value}`}
                                type="button"
                                onClick={() => applyPromqlSuggestion(suggestion)}
                                className="rounded-full border border-sre-border/80 bg-sre-bg-alt/70 px-2 py-0.5 text-[11px] font-mono text-sre-text hover:border-sre-primary/40 hover:text-sre-primary transition-colors"
                              >
                                {suggestion.value}
                              </button>
                            ))}
                          </div>
                        )}
                        <div className="rounded-md border border-sre-border/70 bg-sre-bg-alt/60 px-3 py-2">
                          {promqlPreview.loading ? (
                            <p className="text-xs text-sre-text-muted">Validating query...</p>
                          ) : promqlPreview.valid === true ? (
                            <div className="text-xs text-sre-text">
                              <span className="text-green-600 dark:text-green-400 font-semibold">
                                Query valid.
                              </span>{" "}
                              {promqlPreview.currentValue !== null && (
                                <span>
                                  Current value: <span className="font-mono">{String(promqlPreview.currentValue)}</span>
                                </span>
                              )}{" "}
                              {promqlPreview.resultType && (
                                <span className="text-sre-text-muted">
                                  ({promqlPreview.resultType}, {promqlPreview.sampleCount} samples)
                                </span>
                              )}
                            </div>
                          ) : promqlPreview.valid === false ? (
                            <p className="text-xs text-red-500 dark:text-red-400">
                              {promqlPreview.error || "Query is invalid or returned an error."}
                            </p>
                          ) : (
                            <p className="text-xs text-sre-text-muted">
                              Type a PromQL expression to validate it and preview current values.
                            </p>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2.5 rounded-lg border border-sre-border bg-sre-surface p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-sre-border/70 bg-sre-bg-alt/60 px-2.5 py-2">
                          <label className="inline-flex items-center gap-2 text-xs text-sre-text">
                            <input
                              type="checkbox"
                              checked={builderUseRate}
                              onChange={(e) => setBuilderUseRate(e.target.checked)}
                              className="rounded border-sre-border bg-sre-surface"
                            />
                            Apply <span className="font-mono">rate()</span> to metrics
                          </label>
                          {builderUseRate && (
                            <div className="flex items-center gap-2">
                              <label className="text-xs text-sre-text-muted">
                                Window
                              </label>
                              <Input
                                value={builderRateWindow}
                                onChange={(e) => setBuilderRateWindow(e.target.value)}
                                placeholder="5m"
                                className="w-20 text-xs py-1.5 px-2 border border-sre-border"
                              />
                            </div>
                          )}
                        </div>
                        {builderConditions.map((row, index) => (
                          <div
                            key={row.id}
                            className="grid grid-cols-1 md:grid-cols-[auto_1.8fr_auto_1fr_auto] gap-2 items-center"
                          >
                            {index === 0 ? (
                              <span className="text-[11px] font-semibold uppercase tracking-wide text-sre-text-muted px-2">
                                Start
                              </span>
                            ) : (
                              <Select
                                value={row.joinWithPrev}
                                onChange={(e) =>
                                  updateBuilderCondition(
                                    row.id,
                                    "joinWithPrev",
                                    e.target.value,
                                  )
                                }
                                className="text-xs px-2 py-1 border border-sre-border"
                              >
                                <option value="and">AND</option>
                                <option value="or">OR</option>
                              </Select>
                            )}

                            <Input
                              value={row.metric}
                              onChange={(e) =>
                                updateBuilderCondition(
                                  row.id,
                                  "metric",
                                  e.target.value,
                                )
                              }
                              placeholder="Metric name"
                              list="rule-metric-suggestions"
                              className="w-full text-sm py-2 px-3 border border-sre-border"
                            />
                            <Select
                              value={row.operator}
                              onChange={(e) =>
                                updateBuilderCondition(
                                  row.id,
                                  "operator",
                                  e.target.value,
                                )
                              }
                              className="text-sm px-2 py-2 border border-sre-border"
                            >
                              {CONDITION_OPERATORS.map((op) => (
                                <option key={op} value={op}>
                                  {op}
                                </option>
                              ))}
                            </Select>
                            <Input
                              value={row.value}
                              onChange={(e) =>
                                updateBuilderCondition(row.id, "value", e.target.value)
                              }
                              placeholder="Value"
                              className="w-full text-sm py-2 px-3 border border-sre-border"
                            />
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => removeBuilderCondition(row.id)}
                              className="h-9 w-9 p-0 text-red-500 hover:text-red-700 hover:bg-red-50"
                              title="Remove condition"
                            >
                              <span className="material-icons text-base">close</span>
                            </Button>
                          </div>
                        ))}

                        <div className="flex justify-end">
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            onClick={addBuilderCondition}
                          >
                            <span className="material-icons text-sm mr-1.5">add</span>
                            Add Rule
                          </Button>
                        </div>
                        <datalist id="rule-metric-suggestions">
                          {filteredMetricNames.map((metric) => (
                            <option key={metric} value={metric} />
                          ))}
                        </datalist>
                      </div>
                    )}

                    {validationErrors.expr && (
                      <p className="text-sm text-red-500 dark:text-red-400 font-medium flex items-center gap-1">
                        <span className="material-icons text-sm">error</span>
                        {validationErrors.expr}
                      </p>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-3">
                      <label className="block text-sm font-semibold text-sre-text">
                        Duration{" "}
                        <HelpTooltip text="How long the condition must be true before the alert fires. Use Prometheus duration format (5m, 1h)." />
                      </label>
                      <Input
                        value={formData.duration}
                        onChange={(e) =>
                          setFormData({ ...formData, duration: e.target.value })
                        }
                        placeholder="5m, 1h"
                        className="w-full text-sm py-2 px-3 border border-sre-border focus:border-sre-primary transition-colors"
                      />
                      {validationErrors.duration && (
                        <p className="text-sm text-red-500 dark:text-red-400 font-medium flex items-center gap-1">
                          <span className="material-icons text-sm">error</span>
                          {validationErrors.duration}
                        </p>
                      )}
                    </div>
                    <div className="space-y-3">
                      <label className="block text-sm font-semibold text-sre-text">
                        Correlation ID{" "}
                        <HelpTooltip text="Correlation ID groups related rules/alerts together. Select an existing one or type a new ID." />
                      </label>
                      <div className="space-y-2">
                        <Select
                          value={correlationMode}
                          onChange={(e) => {
                            const mode = e.target.value;
                            setCorrelationMode(mode);
                            if (mode === "existing") {
                              setFormData((prev) => ({
                                ...prev,
                                group:
                                  correlationIdOptions[0] ||
                                  String(prev.group || "").trim() ||
                                  "default",
                              }));
                            }
                          }}
                          className="w-full text-sm py-2 px-3 border border-sre-border focus:border-sre-primary transition-colors"
                        >
                          <option value="existing">Select existing</option>
                          <option value="custom">Create new</option>
                        </Select>

                        {correlationMode === "existing" ? (
                          <Select
                            value={
                              correlationIdOptions.includes(formData.group)
                                ? formData.group
                                : correlationIdOptions[0] || formData.group || "default"
                            }
                            onChange={(e) =>
                              setFormData({ ...formData, group: e.target.value })
                            }
                            className="w-full text-sm px-3 border border-sre-border focus:border-sre-primary transition-colors"
                          >
                            {correlationIdOptions.length === 0 ? (
                              <option value={formData.group || "default"}>
                                {formData.group || "default"}
                              </option>
                            ) : (
                              correlationIdOptions.map((value) => (
                                <option key={value} value={value}>
                                  {value}
                                </option>
                              ))
                            )}
                          </Select>
                        ) : (
                          <div className="flex items-center gap-2">
                            <Input
                              value={formData.group}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  group: e.target.value.slice(
                                    0,
                                    MAX_CORRELATION_ID_LENGTH,
                                  ),
                                })
                              }
                              placeholder="default"
                              maxLength={MAX_CORRELATION_ID_LENGTH}
                              className="w-full text-sm px-3 border border-sre-border focus:border-sre-primary transition-colors"
                            />
                            <Button
                              size="xs"
                              variant="ghost"
                              title="Generate random ID"
                              onClick={generateCorrelationId}
                            >
                              <span className="material-icons text-base">
                                shuffle
                              </span>
                              <span className="sr-only">Generate ID</span>
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                </div>
              </div>
            </>
          )}

          {currentStep === 2 && (
            <>
              {/* Alert Details */}
              <div className="space-y-5 p-1">
                <div className="text-left mb-3">
                  <h2 className="text-lg font-bold text-sre-text mb-1">
                    Alert Details
                  </h2>
                  <p className="text-xs text-sre-text-muted">
                    Add context and labels to make your alerts more informative
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-3">
                    <label className="block text-sm font-semibold text-sre-text">
                      Summary{" "}
                      <HelpTooltip text="A brief summary of the alert that will be shown in notifications and the UI." />
                    </label>
                    <Input
                      value={formData.annotations.summary}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          annotations: {
                            ...formData.annotations,
                            summary: e.target.value,
                          },
                        })
                      }
                      placeholder="Brief alert summary"
                      className="w-full text-sm py-2 px-3 border border-sre-border focus:border-sre-primary transition-colors"
                    />
                  </div>
                  <div className="space-y-3">
                    <label className="block text-sm font-semibold text-sre-text">
                      Description{" "}
                      <HelpTooltip text="Detailed description of the alert condition and what it means when it fires." />
                    </label>
                    <Input
                      value={formData.annotations.description}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          annotations: {
                            ...formData.annotations,
                            description: e.target.value,
                          },
                        })
                      }
                      placeholder="Detailed description"
                      className="w-full text-sm py-2 px-3 border border-sre-border focus:border-sre-primary transition-colors"
                    />
                  </div>
                </div>

                {/* Alert Labels */}
                <div className="pt-2">
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div>
                      <h4 className="text-base font-semibold text-sre-text">
                        Alert Labels
                      </h4>
                      <p className="text-sm text-sre-text-muted">
                        Labels help route and group alerts. Severity is
                        automatically added.
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() =>
                        setLabelPairs([
                          ...labelPairs,
                          {
                            id: Math.random().toString(36).substr(2, 9),
                            key: "",
                            value: "",
                          },
                        ])
                      }
                    >
                      <span className="material-icons text-base mr-2">add</span>
                      Add Label
                    </Button>
                  </div>

                  {labelPairs.length === 0 ? (
                    <p className="text-sm text-sre-text-muted">
                      No labels added yet.
                    </p>
                  ) : (
                    <div className="space-y-2.5">
                      {labelPairs.map((pair, idx) => (
                        <div
                          key={pair.id}
                          className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-2 items-center"
                        >
                          <Input
                            value={pair.key}
                            onChange={(e) => {
                              const next = [...labelPairs];
                              next[idx] = { ...next[idx], key: e.target.value };
                              setLabelPairs(next);
                            }}
                            placeholder="label_key"
                            className="w-full"
                          />
                          <Input
                            value={pair.value}
                            onChange={(e) => {
                              const next = [...labelPairs];
                              next[idx] = {
                                ...next[idx],
                                value: e.target.value,
                              };
                              setLabelPairs(next);
                            }}
                            placeholder="value"
                            className="w-full"
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              setLabelPairs(
                                labelPairs.filter((p) => p.id !== pair.id),
                              )
                            }
                            className="text-red-500 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20 transition-colors"
                          >
                            <span className="material-icons text-base">
                              close
                            </span>
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                  {validationErrors.labels && (
                    <p className="text-sm text-red-500 dark:text-red-400 font-medium flex items-center gap-1 mt-2">
                      <span className="material-icons text-sm">error</span>
                      {validationErrors.labels}
                    </p>
                  )}
                </div>

                {/* Rule Preview */}
                <div>
                  <h4 className="text-base font-semibold text-sre-text mb-2 flex items-center gap-2">
                    Rule Preview
                  </h4>

                  <div className="space-y-3">
                    <div className="space-y-2">
                      <div className="text-sm text-sre-text-muted font-medium uppercase tracking-wide">
                        Expression
                      </div>
                      <div className="text-xs font-mono text-sre-text break-words bg-sre-surface p-3 rounded-lg border border-sre-border shadow-inner max-h-24 overflow-y-auto">
                        {formData.expr || "No expression set"}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                      <div className="space-y-2">
                        <div className="text-sm text-sre-text-muted font-medium uppercase tracking-wide">
                          Duration
                        </div>
                        <div className="text-sm text-sre-text font-mono bg-sre-surface px-3 py-2 rounded border border-sre-border">
                          {formData.duration || "1m"}
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className="text-sm text-sre-text-muted font-medium uppercase tracking-wide">
                          Group
                        </div>
                        <div className="text-sm text-sre-text font-mono bg-sre-surface px-3 py-2 rounded border border-sre-border">
                          {formData.group || "default"}
                        </div>
                      </div>
                      <div className="space-y-2">
                        <div className="text-sm text-sre-text-muted font-medium uppercase tracking-wide">
                          Target Org
                        </div>
                        <div className="text-sm text-sre-text font-mono bg-sre-surface px-3 py-2 rounded border border-sre-border break-words">
                          {formData.orgId || "default org"}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <div className="text-sm text-sre-text-muted font-medium uppercase tracking-wide">
                        Labels
                      </div>
                      <div className="flex flex-wrap items-center gap-2 min-h-[3rem]">
                        {Object.entries(effectiveLabels).length > 0 ? (
                          Object.entries(effectiveLabels).map(
                            ([key, value]) => (
                              <span
                                key={key}
                                className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-sre-primary/25 bg-sre-primary/10 text-sre-text break-all leading-none"
                              >
                                <span className="font-semibold text-sre-primary">
                                  {key}
                                </span>
                                <span className="text-sre-text-muted">=</span>
                                <span className="font-medium">{value}</span>
                              </span>
                            ),
                          )
                        ) : (
                          <span className="text-sm text-sre-text-muted italic">
                            No labels
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {currentStep === 3 && (
            <>
              {/* Advanced Settings */}
              <div className="space-y-5 p-1">
                <div className="text-left mb-3">
                  <h2 className="text-lg font-bold text-sre-text mb-1">
                    Advanced Settings
                  </h2>
                  <p className="text-xs text-sre-text-muted">
                    Configure notifications and rule visibility
                  </p>
                </div>

                {/* Notification Channels */}
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <span className="material-icons text-xl text-sre-primary">
                      notifications
                    </span>
                    <div>
                      <h4 className="text-base font-semibold text-sre-text">
                        Notification Channels
                      </h4>
                      <p className="text-sm text-sre-text-muted">
                        {channels?.length > 0
                          ? `${channels.length} channel${channels.length !== 1 ? "s" : ""} configured`
                          : "No channels configured"}
                      </p>
                    </div>
                  </div>

                  <div className="space-y-3">
                    {channels?.length > 0 ? (
                      <>
                        {/* All Channels Option */}
                        <div
                          onClick={() => {
                            let newChannels = [];
                            if (
                              formData.notificationChannels &&
                              formData.notificationChannels.length > 0
                            ) {
                              newChannels = [];
                            } else {
                              newChannels = channels.map((c) => c.id);
                            }
                            setFormData({
                              ...formData,
                              notificationChannels: newChannels,
                            });
                          }}
                          className={`p-3 rounded-lg border cursor-pointer transition-all duration-200 ${
                            !formData.notificationChannels ||
                            formData.notificationChannels.length === 0
                              ? "border-sre-primary bg-sre-primary/5 shadow-md"
                              : "border-sre-border bg-sre-surface hover:border-sre-primary/50 hover:bg-sre-primary/5"
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <div
                              className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                                !formData.notificationChannels ||
                                formData.notificationChannels.length === 0
                                  ? "bg-sre-primary border-sre-primary"
                                  : "border-sre-border"
                              }`}
                            >
                              {(!formData.notificationChannels ||
                                formData.notificationChannels.length === 0) && (
                                <span className="material-icons text-white text-sm">
                                  check
                                </span>
                              )}
                            </div>
                            <div className="flex-1">
                              <div className="font-semibold text-sre-text">
                                All Channels
                              </div>
                              <div className="text-sm text-sre-text-muted">
                                Use all enabled notification channels (default)
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Individual Channels */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                          {channels.map((channel) => {
                            const isSelected =
                              formData.notificationChannels?.includes(
                                channel.id,
                              );
                            return (
                              <div
                                key={channel.id}
                                onClick={() => {
                                  const channels =
                                    formData.notificationChannels || [];
                                  const newChannels = isSelected
                                    ? channels.filter((id) => id !== channel.id)
                                    : [...channels, channel.id];
                                  setFormData({
                                    ...formData,
                                    notificationChannels: newChannels,
                                  });
                                }}
                                className={`p-3 rounded-lg border cursor-pointer transition-all duration-200 ${
                                  isSelected
                                    ? "border-sre-primary bg-sre-primary/5 shadow-md"
                                    : "border-sre-border bg-sre-surface hover:border-sre-primary/50 hover:bg-sre-primary/5"
                                }`}
                              >
                                <div className="flex items-start gap-3">
                                  <div
                                    className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors mt-0.5 ${
                                      isSelected
                                        ? "bg-sre-primary border-sre-primary"
                                        : "border-sre-border"
                                    }`}
                                  >
                                    {isSelected && (
                                      <span className="material-icons text-white text-sm">
                                        check
                                      </span>
                                    )}
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                      <span
                                        className={`px-2 py-1 rounded-full text-xs font-medium ${
                                          channel.type === "slack"
                                            ? "bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200"
                                            : channel.type === "email"
                                              ? "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200"
                                              : channel.type === "webhook"
                                                ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200"
                                                : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
                                        }`}
                                      >
                                        {channel.type}
                                      </span>
                                      <span
                                        className={`px-2 py-1 rounded-full text-xs font-medium ${
                                          channel.enabled
                                            ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200"
                                            : "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200"
                                        }`}
                                      >
                                        {channel.enabled
                                          ? "Enabled"
                                          : "Disabled"}
                                      </span>
                                    </div>
                                    <div className="font-semibold text-sre-text mb-1">
                                      {channel.name}
                                    </div>
                                    {channel.config?.channel && (
                                      <div className="text-sm text-sre-text-muted">
                                        Channel: {channel.config.channel}
                                      </div>
                                    )}
                                    {channel.config?.url && (
                                      <div className="text-sm text-sre-text-muted truncate">
                                        URL: {channel.config.url}
                                      </div>
                                    )}
                                    {channel.config?.to && (
                                      <div className="text-sm text-sre-text-muted truncate">
                                        To: {channel.config.to}
                                      </div>
                                    )}

                                    {((!channel.config?.channel && !channel.config?.url && !channel.config?.to) || channel.is_hidden || channel.isHidden) && (
                                      <div className="text-xs text-sre-text-muted italic mt-1">
                                        You don't own this channel but may use it
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </>
                    ) : (
                      <div className="text-center py-8 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
                        <span className="material-icons text-4xl text-sre-text-muted mb-4 block">
                          notifications_off
                        </span>
                        <h4 className="text-base font-semibold text-sre-text mb-2">
                          No Channels Configured
                        </h4>
                        {canReadChannels ? (
                          <>
                            <p className="text-sre-text-muted mb-4">
                              Configure notification channels before assigning
                              them to alerts.
                            </p>
                            <div className="flex items-center justify-center gap-3">
                              <a
                                href="/integrations"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-sre-primary hover:underline"
                              >
                                Manage Integrations
                              </a>
                            </div>
                            <p className="text-sm text-sre-text-muted mt-3">
                              You can assign channels later after creating the
                              rule.
                            </p>
                          </>
                        ) : (
                          <p className="text-sre-text-muted mb-4">
                            You don&apos;t have permission to view or configure
                            notification channels. Contact your administrator.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Enable Rule */}
                <div className="flex items-center gap-4">
                  <input
                    type="checkbox"
                    id="enabled"
                    checked={formData.enabled}
                    onChange={(e) =>
                      setFormData({ ...formData, enabled: e.target.checked })
                    }
                    className="w-4 h-4 text-sre-primary border border-sre-border rounded focus:ring-sre-primary"
                  />
                  <label
                    htmlFor="enabled"
                    className="text-sm text-sre-text cursor-pointer"
                  >
                    <span className="font-semibold">Enable this rule</span>{" "}
                    <HelpTooltip text="Only enabled rules will trigger alerts. Disabled rules are saved but won't fire." />
                  </label>
                </div>

                {/* Visibility Settings */}
                <div className="space-y-3">
                  <label
                    htmlFor="rule-visibility"
                    className="block text-sm font-semibold text-sre-text"
                  >
                    <span className="material-icons text-lg align-middle mr-2 text-sre-primary">
                      visibility
                    </span>{" "}
                    Visibility{" "}
                    <HelpTooltip text="Control who can view and edit this alert rule. Private rules are only visible to you." />
                  </label>
                  <Select
                    id="rule-visibility"
                    value={formData.visibility || "private"}
                    onChange={(e) => {
                      const newVisibility = e.target.value;
                      setFormData({ ...formData, visibility: newVisibility });
                      if (newVisibility !== "group") {
                        setSelectedGroups(new Set());
                      }
                    }}
                    className="w-full max-w-md text-sm py-2 px-3 border border-sre-border focus:border-sre-primary transition-colors"
                  >
                    <option value="private">
                      Private - Only visible to me
                    </option>
                    <option value="group">
                      Group - Share with specific groups
                    </option>
                    <option value="tenant">
                      Tenant - Visible to all users in tenant
                    </option>
                  </Select>
                  <p className="text-xs text-sre-text-muted leading-relaxed">
                    {formData.visibility === "private" &&
                      "Only you can view and edit this rule"}
                    {formData.visibility === "group" &&
                      "Users in selected groups can view this rule"}
                    {formData.visibility === "tenant" &&
                      "All users in your organization can view this rule"}
                  </p>
                </div>

                {/* Group Sharing */}
                {formData.visibility === "group" && groups?.length > 0 && (
                  <div className="space-y-3">
                    <label
                      htmlFor="rule-groups"
                      className="block text-sm font-semibold text-sre-text"
                    >
                      Share with Groups{" "}
                      <HelpTooltip text="Select which user groups can view and edit this alert rule." />
                    </label>
                    <div
                      id="rule-groups"
                      className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-56 overflow-y-auto"
                    >
                      {groups.map((group) => (
                        <label
                          key={group.id}
                          className="flex items-center gap-3 p-2.5 bg-sre-surface border border-sre-border rounded-lg cursor-pointer hover:bg-sre-primary/5 hover:border-sre-primary transition-all duration-200"
                        >
                          <input
                            type="checkbox"
                            checked={selectedGroups.has(group.id)}
                            onChange={() => toggleGroup(group.id)}
                            className="w-4 h-4 text-sre-primary border border-sre-border rounded focus:ring-sre-primary"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="font-semibold text-sre-text truncate">
                              {group.name}
                            </div>
                            {group.description && (
                              <div className="text-xs text-sre-text-muted truncate">
                                {group.description}
                              </div>
                            )}
                          </div>
                        </label>
                      ))}
                    </div>
                    <p className="text-xs text-sre-text-muted">
                      {selectedGroups.size} group
                      {selectedGroups.size === 1 ? "" : "s"} selected
                    </p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <RuleEditorWizard
          currentStep={currentStep}
          totalSteps={totalSteps}
          onNext={handleNext}
          onPrevious={handlePrevious}
          onSubmit={handleWizardSubmit}
          onStepClick={handleStepClick}
          canProceed={canProceedToNextStep()}
          isSubmitting={saving}
          hasErrors={hasErrors}
          showIndicator={false}
        />

        {(hasErrors || validationWarnings.length > 0 || saveError) && (
          <div className="border-2 border-red-200 dark:border-red-800 rounded-xl p-4 bg-red-50 dark:bg-red-900/20 shadow-inner">
            <button
              onClick={() => setIssuesCollapsed(!issuesCollapsed)}
              className="w-full flex items-center justify-between text-left focus:outline-none focus:ring-2 focus:ring-red-500 rounded-lg p-2 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
            >
              <h4 className="text-base font-semibold text-red-800 dark:text-red-200 flex items-center gap-2">
                <span className="material-icons text-xl">error</span>
                Checks and Issues
              </h4>
              <div className="flex items-center gap-2">
                {(hasErrors || saveError) && (
                  <span className="px-2 py-1 bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-200 text-xs font-medium rounded-full">
                    {Object.keys(validationErrors).length + (saveError ? 1 : 0)}{" "}
                    errors
                  </span>
                )}
                {validationWarnings.length > 0 && (
                  <span className="px-2 py-1 bg-yellow-100 dark:bg-yellow-900/50 text-yellow-800 dark:text-yellow-200 text-xs font-medium rounded-full">
                    {validationWarnings.length} warnings
                  </span>
                )}
                <span className="material-icons text-red-600 dark:text-red-400">
                  {issuesCollapsed ? "expand_more" : "expand_less"}
                </span>
              </div>
            </button>
            {!issuesCollapsed && (
              <div className="mt-4 space-y-3">
                {saveError && (
                  <div className="p-4 bg-red-100 dark:bg-red-900/50 border border-red-300 dark:border-red-700 rounded-lg text-sm text-red-800 dark:text-red-200 font-medium">
                    {saveError}
                  </div>
                )}
                {hasErrors && (
                  <div className="space-y-3">
                    {Object.values(validationErrors).map((msg, idx) => (
                      <div
                        key={`err-${idx}`}
                        className="p-4 bg-red-100 dark:bg-red-900/50 border border-red-300 dark:border-red-700 rounded-lg text-sm text-red-800 dark:text-red-200 font-medium flex items-start gap-2"
                      >
                        <span className="material-icons text-base mt-0.5 flex-shrink-0">
                          error
                        </span>
                        <span>{msg}</span>
                      </div>
                    ))}
                  </div>
                )}
                {validationWarnings.length > 0 && (
                  <div className="space-y-3">
                    {validationWarnings.map((msg, idx) => (
                      <div
                        key={`warn-${idx}`}
                        className="p-4 bg-yellow-100 dark:bg-yellow-900/50 border border-yellow-300 dark:border-yellow-700 rounded-lg text-sm text-yellow-800 dark:text-yellow-200 font-medium flex items-start gap-2"
                      >
                        <span className="material-icons text-base mt-0.5 flex-shrink-0">
                          warning
                        </span>
                        <span>{msg}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Test Rule Button - Only show for existing rules */}
        {rule?.id && (
          <div className="flex flex-col gap-3 justify-center pt-4">
            <Button
              type="button"
              variant="secondary"
              onClick={handleTestRule}
              disabled={testing}
            >
              <span
                className="material-icons text-base mr-2"
                aria-hidden="true"
              >
                science
              </span>{" "}
              {testing ? "Testing..." : "Test Current Rule"}
            </Button>
            {testResult && (
              <p className="text-sm text-sre-text-muted text-center ">
                {testResult}
              </p>
            )}
          </div>
        )}
      </form>
    </div>
  );
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
  availableCorrelationIds: PropTypes.arrayOf(PropTypes.string),
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
};
