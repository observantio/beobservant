import React, { useState, useEffect } from 'react'
import {
  searchDashboards, getDashboard, createDashboard, updateDashboard, deleteDashboard,
  getDatasources, getDatasource, createDatasource, updateDatasource, deleteDatasource,
  getFolders, createFolder, deleteFolder
} from '../api'
import { Card, Button, Input, Alert, Badge, Spinner, Modal, ConfirmDialog, Select, Checkbox } from '../components/ui'

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'https://localhost/grafana'

const DATASOURCE_TYPES = [
  { value: 'prometheus', label: 'Prometheus', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <rect x="3" y="11" width="4" height="10" rx="1" />
      <rect x="9" y="7" width="4" height="14" rx="1" />
      <rect x="15" y="3" width="4" height="18" rx="1" />
    </svg>
  )},
  { value: 'loki', label: 'Loki', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M3 7h18M3 12h18M3 17h18" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )},
  { value: 'tempo', label: 'Tempo', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <circle cx="11" cy="11" r="6" strokeWidth="2" />
      <path d="M21 21l-4.3-4.3" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )},
  { value: 'graphite', label: 'Graphite', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M3 3v18h18" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 13l4-4 4 6 4-10" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )},
  { value: 'influxdb', label: 'InfluxDB', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M12 2v20" strokeWidth="2" strokeLinecap="round" />
      <path d="M5 7c2 4 4 6 7 6s5-2 7-6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )},
  { value: 'elasticsearch', label: 'Elasticsearch', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M12 2l7 4v8l-7 4-7-4V6l7-4z" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )},
]

export default function GrafanaPage() {
  const [activeTab, setActiveTab] = useState('dashboards')
  const [dashboards, setDashboards] = useState([])
  const [datasources, setDatasources] = useState([])
  const [folders, setFolders] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  // Dashboard editor state
  const [showDashboardEditor, setShowDashboardEditor] = useState(false)
  const [editingDashboard, setEditingDashboard] = useState(null)
  const [dashboardForm, setDashboardForm] = useState({
    title: '',
    tags: '',
    folderId: 0,
    refresh: '30s',
    datasourceUid: '',
  })

  // Datasource editor state
  const [showDatasourceEditor, setShowDatasourceEditor] = useState(false)
  const [editingDatasource, setEditingDatasource] = useState(null)
  const [datasourceForm, setDatasourceForm] = useState({
    name: '',
    type: 'prometheus',
    url: '',
    isDefault: false,
    access: 'proxy',
  })

  // Folder creator state
  const [showFolderCreator, setShowFolderCreator] = useState(false)
  const [folderName, setFolderName] = useState('')

  // Confirm dialog state
  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: null,
    variant: 'danger'
  })

  useEffect(() => {
    loadData()
  }, [activeTab])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      if (activeTab === 'dashboards') {
        const [dashboardsData, foldersData, datasourcesData] = await Promise.all([
          searchDashboards().catch(() => []),
          getFolders().catch(() => []),
          getDatasources().catch(() => []),
        ])
        setDashboards(dashboardsData)
        setFolders(foldersData)
        setDatasources(datasourcesData)
      } else if (activeTab === 'datasources') {
        const datasourcesData = await getDatasources().catch(() => [])
        setDatasources(datasourcesData)
      } else if (activeTab === 'folders') {
        const foldersData = await getFolders().catch(() => [])
        setFolders(foldersData)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function onSearch(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await searchDashboards(query)
      setDashboards(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function openDashboardEditor(dashboard = null) {
    if (dashboard) {
      setEditingDashboard(dashboard)
      setDashboardForm({
        title: dashboard.title || '',
        tags: dashboard.tags?.join(', ') || '',
        folderId: dashboard.folderId || 0,
        refresh: dashboard.refresh || '30s',
        datasourceUid: '',
      })
    } else {
      setEditingDashboard(null)
      setDashboardForm({
        title: '',
        tags: '',
        folderId: 0,
        refresh: '30s',
        datasourceUid: '',
      })
    }
    setShowDashboardEditor(true)
  }

  async function saveDashboard() {
    setError(null)
    setSuccess(null)
    try {
      const tags = dashboardForm.tags
        .split(',')
        .map(t => t.trim())
        .filter(Boolean)

      const selectedDatasource = datasources.find(ds => ds.uid === dashboardForm.datasourceUid)

      const payload = {
        dashboard: {
          title: dashboardForm.title,
          tags,
          refresh: dashboardForm.refresh,
          panels: [],
          timezone: 'browser',
          schemaVersion: 16,
          editable: true,
          templating: selectedDatasource
            ? {
                list: [
                  {
                    name: 'ds_default',
                    label: 'Datasource',
                    type: 'datasource',
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
        folderId: parseInt(dashboardForm.folderId) || 0,
        overwrite: !!editingDashboard,
      }

      if (editingDashboard) {
        payload.dashboard.uid = editingDashboard.uid
        await updateDashboard(editingDashboard.uid, payload)
        setSuccess('Dashboard updated successfully')
      } else {
        await createDashboard(payload)
        setSuccess('Dashboard created successfully')
      }

      setShowDashboardEditor(false)
      loadData()
    } catch (e) {
      setError(e.message)
    }
  }

  function handleDeleteDashboard(dashboard) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Dashboard',
      message: `Are you sure you want to delete "${dashboard.title}"? This action cannot be undone.`,
      variant: 'danger',
      onConfirm: async () => {
        setError(null)
        setSuccess(null)
        try {
          await deleteDashboard(dashboard.uid)
          setSuccess('Dashboard deleted successfully')
          loadData()
        } catch (e) {
          setError(e.message)
        }
      }
    })
  }

  function openDatasourceEditor(datasource = null) {
    if (datasource) {
      setEditingDatasource(datasource)
      setDatasourceForm({
        name: datasource.name || '',
        type: datasource.type || 'prometheus',
        url: datasource.url || '',
        isDefault: datasource.isDefault || false,
        access: datasource.access || 'proxy',
      })
    } else {
      setEditingDatasource(null)
      setDatasourceForm({
        name: '',
        type: 'prometheus',
        url: '',
        isDefault: false,
        access: 'proxy',
      })
    }
    setShowDatasourceEditor(true)
  }

  async function saveDatasource() {
    setError(null)
    setSuccess(null)
    try {
      const payload = {
        name: datasourceForm.name,
        type: datasourceForm.type,
        url: datasourceForm.url,
        access: datasourceForm.access,
        isDefault: datasourceForm.isDefault,
        jsonData: {},
      }

      if (editingDatasource) {
        await updateDatasource(editingDatasource.uid, payload)
        setSuccess('Datasource updated successfully')
      } else {
        await createDatasource(payload)
        setSuccess('Datasource created successfully')
      }

      setShowDatasourceEditor(false)
      loadData()
    } catch (e) {
      setError(e.message)
    }
  }

  function handleDeleteDatasource(datasource) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Datasource',
      message: `Are you sure you want to delete "${datasource.name}"? This will affect all dashboards using this datasource.`,
      variant: 'danger',
      onConfirm: async () => {
        setError(null)
        setSuccess(null)
        try {
          await deleteDatasource(datasource.uid)
          setSuccess('Datasource deleted successfully')
          loadData()
        } catch (e) {
          setError(e.message)
        }
      }
    })
  }

  async function handleCreateFolder() {
    if (!folderName.trim()) return
    
    setError(null)
    setSuccess(null)
    try {
      await createFolder(folderName.trim())
      setSuccess('Folder created successfully')
      setShowFolderCreator(false)
      setFolderName('')
      loadData()
    } catch (e) {
      setError(e.message)
    }
  }

  function handleDeleteFolder(folder) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Folder',
      message: `Are you sure you want to delete "${folder.title}"? All dashboards in this folder will be moved to General.`,
      variant: 'danger',
      onConfirm: async () => {
        setError(null)
        setSuccess(null)
        try {
          await deleteFolder(folder.uid)
          setSuccess('Folder deleted successfully')
          loadData()
        } catch (e) {
          setError(e.message)
        }
      }
    })
  }

  function getDatasourceIcon(type) {
    const found = DATASOURCE_TYPES.find(t => t.value === type)
    return found ? found.icon : '🔧'
  }

  function openInGrafana(path) {
    window.open(`${GRAFANA_URL}${path}`, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-sre-text mb-2">Grafana Dashboard Manager</h1>
          <p className="text-sre-text-muted">Manage dashboards, datasources, and folders with powerful SRE tooling</p>
        </div>
        <Button
          onClick={() => openInGrafana('/')}
          variant="outline"
          className="flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
          Open Grafana
        </Button>
      </div>

      {error && (
        <Alert variant="error" className="mb-6" onClose={() => setError(null)}>
          <strong>Error:</strong> {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-6" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Tabs */}
      <div className="flex gap-2 mb-6 border-b border-sre-border">
        {[
          { id: 'dashboards', label: 'Dashboards', icon: (
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zM13 21h8V11h-8v10zM13 3v6h8V3h-8z" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) },
          { id: 'datasources', label: 'Datasources', icon: (
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M6 3h12v4H6zM6 21h12v-4H6zM3 8h18v8H3z" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) },
          { id: 'folders', label: 'Folders', icon: (
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 font-medium transition-colors relative flex items-center ${
              activeTab === tab.id
                ? 'text-sre-primary border-b-2 border-sre-primary'
                : 'text-sre-text-muted hover:text-sre-text'
            }`}
          >
            <span className="mr-2 flex items-center">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="py-12">
          <Spinner size="lg" />
        </div>
      ) : (
        <>
          {/* Dashboards Tab */}
          {activeTab === 'dashboards' && (
            <>
              <div className="mb-6 flex gap-3">
                <form onSubmit={onSearch} className="flex gap-3 flex-1">
                  <Input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search dashboards by name or tag..."
                    className="flex-1"
                  />
                  <Button type="submit">
                    <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    Search
                  </Button>
                </form>
                <Button onClick={() => openDashboardEditor()} variant="primary">
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  New Dashboard
                </Button>
              </div>

              <Card
                title="Dashboards"
                subtitle={`${dashboards.length} dashboard${dashboards.length !== 1 ? 's' : ''} found`}
              >
                {dashboards.length ? (
                  <div className="space-y-3">
                    {dashboards.map((d) => (
                      <div
                        key={d.uid}
                        className="p-4 bg-sre-bg-alt border border-sre-border rounded-lg hover:border-sre-primary/50 transition-all group"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-3 mb-2">
                              <svg className="w-5 h-5 text-sre-primary flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                              </svg>
                              <h4 className="font-semibold text-sre-text text-lg">
                                {d.title}
                              </h4>
                              {d.isStarred && (
                                <span className="text-yellow-500">⭐</span>
                              )}
                            </div>
                            
                            <div className="flex flex-wrap gap-2 mb-2">
                              {d.tags?.map((tag, idx) => (
                                <Badge key={idx} variant="info">{tag}</Badge>
                              ))}
                              {d.folderTitle && (
                                <Badge variant="outline">
                                  <svg className="inline-block w-4 h-4 mr-1 align-text-bottom" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                    <path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                                  </svg>
                                  {d.folderTitle}
                                </Badge>
                              )}
                            </div>

                            {d.uid && (
                              <p className="text-xs text-sre-text-muted font-mono mt-1">
                                UID: {d.uid}
                              </p>
                            )}
                            {d.url && (
                              <p className="text-xs text-sre-text-subtle mt-1">
                                {d.url}
                              </p>
                            )}
                          </div>

                          <div className="flex gap-2 ml-4">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openInGrafana(d.url)}
                              title="Open in Grafana"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                              </svg>
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openDashboardEditor(d)}
                              title="Edit"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                              </svg>
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDeleteDashboard(d)}
                              className="text-red-500 hover:text-red-600"
                              title="Delete"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <svg className="w-16 h-16 mx-auto text-sre-text-subtle mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                    <p className="text-sre-text-muted text-lg mb-4">No dashboards found</p>
                    <Button onClick={() => openDashboardEditor()} variant="primary">
                      Create Your First Dashboard
                    </Button>
                  </div>
                )}
              </Card>
            </>
          )}

          {/* Datasources Tab */}
          {activeTab === 'datasources' && (
            <>
              <div className="mb-6 flex justify-end">
                <Button onClick={() => openDatasourceEditor()} variant="primary">
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  New Datasource
                </Button>
              </div>

              <Card
                title="Datasources"
                subtitle={`${datasources.length} datasource${datasources.length !== 1 ? 's' : ''} configured`}
              >
                {datasources.length ? (
                  <div className="space-y-3">
                    {datasources.map((ds) => (
                      <div
                        key={ds.uid}
                        className="p-4 bg-sre-bg-alt border border-sre-border rounded-lg hover:border-sre-accent/50 transition-all"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-3 mb-2">
                              <span className="text-2xl">{getDatasourceIcon(ds.type)}</span>
                              <h4 className="font-semibold text-sre-text text-lg">{ds.name}</h4>
                            </div>
                            
                            <div className="flex items-center gap-2 mb-2">
                              <Badge variant="info">{ds.type}</Badge>
                              {ds.isDefault && <Badge variant="neon">default</Badge>}
                              <Badge variant="outline">{ds.access}</Badge>
                            </div>

                            <p className="text-sm text-sre-text-muted mb-1">
                              <strong>URL:</strong> {ds.url}
                            </p>

                            {ds.uid && (
                              <p className="text-xs text-sre-text-muted font-mono">
                                UID: {ds.uid}
                              </p>
                            )}
                          </div>

                          <div className="flex gap-2 ml-4">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openDatasourceEditor(ds)}
                              title="Edit"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                              </svg>
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDeleteDatasource(ds)}
                              className="text-red-500 hover:text-red-600"
                              title="Delete"
                              disabled={ds.isDefault}
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <svg className="w-16 h-16 mx-auto text-sre-text-subtle mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                    </svg>
                    <p className="text-sre-text-muted text-lg mb-4">No datasources configured</p>
                    <Button onClick={() => openDatasourceEditor()} variant="primary">
                      Add Your First Datasource
                    </Button>
                  </div>
                )}
              </Card>
            </>
          )}

          {/* Folders Tab */}
          {activeTab === 'folders' && (
            <>
              <div className="mb-6 flex justify-end">
                <Button onClick={() => setShowFolderCreator(true)} variant="primary">
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  New Folder
                </Button>
              </div>

              <Card
                title="Folders"
                subtitle={`${folders.length} folder${folders.length !== 1 ? 's' : ''} available`}
              >
                {folders.length ? (
                  <div className="space-y-3">
                    {folders.map((folder) => (
                      <div
                        key={folder.uid}
                        className="p-4 bg-sre-bg-alt border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <svg className="w-6 h-6 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                            </svg>
                            <div>
                              <h4 className="font-semibold text-sre-text">{folder.title}</h4>
                              {folder.uid && (
                                <p className="text-xs text-sre-text-muted font-mono">
                                  UID: {folder.uid}
                                </p>
                              )}
                            </div>
                          </div>

                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteFolder(folder)}
                            className="text-red-500 hover:text-red-600"
                            title="Delete Folder"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <svg className="w-16 h-16 mx-auto text-sre-text-subtle mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                    </svg>
                    <p className="text-sre-text-muted text-lg mb-4">No folders available</p>
                    <Button onClick={() => setShowFolderCreator(true)} variant="primary">
                      Create Your First Folder
                    </Button>
                  </div>
                )}
              </Card>
            </>
          )}
        </>
      )}

      {/* Dashboard Editor Modal */}
      <Modal
        isOpen={showDashboardEditor}
        onClose={() => setShowDashboardEditor(false)}
        title={editingDashboard ? 'Edit Dashboard' : 'Create New Dashboard'}
        size="md"
        footer={
          <div className="flex gap-3 justify-end">
            <Button
              variant="ghost"
              onClick={() => setShowDashboardEditor(false)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={saveDashboard}
              disabled={!dashboardForm.title.trim()}
            >
              {editingDashboard ? 'Update Dashboard' : 'Create Dashboard'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Input
            label="Dashboard Title *"
            value={dashboardForm.title}
            onChange={(e) => setDashboardForm({ ...dashboardForm, title: e.target.value })}
            placeholder="My Awesome Dashboard"
            required
          />

          <Input
            label="Tags (comma-separated)"
            value={dashboardForm.tags}
            onChange={(e) => setDashboardForm({ ...dashboardForm, tags: e.target.value })}
            placeholder="production, metrics, monitoring"
            helperText="Use tags to categorize and filter dashboards"
          />

          <Select
            label="Folder"
            value={dashboardForm.folderId}
            onChange={(e) => setDashboardForm({ ...dashboardForm, folderId: e.target.value })}
          >
            <option value="0">General</option>
            {folders.map((folder) => (
              <option key={folder.id} value={folder.id}>
                {folder.title}
              </option>
            ))}
          </Select>

          <Select
            label="Default Datasource"
            value={dashboardForm.datasourceUid}
            onChange={(e) => setDashboardForm({ ...dashboardForm, datasourceUid: e.target.value })}
            helperText="Optional: Sets the default datasource variable for this dashboard"
          >
            <option value="">-- None --</option>
            {datasources.map((ds) => (
              <option key={ds.uid} value={ds.uid}>
                {ds.name} ({ds.type})
              </option>
            ))}
          </Select>

          <Select
            label="Auto-refresh Interval"
            value={dashboardForm.refresh}
            onChange={(e) => setDashboardForm({ ...dashboardForm, refresh: e.target.value })}
            helperText="How often the dashboard should automatically refresh"
          >
            <option value="">No auto-refresh</option>
            <option value="5s">5 seconds</option>
            <option value="10s">10 seconds</option>
            <option value="30s">30 seconds</option>
            <option value="1m">1 minute</option>
            <option value="5m">5 minutes</option>
            <option value="15m">15 minutes</option>
            <option value="30m">30 minutes</option>
            <option value="1h">1 hour</option>
          </Select>
        </div>
      </Modal>

      {/* Datasource Editor Modal */}
      <Modal
        isOpen={showDatasourceEditor}
        onClose={() => setShowDatasourceEditor(false)}
        title={editingDatasource ? 'Edit Datasource' : 'Create New Datasource'}
        size="md"
        footer={
          <div className="flex gap-3 justify-end">
            <Button
              variant="ghost"
              onClick={() => setShowDatasourceEditor(false)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={saveDatasource}
              disabled={!datasourceForm.name.trim() || !datasourceForm.url.trim()}
            >
              {editingDatasource ? 'Update Datasource' : 'Create Datasource'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Input
            label="Datasource Name *"
            value={datasourceForm.name}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, name: e.target.value })}
            placeholder="My Prometheus"
            required
          />

          <Select
            label="Type *"
            value={datasourceForm.type}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, type: e.target.value })}
            disabled={!!editingDatasource}
            helperText={editingDatasource ? "Type cannot be changed after creation" : "Select the datasource type"}
          >
            {DATASOURCE_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.icon} {type.label}
              </option>
            ))}
          </Select>

          <Input
            label="URL *"
            value={datasourceForm.url}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, url: e.target.value })}
            placeholder="http://prometheus:9090"
            helperText="The URL where the datasource is accessible"
            required
          />

          <Select
            label="Access Mode"
            value={datasourceForm.access}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, access: e.target.value })}
            helperText="Proxy: Access via Grafana server. Direct: Access from browser"
          >
            <option value="proxy">Server (Proxy)</option>
            <option value="direct">Browser (Direct)</option>
          </Select>

          <Checkbox
            label="Set as default datasource"
            checked={datasourceForm.isDefault}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, isDefault: e.target.checked })}
          />
        </div>
      </Modal>

      {/* Folder Creator Modal */}
      <Modal
        isOpen={showFolderCreator}
        onClose={() => {
          setShowFolderCreator(false)
          setFolderName('')
        }}
        title="Create New Folder"
        size="sm"
        footer={
          <div className="flex gap-3 justify-end">
            <Button
              variant="ghost"
              onClick={() => {
                setShowFolderCreator(false)
                setFolderName('')
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleCreateFolder}
              disabled={!folderName.trim()}
            >
              Create Folder
            </Button>
          </div>
        }
      >
        <Input
          label="Folder Name *"
          value={folderName}
          onChange={(e) => setFolderName(e.target.value)}
          placeholder="Production Dashboards"
          helperText="Choose a descriptive name for your folder"
          required
          autoFocus
          onKeyPress={(e) => {
            if (e.key === 'Enter' && folderName.trim()) {
              handleCreateFolder()
            }
          }}
        />
      </Modal>

      {/* Confirmation Dialog */}
      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        onClose={() => setConfirmDialog({ ...confirmDialog, isOpen: false })}
        onConfirm={confirmDialog.onConfirm}
        title={confirmDialog.title}
        message={confirmDialog.message}
        variant={confirmDialog.variant}
        confirmText="Delete"
        cancelText="Cancel"
      />
    </div>
  )
}
