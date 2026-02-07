import React, { useState, useEffect, useMemo } from 'react'
import PropTypes from 'prop-types'
import {
  getAlerts, getSilences, createSilence, deleteSilence,
  getAlertRules, createAlertRule, updateAlertRule, deleteAlertRule,
  getNotificationChannels, createNotificationChannel, updateNotificationChannel,
  deleteNotificationChannel, testNotificationChannel, testAlertRule
} from '../api'
import { Card, Button, Input, Select, Alert, Badge, Spinner, ConfirmDialog } from '../components/ui'

const RuleEditor = ({ rule, channels, onSave, onCancel }) => {
  const [formData, setFormData] = useState(rule || {
    name: '',
    expr: '',
    duration: '1m',
    severity: 'warning',
    labels: {},
    annotations: { summary: '', description: '' },
    enabled: true,
    group: 'default',
    notificationChannels: []
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Rule Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
          placeholder="e.g., HighCPUUsage"
        />
        <Select
          label="Severity"
          value={formData.severity}
          onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
        >
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="critical">Critical</option>
        </Select>
      </div>

      <Input
        label="PromQL Expression"
        value={formData.expr}
        onChange={(e) => setFormData({ ...formData, expr: e.target.value })}
        required
        placeholder="e.g., rate(requests_total[5m]) > 100"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Duration"
          value={formData.duration}
          onChange={(e) => setFormData({ ...formData, duration: e.target.value })}
          placeholder="e.g., 5m, 1h"
        />
        <Input
          label="Group"
          value={formData.group}
          onChange={(e) => setFormData({ ...formData, group: e.target.value })}
          placeholder="default"
        />
      </div>

      <Input
        label="Summary"
        value={formData.annotations.summary}
        onChange={(e) => setFormData({ ...formData, annotations: { ...formData.annotations, summary: e.target.value }})}
        placeholder="Brief alert summary"
      />

      <Input
        label="Description"
        value={formData.annotations.description}
        onChange={(e) => setFormData({ ...formData, annotations: { ...formData.annotations, description: e.target.value }})}
        placeholder="Detailed description"
      />

      <div>
        <label className="block text-sm font-medium text-sre-text mb-2">
          Notification Channels {formData.notificationChannels?.length > 0 ? `(${formData.notificationChannels.length} selected)` : '(All channels)'}
        </label>
        <div className="space-y-2 max-h-48 overflow-y-auto border border-sre-border rounded p-3 bg-sre-surface">
          {channels && channels.length > 0 ? (
            <>
              <div className="flex items-center gap-2 pb-2 border-b border-sre-border">
                <input
                  type="checkbox"
                  id="channel-all"
                  checked={!formData.notificationChannels || formData.notificationChannels.length === 0}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setFormData({ ...formData, notificationChannels: [] })
                    }
                  }}
                  className="w-4 h-4"
                />
                <label htmlFor="channel-all" className="text-sm text-sre-text font-medium">
                  All Channels (default)
                </label>
              </div>
              {channels.map((channel) => (
                <div key={channel.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id={`channel-${channel.id}`}
                    checked={formData.notificationChannels?.includes(channel.id)}
                    onChange={(e) => {
                      const currentChannels = formData.notificationChannels || []
                      if (e.target.checked) {
                        setFormData({ ...formData, notificationChannels: [...currentChannels, channel.id] })
                      } else {
                        setFormData({ ...formData, notificationChannels: currentChannels.filter(id => id !== channel.id) })
                      }
                    }}
                    className="w-4 h-4"
                  />
                  <label htmlFor={`channel-${channel.id}`} className="text-sm text-sre-text flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs ${channel.enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                      {channel.type}
                    </span>
                    {channel.name}
                    {!channel.enabled && <span className="text-xs text-gray-500">(disabled)</span>}
                  </label>
                </div>
              ))}
            </>
          ) : (
            <p className="text-sm text-gray-500">No channels configured. Create channels first to assign them to alerts.</p>
          )}
        </div>
        <p className="text-xs text-gray-500 mt-1">
          Select specific channels to notify, or leave empty to notify all channels
        </p>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="enabled"
          checked={formData.enabled}
          onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
          className="w-4 h-4"
        />
        <label htmlFor="enabled" className="text-sm text-sre-text">Enable this rule</label>
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit">
          <span className="material-icons text-sm mr-2">save</span>
          Save Rule
        </Button>
      </div>
    </form>
  )
}

