import  { useState, useEffect } from 'react'
import {
  searchDashboards, createDashboard, updateDashboard, deleteDashboard,
  getDatasources, createDatasource, updateDatasource, deleteDatasource,
  getFolders, createFolder, deleteFolder, getGroups
} from '../api'
import {  Button, Input, Modal, ConfirmDialog, Select, Checkbox } from '../components/ui'
import { useToast } from '../contexts/ToastContext'
import HelpTooltip from '../components/HelpTooltip'
import GrafanaTabs from '../components/grafana/GrafanaTabs'
import GrafanaContent from '../components/grafana/GrafanaContent'
import { useAuth } from '../contexts/AuthContext'
import { GRAFANA_URL, MIMIR_PROMETHEUS_URL, LOKI_BASE, TEMPO_URL, DATASOURCE_TYPES as DS_TYPES, VISIBILITY_OPTIONS, GRAFANA_REFRESH_INTERVALS } from '../utils/constants'

const DATASOURCE_TYPES = DS_TYPES
  .filter(dt => ['prometheus', 'loki', 'tempo'].includes(dt.value))
  .map(dt => {
  const icons = {
    prometheus: <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="3" y="11" width="4" height="10" rx="1" /><rect x="9" y="7" width="4" height="14" rx="1" /><rect x="15" y="3" width="4" height="18" rx="1" /></svg>,
    loki: <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M3 7h18M3 12h18M3 17h18" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
    tempo: <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="11" cy="11" r="6" strokeWidth="2" /><path d="M21 21l-4.3-4.3" strokeWidth="2" strokeLinecap="round" /></svg>,
  }
  return { ...dt, icon: icons[dt.value] || null }
})

function openInGrafana(path) {
  window.open(`${GRAFANA_URL}${path}`, '_blank', 'noopener,noreferrer')
}



