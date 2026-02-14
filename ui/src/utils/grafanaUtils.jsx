import { DATASOURCE_TYPES as DS_TYPES } from './constants'

export const GRAFANA_DATASOURCE_TYPES = DS_TYPES
  .filter((datasourceType) => ['prometheus', 'loki', 'tempo'].includes(datasourceType.value))
  .map((datasourceType) => {
    const icons = {
      prometheus: (
        <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <rect x="3" y="11" width="4" height="10" rx="1" />
          <rect x="9" y="7" width="4" height="14" rx="1" />
          <rect x="15" y="3" width="4" height="18" rx="1" />
        </svg>
      ),
      loki: (
        <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M3 7h18M3 12h18M3 17h18" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ),
      tempo: (
        <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <circle cx="11" cy="11" r="6" strokeWidth="2" />
          <path d="M21 21l-4.3-4.3" strokeWidth="2" strokeLinecap="round" />
        </svg>
      ),
    }

    return { ...datasourceType, icon: icons[datasourceType.value] || null }
  })
