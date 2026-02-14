export function normalizeGrafanaPath(path) {
  let rawPath = '/dashboards'

  if (typeof path === 'string' && path.trim()) {
    const trimmedPath = path.trim()
    if (trimmedPath.startsWith('http://') || trimmedPath.startsWith('https://')) {
      try {
        const absoluteUrl = new URL(trimmedPath)
        rawPath = `${absoluteUrl.pathname || '/'}${absoluteUrl.search || ''}${absoluteUrl.hash || ''}`
      } catch {
        rawPath = '/dashboards'
      }
    } else {
      rawPath = trimmedPath.startsWith('/') ? trimmedPath : `/${trimmedPath}`
    }
  }

  let normalizedPath = rawPath.replace(/^\/grafana(?=\/|$)/, '') || '/dashboards'
  if (!normalizedPath.startsWith('/')) {
    normalizedPath = `/${normalizedPath}`
  }
  return normalizedPath
}

export function buildGrafanaLaunchUrl({ path, token, protocol, hostname }) {
  const proxyOrigin = `${protocol}//${hostname}:8080`
  const normalizedPath = normalizeGrafanaPath(path)
  return token
    ? `${proxyOrigin}/grafana/bootstrap?token=${encodeURIComponent(token)}&next=${encodeURI(normalizedPath)}`
    : `${proxyOrigin}${normalizedPath}`
}