export default function GrafanaPage() { // NOSONAR
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState('dashboards')
  const [dashboards, setDashboards] = useState([])
  const [datasources, setDatasources] = useState([])
  const [folders, setFolders] = useState([])
  const [groups, setGroups] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)

  const toast = useToast()

  // Centralized API error handling for this page.
  // Permission errors (403) are already shown globally via toast; avoid duplicating them here.
  function handleApiError(e) {
    if (!e) return
    if (e.status === 403) return // already shown in toast

    const msg = e.message || String(e || '')
    const lower = msg.toLowerCase()
    // Suppress Grafana 'not found / access denied / update failed' messages as toasts already show them
    if (lower.includes('not found') && (lower.includes('access denied') || lower.includes('update failed'))) return

    toast.error(msg)
  }

  // Dashboard editor state
  const [showDashboardEditor, setShowDashboardEditor] = useState(false)
  const [editingDashboard, setEditingDashboard] = useState(null)
  const [dashboardForm, setDashboardForm] = useState({
    title: '',
    tags: '',
    folderId: 0,
    refresh: '30s',
    datasourceUid: '',
    visibility: 'private',
    sharedGroupIds: [],
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
    visibility: 'private',
    sharedGroupIds: [],
    apiKeyId: '',
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

  // Determine default API key for the current user
  const defaultKey = (user?.api_keys || []).find((k) => k.is_default) || (user?.api_keys || [])[0]

  useEffect(() => {
    loadData()
    loadGroups()
  }, [activeTab])

  async function loadGroups() {
    try {
      const groupsData = await getGroups().catch(() => [])
      setGroups(groupsData)
    } catch {
      // Silently handle
    }
  }

  async function loadData() {
    setLoading(true)
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
      handleApiError(e)
    } finally {
      setLoading(false)
    }
  }

  async function onSearch(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await searchDashboards(query)
      setDashboards(res)
    } catch (e) {
      handleApiError(e)
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
        visibility: 'private',
        sharedGroupIds: [],
      })
    } else {
      setEditingDashboard(null)
      setDashboardForm({
        title: '',
        tags: '',
        folderId: 0,
        refresh: '30s',
        datasourceUid: '',
        visibility: 'private',
        sharedGroupIds: [],
      })
    }
    setShowDashboardEditor(true)
  }

  async function saveDashboard() {
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
        folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
        overwrite: !!editingDashboard,
      }

      // Build query params for visibility
      const params = new URLSearchParams({
        visibility: dashboardForm.visibility,
      })
      if (dashboardForm.visibility === 'group' && dashboardForm.sharedGroupIds?.length > 0) {
        dashboardForm.sharedGroupIds.forEach(gid => params.append('shared_group_ids', gid))
      }

      if (editingDashboard) {
        payload.dashboard.uid = editingDashboard.uid
        await updateDashboard(editingDashboard.uid, payload, params.toString())
        toast.success('Dashboard updated successfully')
      } else {
        await createDashboard(payload, params.toString())
        toast.success('Dashboard created successfully')
      }

      setShowDashboardEditor(false)
      loadData()
    } catch (e) {
      handleApiError(e)
    }
  }

  function handleDeleteDashboard(dashboard) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Dashboard',
      message: `Are you sure you want to delete "${dashboard.title}"? This action cannot be undone.`,
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteDashboard(dashboard.uid)
          toast.success('Dashboard deleted successfully')
          loadData()
        } catch (e) {
          handleApiError(e)
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
        visibility: 'private',
        sharedGroupIds: [],
        apiKeyId: '',
      })
    } else {
      const defaultKey = (user?.api_keys || []).find((k) => k.is_default) || (user?.api_keys || [])[0]
      setEditingDatasource(null)
      setDatasourceForm({
        name: '',
        type: 'prometheus',
        url: '',
        isDefault: false,
        access: 'proxy',
        visibility: 'private',
        sharedGroupIds: [],
        apiKeyId: defaultKey?.id || '',
      })
    }
    setShowDatasourceEditor(true)
  }

  // Auto-fill URL based on datasource type
  useEffect(() => {
    if (editingDatasource) return // Don't auto-fill when editing existing datasource
    
    const urlMapping = {
      prometheus: MIMIR_PROMETHEUS_URL,
      loki: LOKI_BASE,
      tempo: TEMPO_URL,
    }
    
    const defaultUrl = urlMapping[datasourceForm.type]
    if (defaultUrl) {
      setDatasourceForm(prev => ({ ...prev, url: defaultUrl }))
    }
  }, [datasourceForm.type, editingDatasource])

  async function saveDatasource() {
    // Validate org_id for multi-tenant datasources
    const isMultiTenantType = ['prometheus', 'loki', 'tempo'].includes(datasourceForm.type)
    if (!editingDatasource && isMultiTenantType && !datasourceForm.apiKeyId) {
      toast.error('API key is required for Prometheus, Loki, and Tempo datasources')
      return
    }
    
    try {
      const payload = {
        name: datasourceForm.name,
        type: datasourceForm.type,
        url: datasourceForm.url,
        access: datasourceForm.access,
        isDefault: datasourceForm.isDefault,
        jsonData: {},
      }
      
      // Add org_id to payload for new multi-tenant datasources
      if (!editingDatasource && isMultiTenantType) {
        const selectedKey = (user?.api_keys || []).find((k) => k.id === datasourceForm.apiKeyId)
        payload.org_id = selectedKey?.key || user?.org_id || 'default'
      }

      // Build query params for visibility
      const params = new URLSearchParams({
        visibility: datasourceForm.visibility,
      })
      if (datasourceForm.visibility === 'group' && datasourceForm.sharedGroupIds?.length > 0) {
        datasourceForm.sharedGroupIds.forEach(gid => params.append('shared_group_ids', gid))
      }

      if (editingDatasource) {
        await updateDatasource(editingDatasource.uid, payload, params.toString())
        toast.success('Datasource updated successfully')
      } else {
        await createDatasource(payload, params.toString())
        toast.success('Datasource created successfully')
      }

      setShowDatasourceEditor(false)
      loadData()
    } catch (e) {
      handleApiError(e)
    }
  }

  function handleDeleteDatasource(datasource) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Datasource',
      message: `Are you sure you want to delete "${datasource.name}"? This will affect all dashboards using this datasource.`,
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteDatasource(datasource.uid)
          toast.success('Datasource deleted successfully')
          loadData()
        } catch (e) {
          handleApiError(e)
        }
      }
    })
  }

  async function handleCreateFolder() {
    if (!folderName.trim()) return

    try {
      await createFolder(folderName.trim())
      toast.success('Folder created successfully')
      setShowFolderCreator(false)
      setFolderName('')
      loadData()
    } catch (e) {
      handleApiError(e)
    }
  }

  function handleDeleteFolder(folder) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Folder',
      message: `Are you sure you want to delete "${folder.title}"? All dashboards in this folder will be moved to General.`,
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteFolder(folder.uid)
          toast.success('Folder deleted successfully')
          loadData()
        } catch (e) {
          handleApiError(e)
        }
      }
    })
  }

  function getDatasourceIcon(type) {
    const found = DATASOURCE_TYPES.find(t => t.value === type)
    return found ? found.icon : '🔧'
  }

  return (
    <div className="animate-fade-in">
      <GrafanaTabs activeTab={activeTab} onChange={setActiveTab} />

      <GrafanaContent
        loading={loading}
        activeTab={activeTab}
        dashboards={dashboards}
        datasources={datasources}
        folders={folders}
        query={query}
        setQuery={setQuery}
        onSearch={onSearch}
        openDashboardEditor={openDashboardEditor}
        onOpenGrafana={openInGrafana}
        onDeleteDashboard={handleDeleteDashboard}
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={handleDeleteDatasource}
        getDatasourceIcon={getDatasourceIcon}
        onCreateFolder={() => setShowFolderCreator(true)}
        onDeleteFolder={handleDeleteFolder}
      />

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
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Dashboard Title <span className="text-red-500">*</span> <HelpTooltip text="Enter a descriptive title for your dashboard that clearly identifies its purpose." />
            </label>
            <Input
              value={dashboardForm.title}
              onChange={(e) => setDashboardForm({ ...dashboardForm, title: e.target.value })}
              placeholder="My Awesome Dashboard"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Tags (comma-separated) <HelpTooltip text="Add tags to categorize and make your dashboard easier to find. Use commas to separate multiple tags." />
            </label>
            <Input
              value={dashboardForm.tags}
              onChange={(e) => setDashboardForm({ ...dashboardForm, tags: e.target.value })}
              placeholder="production, metrics, monitoring"
            />
            <p className="text-xs text-sre-text-muted mt-1">Use tags to categorize and filter dashboards</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Folder <HelpTooltip text="Choose which folder to organize this dashboard in. Use 'General' for dashboards that don't need specific organization." />
            </label>
            <Select
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
          </div>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Default Datasource <HelpTooltip text="Optional: Set a default datasource that will be pre-selected in dashboard variables for easier panel creation." />
            </label>
            <Select
              value={dashboardForm.datasourceUid}
              onChange={(e) => setDashboardForm({ ...dashboardForm, datasourceUid: e.target.value })}
            >
              <option value="">-- None --</option>
              {datasources.map((ds) => (
                <option key={ds.uid} value={ds.uid}>
                  {ds.name} ({ds.type})
                </option>
              ))}
            </Select>
            <p className="text-xs text-sre-text-muted mt-1">Optional: Sets the default datasource variable for this dashboard</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Auto-refresh Interval <HelpTooltip text="How often the dashboard should automatically refresh its data. Choose 'Off' to disable auto-refresh." />
            </label>
            <Select
              value={dashboardForm.refresh}
              onChange={(e) => setDashboardForm({ ...dashboardForm, refresh: e.target.value })}
            >
              {GRAFANA_REFRESH_INTERVALS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </Select>
            <p className="text-xs text-sre-text-muted mt-1">How often the dashboard should automatically refresh</p>
          </div>

          <div className="border-t border-sre-border pt-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Visibility <HelpTooltip text="Control who can view and edit this dashboard. Private dashboards are only visible to you." />
              </label>
              <Select
                value={dashboardForm.visibility}
                onChange={(e) => {
                  setDashboardForm({ ...dashboardForm, visibility: e.target.value, sharedGroupIds: [] })
                }}
              >
                {VISIBILITY_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </Select>
              <p className="text-xs text-sre-text-muted mt-1">Control who can access this dashboard</p>
            </div>

            {dashboardForm.visibility === 'group' && (
              <div className="mt-4">
                <label htmlFor="shared-groups" className="block text-sm font-medium text-sre-text mb-2">
                  Shared Groups <HelpTooltip text="Select which user groups can view and edit this dashboard." />
                </label>
                <div id="shared-groups" className="space-y-2 max-h-40 overflow-y-auto border border-sre-border rounded p-3">
                  {groups.map(group => (
                    <Checkbox
                      key={group.id}
                      label={group.name}
                      checked={dashboardForm.sharedGroupIds.includes(group.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setDashboardForm({
                            ...dashboardForm,
                            sharedGroupIds: [...dashboardForm.sharedGroupIds, group.id]
                          })
                        } else {
                          setDashboardForm({
                            ...dashboardForm,
                            sharedGroupIds: dashboardForm.sharedGroupIds.filter(id => id !== group.id)
                          })
                        }
                      }}
                    />
                  ))}
                  {groups.length === 0 && (
                    <p className="text-sm text-sre-text-muted">No groups available</p>
                  )}
                </div>
              </div>
            )}
          </div>
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
        <div className="space-y-6">
          {/* Basic Information */}
          <div className="space-y-4">
            <div className="pb-2 border-b border-sre-border">
              <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">Basic Information</h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">
                  Datasource Name <span className="text-red-500">*</span> <HelpTooltip text="Enter a descriptive name for your datasource that clearly identifies its purpose and type." />
                </label>
                <Input
                  value={datasourceForm.name}
                  onChange={(e) => setDatasourceForm({ ...datasourceForm, name: e.target.value })}
                  placeholder={
                    datasourceForm.type === 'prometheus' ? 'My Mimir' :
                    datasourceForm.type === 'loki' ? 'My Loki' :
                    'My Tempo'
                  }
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">
                  Type <span className="text-red-500">*</span> <HelpTooltip text="Select the type of datasource. This determines how Grafana will query and display data." />
                </label>
                <Select
                  value={datasourceForm.type}
                  onChange={(e) => setDatasourceForm({ ...datasourceForm, type: e.target.value })}
                  disabled={!!editingDatasource}
                >
                  {DATASOURCE_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </Select>
                {editingDatasource && <p className="text-xs text-sre-text-muted mt-1">Type cannot be changed after creation</p>}
                {!editingDatasource && <p className="text-xs text-sre-text-muted mt-1">Select the datasource type</p>}
              </div>
            </div>
          </div>

          {/* Connection Settings */}
          <div className="space-y-4">
            <div className="pb-2 border-b border-sre-border">
              <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">Connection</h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-sre-text mb-2">
                  URL <span className="text-red-500">*</span> <HelpTooltip text="The endpoint URL where the datasource service is running and accessible." />
                </label>
                <Input
                  value={datasourceForm.url}
                  onChange={(e) => setDatasourceForm({ ...datasourceForm, url: e.target.value })}
                  placeholder={
                    datasourceForm.type === 'prometheus' ? MIMIR_PROMETHEUS_URL :
                    datasourceForm.type === 'loki' ? LOKI_BASE :
                    datasourceForm.type === 'tempo' ? TEMPO_URL :
                    'https://example.com'
                  }
                  required
                />
                <p className="text-xs text-sre-text-muted mt-1">The URL where the datasource is accessible</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">
                  Access Mode <HelpTooltip text="Server (Proxy): Grafana server makes requests. Browser (Direct): Browser makes direct requests to the datasource." />
                </label>
                <Select
                  value={datasourceForm.access}
                  onChange={(e) => setDatasourceForm({ ...datasourceForm, access: e.target.value })}
                >
                  <option value="proxy">Server (Proxy)</option>
                  <option value="direct">Browser (Direct)</option>
                </Select>
                <p className="text-xs text-sre-text-muted mt-1">Proxy: Access via Grafana server. Direct: Access from browser</p>
              </div>
            </div>
          </div>

          {/* Multi-tenant Configuration */}
          {!editingDatasource && ['prometheus', 'loki', 'tempo'].includes(datasourceForm.type) && (
            <div className="space-y-4">
              <div className="pb-2 border-b border-sre-border">
                <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">Multi-tenant Configuration</h3>
              </div>

              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">
                  API Key <span className="text-red-500">*</span> <HelpTooltip text="Select the API key for multi-tenant data isolation. This ensures the datasource only queries data for the selected product." />
                </label>
                <Select
                  value={datasourceForm.apiKeyId}
                  onChange={(e) => setDatasourceForm({ ...datasourceForm, apiKeyId: e.target.value })}
                  required
                >
                  {defaultKey && (
                    <option key={defaultKey.id} value={defaultKey.id}>
                      Default — {defaultKey.name}
                    </option>
                  )}
                  {(user?.api_keys || []).filter(k => !k.is_default).map((key) => (
                    <option key={key.id} value={key.id}>
                      {key.name}
                    </option>
                  ))}
                </Select>
                <p className="text-xs text-sre-text-muted mt-1">Select which API key to use for multi-tenant data isolation.</p>
                {(() => {
                  let datasourceName;
                  if (datasourceForm.type === 'prometheus') {
                    datasourceName = 'Mimir';
                  } else if (datasourceForm.type === 'loki') {
                    datasourceName = 'Loki';
                  } else {
                    datasourceName = 'Tempo';
                  }
                  return (
                    <div className="mt-2 text-xs text-sre-text-muted">
                      <span className="material-icons text-sm align-middle mr-1">info</span>
                      This datasource will only query data tagged with this API key in {datasourceName}.
                    </div>
                  );
                })()}
              </div>
            </div>
          )}

          {/* Settings */}
          <div className="space-y-4">
            <div className="pb-2 border-b border-sre-border">
              <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">Settings</h3>
            </div>

            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is-default"
                  checked={datasourceForm.isDefault}
                  onChange={(e) => setDatasourceForm({ ...datasourceForm, isDefault: e.target.checked })}
                  className="w-4 h-4"
                />
                <label htmlFor="is-default" className="text-sm text-sre-text">
                  Set as default datasource <HelpTooltip text="When checked, this datasource will be the default choice in new panels and dashboards." />
                </label>
              </div>

              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">
                  Visibility <HelpTooltip text="Control who can view and use this datasource. Private datasources are only accessible to you." />
                </label>
                <Select
                  value={datasourceForm.visibility}
                  onChange={(e) => {
                    setDatasourceForm({ ...datasourceForm, visibility: e.target.value, sharedGroupIds: [] })
                  }}
                >
                  {VISIBILITY_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
                <p className="text-xs text-sre-text-muted mt-1">Control who can access this datasource</p>
              </div>

              {datasourceForm.visibility === 'group' && (
                <div>
                  <label htmlFor="shared-groups" className="block text-sm font-medium text-sre-text mb-2">
                    Shared Groups <HelpTooltip text="Select which user groups can view and use this datasource." />
                  </label>
                <div id="shared-groups" className="space-y-2 max-h-40 overflow-y-auto border border-sre-border rounded p-3">
                  {groups.map(group => (
                    <Checkbox
                      key={group.id}
                      label={group.name}
                      checked={datasourceForm.sharedGroupIds.includes(group.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setDatasourceForm({
                            ...datasourceForm,
                            sharedGroupIds: [...datasourceForm.sharedGroupIds, group.id]
                          })
                        } else {
                          setDatasourceForm({
                            ...datasourceForm,
                            sharedGroupIds: datasourceForm.sharedGroupIds.filter(id => id !== group.id)
                          })
                        }
                      }}
                    />
                  ))}
                  {groups.length === 0 && (
                    <p className="text-sm text-sre-text-muted">No groups available</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
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
        <div>
          <label className="block text-sm font-medium text-sre-text mb-2">
            Folder Name <span className="text-red-500">*</span> <HelpTooltip text="Enter a descriptive name for your folder to organize related dashboards." />
          </label>
          <Input
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            placeholder="Production Dashboards"
            required
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter' && folderName.trim()) {
                handleCreateFolder()
              }
            }}
          />
          <p className="text-xs text-sre-text-muted mt-1">Choose a descriptive name for your folder</p>
        </div>
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
