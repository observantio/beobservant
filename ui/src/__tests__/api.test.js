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
});
