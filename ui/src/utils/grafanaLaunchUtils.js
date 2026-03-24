function stripGrafanaInternalOrgId(pathnameWithQueryAndHash) {
  const [beforeHash, hash = ""] = String(pathnameWithQueryAndHash || "").split("#", 2);
  const [pathname, query = ""] = beforeHash.split("?", 2);
  if (!query) {
    return hash ? `${pathname}#${hash}` : pathname;
  }

  const params = new URLSearchParams(query);
  params.delete("orgId");
  const nextQuery = params.toString();
  const querySuffix = nextQuery ? `?${nextQuery}` : "";
  const hashSuffix = hash ? `#${hash}` : "";
  return `${pathname}${querySuffix}${hashSuffix}`;
}

export function normalizeGrafanaPath(path) {
  let rawPath = "/dashboards";

  if (typeof path === "string" && path.trim()) {
    const trimmedPath = path.trim();
    if (
      trimmedPath.startsWith("http://") ||
      trimmedPath.startsWith("https://")
    ) {
      try {
        const absoluteUrl = new URL(trimmedPath);
        rawPath = `${absoluteUrl.pathname || "/"}${absoluteUrl.search || ""}${absoluteUrl.hash || ""}`;
      } catch {
        rawPath = "/dashboards";
      }
    } else {
      rawPath = trimmedPath.startsWith("/") ? trimmedPath : `/${trimmedPath}`;
    }
  }

  let normalizedPath =
    rawPath.replace(/^\/grafana(?=\/|$)/, "") || "/dashboards";
  if (!normalizedPath.startsWith("/")) {
    normalizedPath = `/${normalizedPath}`;
  }
  return stripGrafanaInternalOrgId(normalizedPath);
}

import { APP_ORG_KEY, GRAFANA_URL } from "./constants";

export function buildGrafanaLaunchUrl({ path, protocol, hostname }) {
  const normalizedPath = normalizeGrafanaPath(path);
  let grafanaBase = "";
  try {
    const parsed = new URL(GRAFANA_URL);
    grafanaBase = (parsed.pathname || "").replace(/\/$/, "");
  } catch {
    grafanaBase = "/grafana";
  }
  const proxyOrigin = `${protocol}//${hostname}:8080`;
  const separator = normalizedPath.includes("?") ? "&" : "?";
  return `${proxyOrigin}${grafanaBase}${normalizedPath}${separator}org-key=${encodeURIComponent(APP_ORG_KEY)}`;
}

export function buildGrafanaBootstrapUrl({ path, protocol, hostname }) {
  const normalizedPath = normalizeGrafanaPath(path);
  const proxyOrigin = `${protocol}//${hostname}:8080`;
  const encoded = encodeURIComponent(normalizedPath).replace(/%2F/g, "/");
  return `${proxyOrigin}/grafana/bootstrap?next=${encoded}`;
}
