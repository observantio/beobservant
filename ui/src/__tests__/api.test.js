import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "ERR",
    headers: {
      get: (name) =>
        name.toLowerCase() === "content-type" ? "application/json" : null,
    },
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  };
}

describe("api request behavior", () => {
  beforeEach(() => {
    api.setAuthToken(null);
    api.setUserOrgIds([]);
    api.setSetupToken(null);
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ ok: true })),
    );
  });

  it("sends credentials and authorization header when token is set", async () => {
    api.setAuthToken("token-123");
    await api.getCurrentUser();

    expect(fetch).toHaveBeenCalledTimes(1);
    const [, options] = fetch.mock.calls[0];
    expect(options.credentials).toBe("include");
    expect(options.headers.Authorization).toBe("Bearer token-123");
  });

  it("sends credentials but no Authorization header when token is not set (cookie sessions)", async () => {
    api.setAuthToken(null);
    await api.getCurrentUser();

    expect(fetch).toHaveBeenCalledTimes(1);
    const [, options] = fetch.mock.calls[0];
    expect(options.credentials).toBe("include");
    expect(options.headers.Authorization).toBeUndefined();
  });

  it("adds X-Scope-OrgID for Loki/Tempo requests", async () => {
    api.setAuthToken("token-abc");
    api.setUserOrgIds(["org-a"]);

    await api.queryLogs({ query: '{job="api"}', limit: 5 });

    const [, options] = fetch.mock.calls[0];
    expect(options.headers["X-Scope-OrgID"]).toBe("org-a");
    expect(options.headers.Authorization).toBe("Bearer token-abc");
  });

  it("adds X-Scope-OrgID for Resolver requests", async () => {
    api.setAuthToken("token-abc");
    api.setUserOrgIds(["org-a"]);

    await api.listRcaJobs();

    const [, options] = fetch.mock.calls[0];
    expect(options.headers["X-Scope-OrgID"]).toBe("org-a");
    expect(options.headers.Authorization).toBe("Bearer token-abc");
  });

  it("requests the RCA config template from Resolver with scoped headers", async () => {
    api.setAuthToken("token-abc");
    api.setUserOrgIds(["org-a"]);

    await api.getRcaAnalyzeConfigTemplate();

    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, options] = fetch.mock.calls[0];
    expect(url).toContain("/api/resolver/analyze/config-template");
    expect(options.headers["X-Scope-OrgID"]).toBe("org-a");
  });

  it("throws structured error body on non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "Denied" }, 403)),
    );

    await expect(api.getCurrentUser()).rejects.toMatchObject({
      status: 403,
      body: { detail: "Denied" },
    });
  });

  it("appends query params for filtered users and groups requests", async () => {
    await api.getUsers({ q: "alice" });
    await api.getGroups({ q: "ops team" });

    const [usersUrl] = fetch.mock.calls[0];
    const [groupsUrl] = fetch.mock.calls[1];
    expect(usersUrl).toContain("/api/auth/users?q=alice");
    expect(groupsUrl).toContain("/api/auth/groups?q=ops+team");
  });

  it("lists API keys without hidden filter by default", async () => {
    await api.listApiKeys();

    const [url] = fetch.mock.calls[0];
    expect(url).toContain("/api/auth/api-keys");
  });

  it("lists API keys with show_hidden when requested", async () => {
    await api.listApiKeys({ showHidden: true });

    const [url] = fetch.mock.calls[0];
    expect(url).toContain("/api/auth/api-keys?show_hidden=true");
  });

  it("hides API key using encoded id and boolean payload", async () => {
    await api.setApiKeyHidden("key/id with space", false);

    const [url, options] = fetch.mock.calls[0];
    expect(url).toContain("/api/auth/api-keys/key%2Fid%20with%20space/hide");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ hidden: false });
  });

  it("replaces API key shares with both user and group ids", async () => {
    await api.replaceApiKeyShares("k-1", ["u-1", "u-2"], ["g-1"]);

    const [url, options] = fetch.mock.calls[0];
    expect(url).toContain("/api/auth/api-keys/k-1/shares");
    expect(options.method).toBe("PUT");
    expect(JSON.parse(options.body)).toEqual({
      user_ids: ["u-1", "u-2"],
      group_ids: ["g-1"],
    });
  });

  it("builds datasource query with combined filters including hidden", async () => {
    await api.getDatasources({
      uid: "uid-1",
      query: "prod metrics",
      labelKey: "service",
      labelValue: "payments",
      teamId: "g-7",
      showHidden: true,
    });

    const [url] = fetch.mock.calls[0];
    expect(url).toContain("/api/grafana/datasources?");
    expect(url).toContain("uid=uid-1");
    expect(url).toContain("query=prod+metrics");
    expect(url).toContain("label_key=service");
    expect(url).toContain("label_value=payments");
    expect(url).toContain("team_id=g-7");
    expect(url).toContain("show_hidden=true");
  });

  it("toggles datasource hidden state with explicit false", async () => {
    await api.toggleDatasourceHidden("ds/one", false);

    const [url, options] = fetch.mock.calls[0];
    expect(url).toContain("/api/grafana/datasources/ds%2Fone/hide");
    expect(JSON.parse(options.body)).toEqual({ hidden: false });
  });

  it("lists notification channels including hidden items", async () => {
    await api.getNotificationChannels({ showHidden: true });

    const [url] = fetch.mock.calls[0];
    expect(url).toContain("/api/alertmanager/channels?show_hidden=true");
  });

  it("sets notification channel hidden with encoded id", async () => {
    await api.setNotificationChannelHidden("channel/ops", true);

    const [url, options] = fetch.mock.calls[0];
    expect(url).toContain("/api/alertmanager/channels/channel%2Fops/hide");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ hidden: true });
  });

  it("lists Jira integrations including hidden items", async () => {
    await api.listJiraIntegrations({ showHidden: true });

    const [url] = fetch.mock.calls[0];
    expect(url).toContain("/api/alertmanager/integrations/jira?show_hidden=true");
  });

  it("sets Jira integration hidden using encoded id", async () => {
    await api.setJiraIntegrationHidden("jira/id", false);

    const [url, options] = fetch.mock.calls[0];
    expect(url).toContain("/api/alertmanager/integrations/jira/jira%2Fid/hide");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ hidden: false });
  });

  it("creates server-side grafana bootstrap session without token in URL", async () => {
    await api.createGrafanaBootstrapSession("/d/abc");
    const [url, options] = fetch.mock.calls[0];
    expect(url).toContain("/api/grafana/bootstrap-session");
    expect(options.method).toBe("POST");
    expect(options.body).toContain('"next":"/d/abc"');
  });

  it("retries idempotent requests once on transient status", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ detail: "busy" }, 503))
        .mockResolvedValueOnce(jsonResponse({ id: "u-1" }, 200)),
    );

    const result = await api.getCurrentUser();
    expect(result).toEqual({ id: "u-1" });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("surfaces request aborted code for cancelled requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        const err = new Error("Aborted");
        err.name = "AbortError";
        throw err;
      }),
    );
    const controller = new AbortController();
    controller.abort();

    await expect(
      api.getTrace("trace-1", { signal: controller.signal }),
    ).rejects.toMatchObject({
      code: "REQUEST_ABORTED",
    });
  });

  it("covers setup-token and auth-token MFA enrollment branches", async () => {
    api.setAuthToken(null);
    api.clearSetupToken();
    await expect(api.enrollMFA()).rejects.toThrow("Not authenticated");
    await expect(api.verifyMFA("123456")).rejects.toThrow("Not authenticated");

    api.setSetupToken("setup-token");
    await api.enrollMFA();
    let [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe("Bearer setup-token");

    await api.verifyMFA("654321");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe("Bearer setup-token");
    expect(options.body).toContain("654321");

    api.setAuthToken("auth-token");
    api.clearSetupToken();
    await api.enrollMFA();
    [, options] = fetch.mock.calls.at(-1);
    expect(options.headers.Authorization).toBe("Bearer auth-token");

    await api.verifyMFA("222222");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.headers.Authorization).toBe("Bearer auth-token");
    expect(options.body).toContain("222222");
  });

  it("covers endpoint builders across auth, alertmanager, loki, tempo, resolver, and grafana", async () => {
    api.setAuthToken("tk");
    api.setUserOrgIds(["tenant-a", "tenant-b"]);

    await api.fetchInfo();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/");

    await api.fetchHealth();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/health");

    await api.fetchSystemMetrics();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/system/metrics");

    await api.getSystemQuotas("org-9");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/system/quotas?orgId=org-9");

    await api.getOjoReleases();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/system/ojo/releases");

    await api.login("alice", "pw", "777777");
    let [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("POST");
    expect(options.body).toContain('"mfa_code":"777777"');

    await api.refreshSession();
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("GET");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/me");

    await api.getCurrentUserNoRedirect();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/me");

    await api.disableMFA({ current_password: "cur", code: "111111" });
    [, options] = fetch.mock.calls.at(-1);
    expect(options.body).toContain('"current_password":"cur"');

    await api.logout();
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("POST");

    await api.resetUserMFA("u/1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/users/u%2F1/mfa/reset");

    await api.resetUserPasswordTemp("u/2");
    expect(fetch.mock.calls.at(-1)[0]).toContain(
      "/api/auth/users/u%2F2/password/reset-temp",
    );

    await api.getAuthMode();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/mode");

    await api.getOIDCAuthorizeUrl("https://app/cb", {
      state: "s",
      nonce: "n",
      code_challenge: "c",
      code_challenge_method: "S256",
    });
    [, options] = fetch.mock.calls.at(-1);
    expect(options.body).toContain('"redirect_uri":"https://app/cb"');
    expect(options.body).toContain('"code_challenge_method":"S256"');

    await api.exchangeOIDCCode("code-1", "https://app/cb", {
      state: "s",
      transaction_id: "tx",
      code_verifier: "verifier",
    });
    [, options] = fetch.mock.calls.at(-1);
    expect(options.body).toContain('"transaction_id":"tx"');

    await api.register("alice", "a@example.com", "pw", "Alice");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.body).toContain('"full_name":"Alice"');

    await api.updateCurrentUser({ full_name: "Alice 2" });
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("PUT");

    await api.createApiKey({ name: "k1" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/api-keys");

    await api.updateApiKey("k-1", { desc: "x" });
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("PATCH");

    await api.regenerateApiKeyOtlpToken("k-1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/otlp-token/regenerate");

    await api.deleteApiKey("k-1");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.getApiKeyShares("k-2");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/api-keys/k-2/shares");

    await api.deleteApiKeyShare("k-2", "u-7");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/api-keys/k-2/shares/u-7");

    await api.getAuditLogs({ actor: "alice", action: "login" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("actor=alice");

    await api.exportAuditLogs({ action: "create" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/audit-logs/export?action=create");

    await api.createUser({ username: "new-user" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/users");

    await api.updateUser("u-1", { enabled: false });
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("PUT");

    await api.deleteUser("u-1");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.createGroup({ name: "ops" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/groups");

    await api.updateGroup("g-1", { name: "ops2" });
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("PUT");

    await api.deleteGroup("g-1");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.updateGroupMembers("g-1", ["u1", "u2"]);
    [, options] = fetch.mock.calls.at(-1);
    expect(options.body).toContain('"user_ids":["u1","u2"]');

    await api.getPermissions();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/permissions");

    await api.getRoleDefaults();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/role-defaults");

    await api.updateUserPermissions("u-1", { can_read: true });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/users/u-1/permissions");

    await api.updateGroupPermissions("g-2", { can_write: true });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/groups/g-2/permissions");

    await api.updatePassword("u-3", { current: "x", next: "y" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/users/u-3/password");

    await api.getActiveAgents();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/agents/active");

    await api.getAgents();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/agents/");

    await api.getAgentMetricVolume({
      tenantId: " tenant-a ",
      minutes: 15,
      stepSeconds: 30,
    });
    expect(fetch.mock.calls.at(-1)[0]).toContain("tenant_id=tenant-a");
    expect(fetch.mock.calls.at(-1)[0]).toContain("minutes=15");
    expect(fetch.mock.calls.at(-1)[0]).toContain("step_seconds=30");

    await api.getAlerts({
      showHidden: true,
      severity: "critical",
      correlationId: "cid-1",
      label: " svc:api ",
    });
    expect(fetch.mock.calls.at(-1)[0]).toContain("show_hidden=true");
    expect(fetch.mock.calls.at(-1)[0]).toContain("severity=critical");
    expect(fetch.mock.calls.at(-1)[0]).toContain("correlation_id=cid-1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("label=svc%3Aapi");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.headers["X-Scope-OrgID"]).toBe("tenant-a");

    await api.getAlertsByFilter({ service: "checkout" }, false);
    expect(fetch.mock.calls.at(-1)[0]).toContain("filter_labels=");
    expect(fetch.mock.calls.at(-1)[0]).toContain("active=false");

    await api.getAlertGroups();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/alerts/groups");

    await api.getSilences({ showHidden: true });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/silences?show_hidden=true");

    await api.createSilence({ name: "maint" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/silences");

    await api.deleteSilence("s/1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/silences/s%2F1");

    await api.postAlerts({ alerts: [] });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/alerts");

    await api.deleteAlerts({ severity: "critical" });
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.getAlertRules({
      showHidden: true,
      owner: "ops",
      status: "firing",
      severity: "critical",
      orgId: "org-1",
      correlationId: "cid-2",
    });
    expect(fetch.mock.calls.at(-1)[0]).toContain("owner=ops");
    expect(fetch.mock.calls.at(-1)[0]).toContain("status=firing");

    await api.setAlertRuleHidden("rule/1", false);
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/rules/rule%2F1/hide");

    await api.setSilenceHidden("sil/1", true);
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/silences/sil%2F1/hide");

    await api.getPublicAlertRules();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/public/rules");

    await api.getIncidents("open", "private", "g-1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/incidents?status=open");

    await api.getIncidentsSummary();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/incidents/summary");

    await api.updateIncident("inc/1", { status: "closed" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/incidents/inc%2F1");

    await api.createIncidentJira("inc/2", { issueType: "Bug" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/incidents/inc%2F2/jira");

    await api.getJiraConfig();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/jira/config");

    await api.updateJiraConfig({ project: "OPS" });
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("PUT");

    await api.listJiraProjects();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/jira/projects");

    await api.listJiraProjectsByIntegration("int/1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/integrations/jira/int%2F1/projects");

    await api.listJiraIssueTypes("OPS");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/jira/projects/OPS/issue-types");

    await api.listJiraIssueTypes("OPS", "int/9");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/integrations/jira/int%2F9/projects/OPS/issue-types");

    await api.listIncidentJiraComments("inc-77");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/incidents/inc-77/jira/comments");

    await api.importAlertRules({ rules: [] });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/rules/import");

    await api.getAllowedChannelTypes();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/integrations/channel-types");

    await api.createJiraIntegration({ name: "jira" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/integrations/jira");

    await api.updateJiraIntegration("j/1", { name: "jira2" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/integrations/jira/j%2F1");

    await api.deleteJiraIntegration("j/1");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.createAlertRule({ name: "r" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/rules");

    await api.updateAlertRule("r/1", { name: "r2" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/rules/r%2F1");

    await api.deleteAlertRule("r/1");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.testAlertRule("r/2");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("POST");

    await api.createNotificationChannel({ type: "email" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/channels");

    await api.updateNotificationChannel("ch/1", { name: "ops" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/channels/ch%2F1");

    await api.deleteNotificationChannel("ch/1");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.testNotificationChannel("ch/2");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("POST");

    await api.listMetricNames("org-9");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/metrics/names?orgId=org-9");

    await api.evaluatePromql("up", "org-2", { sampleLimit: 10 });
    expect(fetch.mock.calls.at(-1)[0]).toContain("sampleLimit=10");

    await api.listMetricLabels("org-2");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/metrics/labels?orgId=org-2");

    await api.listMetricLabelValues("service", "org-3", { metricName: "http_requests_total" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("label-values/service?orgId=org-3");
    expect(fetch.mock.calls.at(-1)[0]).toContain("metricName=http_requests_total");

    await api.queryLogs({
      query: '{job="api"}',
      limit: 0,
      start: "100",
      end: "200",
      direction: "forward",
      step: "30",
    });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/loki/query?");
    expect(fetch.mock.calls.at(-1)[0]).toContain("limit=1");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.headers["X-Scope-OrgID"]).toBe("tenant-a");

    await api.getLabels();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/loki/labels");

    await api.getLabelValues("pod/name", { query: "{app='x'}", start: "1", end: "2" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/loki/label/pod%2Fname/values?");

    await api.searchLogs({ pattern: "err", labels: { app: "x" }, start: "1", end: "2" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/loki/search");

    await api.filterLogs({ labels: { app: "x" }, filters: ["error"] });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/loki/filter");

    await api.aggregateLogs("sum(rate(x[5m]))", { step: 120 });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/loki/aggregate?");

    await api.getLogVolume("{app='x'}", { step: 90 });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/loki/volume?");

    await api.searchTraces({
      service: "checkout",
      operation: "GET /orders",
      minDuration: "10ms",
      maxDuration: "1s",
      start: "100",
      end: "200",
      limit: 25,
      fetchFull: true,
    });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/tempo/traces/search?");
    expect(fetch.mock.calls.at(-1)[0]).toContain("fetchFull=true");

    await api.fetchTempoServices();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/tempo/services");

    await api.getTrace("trace/1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/tempo/traces/trace%2F1");

    await api.createRcaAnalyzeJob({ config: {} });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/analyze/jobs");

    await api.listRcaJobs({ state: "running", owner: "ops" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("state=running");

    await api.getRcaJob("job/1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/analyze/jobs/job%2F1");

    await api.getRcaJobResult("job/1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/analyze/jobs/job%2F1/result");

    await api.getRcaReportById("rep/1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/reports/rep%2F1");

    await api.deleteRcaReport("rep/1");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.fetchRcaMetricAnomalies({});
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/anomalies/metrics");

    await api.fetchRcaLogPatterns({});
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/anomalies/logs/patterns");

    await api.fetchRcaLogBursts({});
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/anomalies/logs/bursts");

    await api.fetchRcaTraceAnomalies({});
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/anomalies/traces");

    await api.fetchRcaCorrelate({});
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/correlate");

    await api.fetchRcaTopology({});
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/topology/blast-radius");

    await api.fetchRcaSloBurn({});
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/slo/burn");

    await api.fetchRcaForecast({}, { horizon: 12 });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/forecast/trajectory?horizon=12");

    await api.fetchRcaGranger({}, { max_lag: 6 });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/causal/granger?max_lag=6");

    await api.fetchRcaBayesian({});
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/causal/bayesian");

    await api.getRcaMlWeights();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/ml/weights");

    await api.submitRcaMlWeightFeedback("trace-a", true);
    expect(fetch.mock.calls.at(-1)[0]).toContain("signal=trace-a");
    expect(fetch.mock.calls.at(-1)[0]).toContain("was_correct=true");

    await api.resetRcaMlWeights();
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("POST");

    await api.getRcaDeployments();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/resolver/events/deployments");

    await api.searchDashboards({
      query: "cpu",
      uid: "uid-1",
      labelKey: "service",
      labelValue: "checkout",
      teamId: "g-1",
      folderId: 5,
      folderUid: "f-uid",
      showHidden: true,
      tag: "ops",
      starred: true,
    });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/dashboards/search?");
    expect(fetch.mock.calls.at(-1)[0]).toContain("folderIds=5");
    expect(fetch.mock.calls.at(-1)[0]).toContain("folderUIDs=f-uid");
    expect(fetch.mock.calls.at(-1)[0]).toContain("show_hidden=true");

    await api.getDashboard("d/1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/dashboards/d%2F1");

    await api.createDashboard({ title: "One" }, "overwrite=true");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/dashboards?overwrite=true");

    await api.updateDashboard("d/1", { title: "Two" }, "message=rename");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/dashboards/d%2F1?message=rename");

    await api.deleteDashboard("d/2");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.toggleDashboardHidden("d/3", false);
    [, options] = fetch.mock.calls.at(-1);
    expect(options.body).toContain('"hidden":false');

    await api.getDashboardFilterMeta();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/dashboards/meta/filters");

    await api.getDatasource("ds/1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/datasources/ds%2F1");

    await api.createDatasource({ name: "prom" }, "x-org=1");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/datasources?x-org=1");

    await api.updateDatasource("uid/9", { name: "prom2" }, "dryRun=true");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/datasources/uid%2F9?dryRun=true");

    await api.deleteDatasource("uid/9");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.getDatasourceFilterMeta();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/datasources/meta/filters");

    await api.getFolders({ showHidden: true });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/folders?show_hidden=true");

    await api.createFolder("Ops", "overwrite=true", true);
    [, options] = fetch.mock.calls.at(-1);
    expect(options.body).toContain('"allowDashboardWrites":true');

    await api.deleteFolder("f/1");
    [, options] = fetch.mock.calls.at(-1);
    expect(options.method).toBe("DELETE");

    await api.updateFolder("f/2", { title: "Renamed" }, "overwrite=true");
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/folders/f%2F2?overwrite=true");

    await api.toggleFolderHidden("f/3", false);
    [, options] = fetch.mock.calls.at(-1);
    expect(options.body).toContain('"hidden":false');
  });

  it("covers default/falsey query filter branches", async () => {
    await api.getSystemQuotas();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/system/quotas");

    await api.getUsers({ q: "", page: null, per_page: undefined });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/users");
    expect(fetch.mock.calls.at(-1)[0]).not.toContain("?");

    await api.getGroups({ q: "", role: undefined });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/auth/groups");

    await api.getAlerts({ severity: "all", correlationId: "all", label: "   " });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/alerts");

    await api.getAlertRules({
      owner: "all",
      status: "all",
      severity: "all",
      orgId: "all",
      correlationId: "   ",
    });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/alertmanager/rules");

    await api.searchDashboards({ query: "" });
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/dashboards/search");

    await api.getDatasources();
    expect(fetch.mock.calls.at(-1)[0]).toContain("/api/grafana/datasources");
  });

  it("returns plain text for non-json responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        statusText: "OK",
        headers: { get: () => "text/plain" },
        text: async () => "pong",
        json: async () => ({ never: true }),
      })),
    );

    const result = await api.fetchHealth();
    expect(result).toBe("pong");
  });
});
