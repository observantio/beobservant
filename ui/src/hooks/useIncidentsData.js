import { useCallback, useEffect, useState } from 'react'
import { getIncidents, getUsers } from '../api'

export function useIncidentsData({ visibilityTab = 'public', selectedGroup = '', showHiddenResolved = false, canReadUsers = false } = {}) {
  const [incidents, setIncidents] = useState([])
  const [incidentUsers, setIncidentUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (showHiddenResolved) {
        const [openIncidents, resolvedIncidents, usersData] = await Promise.all([
          getIncidents(undefined, visibilityTab, visibilityTab === 'group' ? selectedGroup : undefined).catch(() => []),
          getIncidents('resolved', visibilityTab, visibilityTab === 'group' ? selectedGroup : undefined).catch(() => []),
          canReadUsers ? getUsers().catch(() => []) : Promise.resolve([]),
        ])
        const mergedIncidents = []
        const seenIncidentIds = new Set()
        for (const incident of (openIncidents || [])) {
          if (!incident?.id || seenIncidentIds.has(incident.id)) continue
          seenIncidentIds.add(incident.id)
          mergedIncidents.push(incident)
        }
        for (const incident of (resolvedIncidents || [])) {
          if (!incident?.id || seenIncidentIds.has(incident.id)) continue
          seenIncidentIds.add(incident.id)
          mergedIncidents.push(incident)
        }
        setIncidents(mergedIncidents)
        setIncidentUsers(Array.isArray(usersData) ? usersData : [])
      } else {
        const [incidentsData, usersData] = await Promise.all([
          getIncidents(undefined, visibilityTab, visibilityTab === 'group' ? selectedGroup : undefined).catch(() => []),
          canReadUsers ? getUsers().catch(() => []) : Promise.resolve([]),
        ])
        setIncidents(Array.isArray(incidentsData) ? incidentsData : [])
        setIncidentUsers(Array.isArray(usersData) ? usersData : [])
      }
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }, [visibilityTab, selectedGroup, showHiddenResolved, canReadUsers])

  useEffect(() => {
    loadData()
  }, [loadData])

  return { incidents, incidentUsers, loading, error, refresh: loadData, setIncidents, setIncidentUsers }
}