RuleEditor.propTypes = {
  rule: PropTypes.object,
  channels: PropTypes.array,
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}

const ChannelEditor = ({ channel, onSave, onCancel }) => {
  const [formData, setFormData] = useState(channel || {
    name: '',
    type: 'webhook',
    enabled: true,
    config: {}
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(formData)
  }

  const renderConfigFields = () => {
    switch (formData.type) {
      case 'email':
        return (
          <>
            <Input
              label="SMTP Host"
              value={formData.config.smtp_host || ''}
              onChange={(e) => setFormData({ ...formData, config: { ...formData.config, smtp_host: e.target.value }})}
              placeholder="smtp.gmail.com"
            />
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="SMTP Port"
                type="number"
                value={formData.config.smtp_port || '587'}
                onChange={(e) => setFormData({ ...formData, config: { ...formData.config, smtp_port: e.target.value }})}
              />
              <Input
                label="From Email"
                value={formData.config.from || ''}
                onChange={(e) => setFormData({ ...formData, config: { ...formData.config, from: e.target.value }})}
                placeholder="alerts@example.com"
              />
            </div>
            <Input
              label="To Email"
              value={formData.config.to || ''}
              onChange={(e) => setFormData({ ...formData, config: { ...formData.config, to: e.target.value }})}
              placeholder="team@example.com"
              required
            />
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Username"
                value={formData.config.username || ''}
                onChange={(e) => setFormData({ ...formData, config: { ...formData.config, username: e.target.value }})}
              />
              <Input
                label="Password"
                type="password"
                value={formData.config.password || ''}
                onChange={(e) => setFormData({ ...formData, config: { ...formData.config, password: e.target.value }})}
              />
            </div>
          </>
        )
      case 'slack':
        return (
          <>
            <Input
              label="Webhook URL"
              value={formData.config.webhook_url || ''}
              onChange={(e) => setFormData({ ...formData, config: { ...formData.config, webhook_url: e.target.value }})}
              placeholder="https://hooks.slack.com/services/..."
              required
            />
            <Input
              label="Channel"
              value={formData.config.channel || ''}
              onChange={(e) => setFormData({ ...formData, config: { ...formData.config, channel: e.target.value }})}
              placeholder="#alerts"
            />
          </>
        )
      case 'teams':
        return (
          <Input
            label="Webhook URL"
            value={formData.config.webhook_url || ''}
            onChange={(e) => setFormData({ ...formData, config: { ...formData.config, webhook_url: e.target.value }})}
            placeholder="https://outlook.office.com/webhook/..."
            required
          />
        )
      case 'webhook':
        return (
          <Input
            label="Webhook URL"
            value={formData.config.url || ''}
            onChange={(e) => setFormData({ ...formData, config: { ...formData.config, url: e.target.value }})}
            placeholder="https://example.com/webhook"
            required
          />
        )
      case 'pagerduty':
        return (
          <Input
            label="Routing Key"
            value={formData.config.routing_key || ''}
            onChange={(e) => setFormData({ ...formData, config: { ...formData.config, routing_key: e.target.value }})}
            placeholder="Your PagerDuty routing key"
            required
          />
        )
      case 'opsgenie':
        return (
          <Input
            label="API Key"
            value={formData.config.api_key || ''}
            onChange={(e) => setFormData({ ...formData, config: { ...formData.config, api_key: e.target.value }})}
            placeholder="Your Opsgenie API key"
            required
          />
        )
      default:
        return null
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Channel Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
          placeholder="e.g., Team Slack Channel"
        />
        <Select
          label="Channel Type"
          value={formData.type}
          onChange={(e) => setFormData({ ...formData, type: e.target.value, config: {} })}
        >
          <option value="email">Email</option>
          <option value="slack">Slack</option>
          <option value="teams">Microsoft Teams</option>
          <option value="webhook">Webhook</option>
          <option value="pagerduty">PagerDuty</option>
          <option value="opsgenie">Opsgenie</option>
        </Select>
      </div>

      {renderConfigFields()}

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="channel-enabled"
          checked={formData.enabled}
          onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
          className="w-4 h-4"
        />
        <label htmlFor="channel-enabled" className="text-sm text-sre-text">Enable this channel</label>
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit">
          <span className="material-icons text-sm mr-2">save</span>
          Save Channel
        </Button>
      </div>
    </form>
  )
}

ChannelEditor.propTypes = {
  channel: PropTypes.object,
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}

const SilenceForm = ({ onSave, onCancel }) => {
  const [matchers, setMatchers] = useState([{ name: 'alertname', value: '', isRegex: false, isEqual: true }])
  const [duration, setDuration] = useState('1')
  const [comment, setComment] = useState('')

  const addMatcher = () => {
    setMatchers([...matchers, { name: '', value: '', isRegex: false, isEqual: true }])
  }

  const removeMatcher = (index) => {
    setMatchers(matchers.filter((_, i) => i !== index))
  }

  const updateMatcher = (index, field, value) => {
    const updated = [...matchers]
    updated[index] = { ...updated[index], [field]: value }
    setMatchers(updated)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const startsAt = new Date().toISOString()
    const endsAt = new Date(Date.now() + Number.parseInt(duration) * 60 * 60 * 1000).toISOString()
    
    onSave({
      matchers,
      startsAt,
      endsAt,
      createdBy: 'ui',
      comment
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <label className="text-sm font-semibold text-sre-text">Matchers</label>
        {matchers.map((matcher, index) => (
          <div key={index} className="flex gap-2 items-end">
            <Input
              label={index === 0 ? "Label" : ""}
              value={matcher.name}
              onChange={(e) => updateMatcher(index, 'name', e.target.value)}
              placeholder="label name"
              required
            />
            <Input
              label={index === 0 ? "Value" : ""}
              value={matcher.value}
              onChange={(e) => updateMatcher(index, 'value', e.target.value)}
              placeholder="label value"
              required
            />
            {matchers.length > 1 && (
              <Button type="button" variant="ghost" onClick={() => removeMatcher(index)}>
                <span className="material-icons text-sm">delete</span>
              </Button>
            )}
          </div>
        ))}
        <Button type="button" variant="ghost" onClick={addMatcher}>
          <span className="material-icons text-sm mr-2">add</span>
          Add Matcher
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Duration (hours)"
          type="number"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
          min="1"
          required
        />
        <Input
          label="Comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Reason for silence"
          required
        />
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit">
          <span className="material-icons text-sm mr-2">volume_off</span>
          Create Silence
        </Button>
      </div>
    </form>
  )
}

SilenceForm.propTypes = {
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}

export default function AlertManagerPage() {
  const [activeTab, setActiveTab] = useState('alerts')
  const [alerts, setAlerts] = useState([])
  const [silences, setSilences] = useState([])
  const [rules, setRules] = useState([])
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showRuleEditor, setShowRuleEditor] = useState(false)
  const [showChannelEditor, setShowChannelEditor] = useState(false)
  const [showSilenceForm, setShowSilenceForm] = useState(false)
  const [editingRule, setEditingRule] = useState(null)
  const [editingChannel, setEditingChannel] = useState(null)
  const [filterSeverity, setFilterSeverity] = useState('all')
  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: null,
    confirmText: 'Delete',
    variant: 'danger'
  })

  const [testDialog, setTestDialog] = useState({ isOpen: false, title: '', message: '' })

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [alertsData, silencesData, rulesData, channelsData] = await Promise.all([
        getAlerts().catch(() => []),
        getSilences().catch(() => []),
        getAlertRules().catch(() => []),
        getNotificationChannels().catch(() => [])
      ])
      setAlerts(alertsData)
      setSilences(silencesData)
      setRules(rulesData)
      setChannels(channelsData)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSaveRule(ruleData) {
    try {
      if (editingRule) {
        await updateAlertRule(editingRule.id, ruleData)
      } else {
        await createAlertRule(ruleData)
      }
      await loadData()
      setShowRuleEditor(false)
      setEditingRule(null)
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleDeleteRule(ruleId) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Alert Rule',
      message: 'Are you sure you want to delete this rule? This action cannot be undone.',
      confirmText: 'Delete',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteAlertRule(ruleId)
          await loadData()
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        } catch (e) {
          setError(e.message)
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        }
      }
    })
  }

  async function handleSaveChannel(channelData) {
    try {
      if (editingChannel) {
        await updateNotificationChannel(editingChannel.id, channelData)
      } else {
        await createNotificationChannel(channelData)
      }
      await loadData()
      setShowChannelEditor(false)
      setEditingChannel(null)
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleDeleteChannel(channelId) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Notification Channel',
      message: 'Are you sure you want to delete this channel? This action cannot be undone.',
      confirmText: 'Delete',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteNotificationChannel(channelId)
          await loadData()
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        } catch (e) {
          setError(e.message)
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        }
      }
    })
  }

  async function handleTestChannel(channelId) {
    try {
      const result = await testNotificationChannel(channelId)
      setTestDialog({ isOpen: true, title: 'Test Notification', message: result.message || 'Test notification sent' })
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleTestRule(ruleId) {
    try {
      const result = await testAlertRule(ruleId)
      setTestDialog({ isOpen: true, title: 'Success', message: result.message || 'We have invoked a test alert, please check your alerting system.' })
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleCreateSilence(silenceData) {
    try {
      await createSilence(silenceData)
      await loadData()
      setShowSilenceForm(false)
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleDeleteSilence(silenceId) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Silence',
      message: 'Are you sure you want to delete this silence?',
      confirmText: 'Delete',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteSilence(silenceId)
          await loadData()
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        } catch (e) {
          setError(e.message)
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        }
      }
    })
  }

  const filteredAlerts = useMemo(() => {
    if (filterSeverity === 'all') return alerts
    return alerts.filter(a => a.labels?.severity === filterSeverity)
  }, [alerts, filterSeverity])

  const stats = useMemo(() => ({
    totalAlerts: alerts.length,
    critical: alerts.filter(a => a.labels?.severity === 'critical').length,
    warning: alerts.filter(a => a.labels?.severity === 'warning').length,
    activeSilences: silences.length,
    enabledRules: rules.filter(r => r.enabled).length,
    totalRules: rules.length,
    enabledChannels: channels.filter(c => c.enabled).length,
    totalChannels: channels.length
  }), [alerts, silences, rules, channels])

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-sre-text mb-2 flex items-center gap-2">
          <span className="material-icons text-3xl text-sre-primary">notifications_active</span>
          AlertManager
        </h1>
        <p className="text-sre-text-muted">Comprehensive alerting system with rules, channels, and silences</p>
      </div>

      {error && (
        <Alert variant="error" className="mb-6" onClose={() => setError(null)}>
          <strong>Error:</strong> {error}
        </Alert>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card className="p-4">
          <div className="text-sre-text-muted text-xs mb-1">Active Alerts</div>
          <div className="text-2xl font-bold text-sre-text">{stats.totalAlerts}</div>
          <div className="text-xs text-sre-text-muted mt-1">
            <span className="text-red-500">{stats.critical} critical</span> · <span className="text-yellow-500">{stats.warning} warning</span>
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-sre-text-muted text-xs mb-1">Alert Rules</div>
          <div className="text-2xl font-bold text-sre-text">{stats.enabledRules}/{stats.totalRules}</div>
          <div className="text-xs text-sre-text-muted mt-1">enabled</div>
        </Card>
        <Card className="p-4">
          <div className="text-sre-text-muted text-xs mb-1">Notification Channels</div>
          <div className="text-2xl font-bold text-sre-text">{stats.enabledChannels}/{stats.totalChannels}</div>
          <div className="text-xs text-sre-text-muted mt-1">active</div>
        </Card>
        <Card className="p-4">
          <div className="text-sre-text-muted text-xs mb-1">Active Silences</div>
          <div className="text-2xl font-bold text-sre-text">{stats.activeSilences}</div>
          <div className="text-xs text-sre-text-muted mt-1">muting alerts</div>
        </Card>
      </div>

      <div className="mb-6 flex gap-2 border-b border-sre-border">
        {[
          { key: 'alerts', label: 'Alerts', icon: 'notification_important' },
          { key: 'rules', label: 'Rules', icon: 'rule' },
          { key: 'channels', label: 'Channels', icon: 'send' },
          { key: 'silences', label: 'Silences', icon: 'volume_off' }
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 flex items-center gap-2 border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-sre-primary text-sre-primary'
                : 'border-transparent text-sre-text-muted hover:text-sre-text'
            }`}
          >
            <span className="material-icons text-sm">{tab.icon}</span>
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
          {activeTab === 'alerts' && (
            <Card 
              title="Active Alerts" 
              subtitle={`${filteredAlerts.length} alert${filteredAlerts.length !== 1 ? 's' : ''}`}
              action={
                <Select value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
                  <option value="all">All Severities</option>
                  <option value="critical">Critical</option>
                  <option value="warning">Warning</option>
                  <option value="info">Info</option>
                </Select>
              }
            >
              {filteredAlerts.length ? (
                <div className="space-y-3">
                  {filteredAlerts.map((a) => (
                    <div
                      key={a.fingerprint || Math.random()}
                      className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <span className="material-icons text-sre-error">
                            {a.labels?.severity === 'critical' ? 'error' : 'warning'}
                          </span>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-sm font-semibold text-sre-text">
                                {a.labels?.alertname || 'Unknown'}
                              </span>
                              <Badge variant={a.labels?.severity === 'critical' ? 'error' : 'warning'}>
                                {a.labels?.severity || 'unknown'}
                              </Badge>
                              <Badge variant="default">{a.status?.state || 'active'}</Badge>
                            </div>
                            {a.annotations?.summary && (
                              <p className="text-sm text-sre-text-muted">{a.annotations.summary}</p>
                            )}
                          </div>
                        </div>
                        <span className="text-xs text-sre-text-muted">
                          {new Date(a.starts_at || a.startsAt).toLocaleString()}
                        </span>
                      </div>
                      {a.labels && Object.keys(a.labels).length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1">
                          {Object.entries(a.labels)
                            .filter(([key]) => !['alertname', 'severity'].includes(key))
                            .map(([key, value]) => (
                              <span
                                key={key}
                                className="text-xs px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-sre-text-muted"
                              >
                                {key}={value}
                              </span>
                            ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <span className="material-icons text-6xl text-sre-text-subtle mb-4">check_circle</span>
                  <p className="text-sre-text-muted">No active alerts</p>
                </div>
              )}
            </Card>
          )}

          {activeTab === 'rules' && (
            <>
              {showRuleEditor ? (
                <Card title={editingRule ? "Edit Alert Rule" : "Create Alert Rule"}>
                  <RuleEditor
                    rule={editingRule}
                    channels={channels}
                    onSave={handleSaveRule}
                    onCancel={() => {
                      setShowRuleEditor(false)
                      setEditingRule(null)
                    }}
                  />
                </Card>
              ) : (
                <Card
                  title="Alert Rules"
                  subtitle={`${rules.length} rule${rules.length !== 1 ? 's' : ''} configured`}
                  action={
                    <Button onClick={() => setShowRuleEditor(true)}>
                      <span className="material-icons text-sm mr-2">add</span>
                      Create Rule
                    </Button>
                  }
                >
                  {rules.length ? (
                    <div className="space-y-3">
                      {rules.map((rule) => (
                        <div
                          key={rule.id}
                          className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="font-semibold text-sre-text">{rule.name}</span>
                                <Badge variant={rule.severity === 'critical' ? 'error' : rule.severity === 'warning' ? 'warning' : 'info'}>
                                  {rule.severity}
                                </Badge>
                                {rule.enabled ? (
                                  <Badge variant="success">Enabled</Badge>
                                ) : (
                                  <Badge variant="default">Disabled</Badge>
                                )}
                                <Badge variant="default">{rule.group}</Badge>
                              </div>
                              <p className="text-sm font-mono text-sre-text-muted mb-2">{rule.expr}</p>
                              <p className="text-xs text-sre-text-muted">
                                Duration: {rule.duration} · {rule.annotations?.summary || 'No summary'}
                              </p>
                            </div>
                            <div className="flex gap-2">
                              <Button variant="ghost" onClick={() => handleTestRule(rule.id)}>
                                <span className="material-icons text-sm">science</span>
                              </Button>
                              <Button
                                variant="ghost"
                                onClick={() => {
                                  setEditingRule(rule)
                                  setShowRuleEditor(true)
                                }}
                              >
                                <span className="material-icons text-sm">edit</span>
                              </Button>
                              <Button variant="ghost" onClick={() => handleDeleteRule(rule.id)}>
                                <span className="material-icons text-sm">delete</span>
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-12">
                      <span className="material-icons text-6xl text-sre-text-subtle mb-4">rule</span>
                      <p className="text-sre-text-muted mb-4">No alert rules configured</p>
                      <Button onClick={() => setShowRuleEditor(true)}>
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Your First Rule
                      </Button>
                    </div>
                  )}
                </Card>
              )}
            </>
          )}

          {activeTab === 'channels' && (
            <>
              {showChannelEditor ? (
                <Card title={editingChannel ? "Edit Notification Channel" : "Create Notification Channel"}>
                  <ChannelEditor
                    channel={editingChannel}
                    onSave={handleSaveChannel}
                    onCancel={() => {
                      setShowChannelEditor(false)
                      setEditingChannel(null)
                    }}
                  />
                </Card>
              ) : (
                <Card
                  title="Notification Channels"
                  subtitle={`${channels.length} channel${channels.length !== 1 ? 's' : ''} configured`}
                  action={
                    <Button onClick={() => setShowChannelEditor(true)}>
                      <span className="material-icons text-sm mr-2">add</span>
                      Create Channel
                    </Button>
                  }
                >
                  {channels.length ? (
                    <div className="space-y-3">
                      {channels.map((channel) => (
                        <div
                          key={channel.id}
                          className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="material-icons text-sre-primary">
                                  {channel.type === 'email' ? 'email' : channel.type === 'slack' ? 'chat' : channel.type === 'teams' ? 'groups' : 'webhook'}
                                </span>
                                <span className="font-semibold text-sre-text">{channel.name}</span>
                                <Badge variant="info">{channel.type}</Badge>
                                {channel.enabled ? (
                                  <Badge variant="success">Enabled</Badge>
                                ) : (
                                  <Badge variant="default">Disabled</Badge>
                                )}
                              </div>
                              <p className="text-xs text-sre-text-muted">
                                {channel.type === 'email' && `To: ${channel.config.to}`}
                                {channel.type === 'slack' && `Channel: ${channel.config.channel || 'default'}`}
                                {channel.type === 'webhook' && `URL: ${channel.config.url}`}
                              </p>
                            </div>
                            <div className="flex gap-2">
                              <Button variant="ghost" onClick={() => handleTestChannel(channel.id)}>
                                <span className="material-icons text-sm">send</span>
                              </Button>
                              <Button
                                variant="ghost"
                                onClick={() => {
                                  setEditingChannel(channel)
                                  setShowChannelEditor(true)
                                }}
                              >
                                <span className="material-icons text-sm">edit</span>
                              </Button>
                              <Button variant="ghost" onClick={() => handleDeleteChannel(channel.id)}>
                                <span className="material-icons text-sm">delete</span>
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-12">
                      <span className="material-icons text-6xl text-sre-text-subtle mb-4">send</span>
                      <p className="text-sre-text-muted mb-4">No notification channels configured</p>
                      <Button onClick={() => setShowChannelEditor(true)}>
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Your First Channel
                      </Button>
                    </div>
                  )}
                </Card>
              )}
            </>
          )}

          {activeTab === 'silences' && (
            <>
              {showSilenceForm ? (
                <Card title="Create Silence">
                  <SilenceForm
                    onSave={handleCreateSilence}
                    onCancel={() => setShowSilenceForm(false)}
                  />
                </Card>
              ) : (
                <Card
                  title="Active Silences"
                  subtitle={`${silences.length} silence${silences.length !== 1 ? 's' : ''} active`}
                  action={
                    <Button onClick={() => setShowSilenceForm(true)}>
                      <span className="material-icons text-sm mr-2">add</span>
                      Create Silence
                    </Button>
                  }
                >
                  {silences.length ? (
                    <div className="space-y-3">
                      {silences.map((s) => (
                        <div
                          key={s.id}
                          className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="material-icons text-sre-warning">volume_off</span>
                                <Badge variant="warning">Silenced</Badge>
                                <span className="text-sm text-sre-text-muted">{s.comment}</span>
                              </div>
                              <div className="text-xs text-sre-text-muted mb-2">
                                <span className="font-mono">ID: {s.id}</span>
                              </div>
                              {s.matchers && s.matchers.length > 0 && (
                                <div className="flex flex-wrap gap-1">
                                  {s.matchers.map((m, idx) => (
                                    <span
                                      key={idx}
                                      className="text-xs px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-sre-text"
                                    >
                                      {m.name}{m.isEqual ? '=' : '!='}{m.value}
                                    </span>
                                  ))}
                                </div>
                              )}
                              <div className="text-xs text-sre-text-muted mt-2">
                                {new Date(s.starts_at || s.startsAt).toLocaleString()} → {new Date(s.ends_at || s.endsAt).toLocaleString()}
                              </div>
                            </div>
                            <Button variant="ghost" onClick={() => handleDeleteSilence(s.id)}>
                              <span className="material-icons text-sm">delete</span>
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-12">
                      <span className="material-icons text-6xl text-sre-text-subtle mb-4">volume_up</span>
                      <p className="text-sre-text-muted mb-4">No active silences</p>
                      <Button onClick={() => setShowSilenceForm(true)}>
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Silence
                      </Button>
                    </div>
                  )}
                </Card>
              )}
            </>
          )}
        </>
      )}

      <ConfirmDialog
        isOpen={testDialog.isOpen}
        title={testDialog.title}
        message={testDialog.message}
        onConfirm={() => setTestDialog({ isOpen: false, title: '', message: '' })}
        confirmText="OK"
        variant="success"
        onClose={() => setTestDialog({ isOpen: false, title: '', message: '' })}
      />

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        onConfirm={confirmDialog.onConfirm}
        confirmText={confirmDialog.confirmText}
        variant={confirmDialog.variant}
        onClose={() => setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })}
      />
    </div>
  )
}
