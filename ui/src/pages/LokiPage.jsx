import { useState, useEffect, useRef } from 'react'
import { queryLogs, getLabels, getLabelValues, getLogVolume } from '../api'
import { Card, Button, Alert } from '../components/ui'
import LogQueryForm from '../components/loki/LogQueryForm'
import LogResults from '../components/loki/LogResults'
import LogVolume from '../components/loki/LogVolume'
import LogQuickFilters from '../components/loki/LogQuickFilters'
import LogLabels from '../components/loki/LogLabels'

function copyToClipboard(text){
  navigator.clipboard.writeText(text).then(() => {
    alert('Copied to clipboard!')
  }).catch(error_ => {
    console.error('Failed to copy:', error_)
  })
}

function getLogText(raw){
  try {
    const parsed = JSON.parse(raw)
    return Object.values(parsed).join(' ')
  } catch {
    return String(raw)
  }
}

function normalizeToken(tok){
  return tok.replaceAll(/(?:^\W+|\W+$)/g, '')
}

function isTokenValid(tok, stopwords){
  if(tok.length < 3) return false
  if(/^\d+$/.test(tok)) return false
  if(stopwords.has(tok)) return false
  return true
}

function collectTokensFromValues(values, stopwords, maxSamples, state, tokens){
  for(const v of values){
    if(state.seen++ > maxSamples){
      state.done = true
      return
    }
    const parts = getLogText(v[1]).toLowerCase().split(/[^a-z0-9_+-]+/).filter(Boolean)
    const cleaned = parts
      .filter(tok => isTokenValid(tok, stopwords))
      .map(normalizeToken)
      .filter(Boolean)
    tokens.push(...cleaned)
  }
}

function collectTokensFromResults(result, maxSamples, stopwords){
  if(!result) return []
  const tokens = []
  const state = { seen: 0, done: false }
  for(const stream of result){
    collectTokensFromValues(stream.values || [], stopwords, maxSamples, state, tokens)
    if(state.done) break
  }
  return tokens
}

function countTokens(tokens){
  return tokens.reduce((acc, t) => {
    acc[t] = (acc[t] || 0) + 1
    return acc
  }, {})
}

function mapTopTerms(freq, maxTerms){
  const arr = Object.entries(freq).map(([term,count]) => ({term, count})).sort((a,b)=>b.count - a.count)
  return arr.slice(0, maxTerms).map(item => {
    let icon = 'search'
    let iconClass = ''
    if(item.term.includes('error')){ icon='error'; iconClass='text-red-500' }
    else if(item.term.includes('warn')){ icon='warning'; iconClass='text-yellow-500' }
    else if(item.term.includes('timeout') || item.term.includes('timedout')){ icon='schedule'; iconClass='text-orange-500' }
    else if(item.term.includes('exception')){ icon='error_outline'; iconClass='text-red-400' }
    return {...item, icon, iconClass}
  })
}

function computeTopTermsFromResult(res, maxTerms = 8){
  if(!res?.data?.result) return []

  const stopwords = new Set(['the','and','for','with','that','this','from','are','was','but','not','you','your','have','has','will','can','http','https','info','message'])
  const tokens = collectTokensFromResults(res.data.result, 2000, stopwords)
  if(tokens.length === 0) return []
  const freq = countTokens(tokens)
  return mapTopTerms(freq, maxTerms)
}

function getVolumeValues(volRes){
  return (volRes?.data?.result?.[0]?.values || []).map(v => Number(v[1]))
}

function buildFallbackVolume(res, totalLogs){
  const buckets = {}
  if(res?.data?.result){
    for(const stream of res.data.result){
      for(const [ts] of (stream.values || [])){
        const bucket = Math.floor(Number.parseInt(ts, 10) / 1e9 / 60)
        buckets[bucket] = (buckets[bucket] || 0) + 1
      }
    }
  }
  const volumeData = Object.values(buckets).slice(-60)
  if(volumeData.length > 0) return volumeData
  if(totalLogs > 0) return new Array(10).fill(Math.ceil(totalLogs / 10))
  return [0]
}

export default function LokiPage() {
  const [labels, setLabels] = useState([])
  const [labelValuesCache, setLabelValuesCache] = useState({})
  const [loadingValues, setLoadingValues] = useState({})
  const [selectedFilters, setSelectedFilters] = useState([])
  const [selectedLabel, setSelectedLabel] = useState('')
  const [selectedValue, setSelectedValue] = useState('')
  const [pattern, setPattern] = useState('')
  const [rangeMinutes, setRangeMinutes] = useState(60)
  const [maxLogs, setMaxLogs] = useState(100)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(30)
  const [viewMode, setViewMode] = useState('table') 
  const [expandedLogs, setExpandedLogs] = useState({})
  const [searchText, setSearchText] = useState('')
  const [queryMode, setQueryMode] = useState('builder')
  const [customLogQL, setCustomLogQL] = useState('')
  
  const [queryResult, setQueryResult] = useState(null)
  const [volume, setVolume] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [topTerms, setTopTerms] = useState([])
  
  
  const autoRefreshRef = useRef(null)

  useEffect(()=>{
    loadInitialData()
  },[])
  
  useEffect(()=>{
    if(autoRefresh){
      autoRefreshRef.current = setInterval(()=>{
        runQuery()
      }, refreshInterval * 1000)
    } else if(autoRefreshRef.current){
      clearInterval(autoRefreshRef.current)
      autoRefreshRef.current = null
    }
    return () => {
      if(autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    }
  }, [autoRefresh, refreshInterval, selectedFilters, pattern, rangeMinutes])
  
  async function loadInitialData(){
    try {
      const lbls = await getLabels()
      console.log('[LokiPage] getLabels response:', lbls)
      const labelsArray = lbls?.data || []
      console.log('[LokiPage] Setting labels:', labelsArray)
      setLabels(labelsArray)
      
      if(labelsArray.length > 0){
        for(const label of labelsArray){
          try {
            const vals = await getLabelValues(label)
            console.log(`[LokiPage] getLabelValues(${label}):`, vals)
            setLabelValuesCache(prev => ({...prev, [label]: vals?.data || []}))
          } catch(e) {
            console.warn(`Failed to load values for ${label}:`, e)
          }
        }
      }
    } catch(e) {
      console.error('[LokiPage] Failed to load labels:', e)
      setLabels([])
    }
  }

  async function loadLabelValues(label){
    if(!label) return
    if(labelValuesCache[label]) return
    
    setLoadingValues(prev => ({...prev, [label]: true}))
    try{
      const vals = await getLabelValues(label)
      setLabelValuesCache(prev => ({...prev, [label]: vals.data || []}))
    }catch(e){
      console.warn('Failed to load label values for', label, e)
    }finally{
      setLoadingValues(prev => ({...prev, [label]: false}))
    }
  }

  function addFilter(){
    if(!selectedLabel || !selectedValue) return
    setSelectedFilters(prev => {
      const exists = prev.find(p=>p.label===selectedLabel && p.value===selectedValue)
      if(exists) return prev
      return [...prev, {label:selectedLabel, value:selectedValue}]
    })
    setSelectedLabel('')
    setSelectedValue('')
  }

  function removeFilter(i){
    setSelectedFilters(prev => prev.filter((_,idx)=>idx!==i))
  }
  
  function clearAllFilters(){
    setSelectedFilters([])
    setPattern('')
  }

  function buildSelector(){
    if(!selectedFilters.length) {
      // Return a selector that matches all logs using the first available label
      const firstLabel = labels[0] || 'service_name'
      return `{${firstLabel}=~".+"}`
    }
    const parts = selectedFilters.map(f => (
      f.value === '__any__' ? `${f.label}=~".+"` : `${f.label}="${f.value}"`
    ))
    return `{${parts.join(',')}}`
  }
  
  function toggleLogExpand(logKey){
    setExpandedLogs(prev => ({...prev, [logKey]: !prev[logKey]}))
  }
  
  function downloadLogs(){
    if(!queryResult?.data?.result) return
    
    const logs = []
    queryResult.data.result.forEach(stream => {
      stream.values.forEach(v => {
        logs.push({
          timestamp: formatNsToIso(v[0]),
          stream: stream.stream,
          log: v[1]
        })
      })
    })
    
    const blob = new Blob([JSON.stringify(logs, null, 2)], {type: 'application/json'})
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `loki-logs-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }
  
  function filterDisplayedLogs(logs){
    if(!searchText) return logs
    const search = searchText.toLowerCase()
    return logs.filter(v => {
      const logText = typeof v[1] === 'string' ? v[1] : JSON.stringify(v[1])
      return logText.toLowerCase().includes(search)
    })
  }

  async function fetchAndSetVolume(selectorForVolume, startNs, endNs, totalLogs, res){
    try {
      const volRes = await getLogVolume(selectorForVolume, {start: Math.round(startNs), end: Math.round(endNs), step: Math.max(60, Math.floor(rangeMinutes*60 / 60))})
      const vals = getVolumeValues(volRes)
      if(vals.some(v => v > 0)) {
        setVolume(vals)
        return
      }
    } catch (error_) {
      console.warn('Failed to fetch log volume:', error_)
    }
    setVolume(buildFallbackVolume(res, totalLogs))
  }

  async function runQuery(e){
    e?.preventDefault?.()
    setError(null)
    setLoading(true)
    const queryStartTime = Date.now()
    
    try{
      let q
      let selectorForVolume
      if(queryMode === 'custom') {
        q = customLogQL.trim()
        if(!q) {
          setError('Please enter a LogQL query')
          setLoading(false)
          return
        }
        selectorForVolume = buildSelector()
      } else {
        const selector = buildSelector()
        selectorForVolume = selector
        q = selector
        if(pattern) q += ` |= "${pattern}"`
      }
      
      const start = Date.now() - rangeMinutes*60*1000
      const startNs = start * 1e6
      const endNs = Date.now() * 1e6
      
      console.log('[LokiPage] runQuery:', {query: q, start: Math.round(startNs), end: Math.round(endNs), limit: maxLogs})

      const res = await queryLogs({query: q, start: Math.round(startNs), end: Math.round(endNs), limit: maxLogs})
      console.log('[LokiPage] queryLogs response:', res)
      setQueryResult(res)
      // update dynamic quick-search terms based on recent results
      try {
        const terms = computeTopTermsFromResult(res, 12)
        setTopTerms(terms)
      } catch (err) {
        console.warn('Failed to compute top terms:', err)
        setTopTerms([])
      }
      
      const totalLogs = res.data?.result?.reduce((acc, stream) => acc + (stream.values?.length || 0), 0) || 0
      const streams = res.data?.result?.length || 0
      const queryTime = Date.now() - queryStartTime
      console.log('[LokiPage] Query summary:', {totalLogs, streams, queryTime})

      await fetchAndSetVolume(selectorForVolume, startNs, endNs, totalLogs, res)
    }catch(e){
      setError(e.message)
    }finally{
      setLoading(false)
    }
  }
  
  function handleSelectLabelValue(label, value){
    const filters = [{ label, value }]
    setSelectedFilters(filters)
    setPattern('')
    runQueryWithFilters(filters, '')
  }

  function handleSelectPattern(term){
    setSelectedFilters([])
    setPattern(term)
    runQueryWithFilters([], term)
  }
  
  async function runQueryWithFilters(filters, textPattern){
    setError(null)
    setLoading(true)
    const queryStartTime = Date.now()
    
    try{
      let q
      let selectorForVolume
      if(queryMode === 'custom') {
        q = customLogQL.trim()
        if(!q) {
          setError('Please enter a LogQL query')
          setLoading(false)
          return
        }
        selectorForVolume = buildSelectorFromFilters(filters)
      } else {
        const selector = buildSelectorFromFilters(filters)
        selectorForVolume = selector
        q = selector
        if(textPattern) q += ` |= "${textPattern}"`
      }
      
      const start = Date.now() - rangeMinutes*60*1000
      const startNs = start * 1e6
      const endNs = Date.now() * 1e6
      

      const res = await queryLogs({query: q, start: Math.round(startNs), end: Math.round(endNs), limit: maxLogs})
      setQueryResult(res)
      // update quick-search suggestions
      try {
        const terms = computeTopTermsFromResult(res, 12)
        setTopTerms(terms)
      } catch (err) {
        console.warn('Failed to compute top terms:', err)
        setTopTerms([])
      }
      
      const totalLogs = res.data?.result?.reduce((acc, stream) => acc + (stream.values?.length || 0), 0) || 0
      const streams = res.data?.result?.length || 0
      const queryTime = Date.now() - queryStartTime
      console.log('[LokiPage] Query summary:', {totalLogs, streams, queryTime})

      await fetchAndSetVolume(selectorForVolume, startNs, endNs, totalLogs, res)
    }catch(err){
      console.error('Query error:', err)
      setError(err.message || 'Failed to query logs')
    }finally{
      setLoading(false)
    }
  }
  
  function buildSelectorFromFilters(filters){
    if(!filters?.length) {
      // Use first available label or fallback to common label
      const firstLabel = labels[0] || 'service_name'
      return `{${firstLabel}=~".+"}`  
    }
    const parts = filters.map(f=>`${f.label}="${f.value}"`)
    return `{${parts.join(',')}}`
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-sre-text mb-2">Loki — Log Aggregation</h1>
          <p className="text-sre-text-muted">Query and analyze logs using LogQL</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-sre-text">
            <input 
              type="checkbox" 
              checked={autoRefresh} 
              onChange={(e)=>setAutoRefresh(e.target.checked)}
              className="rounded border-sre-border bg-sre-surface"
            />
            <span>Auto-refresh</span>
          </label>
          {autoRefresh && (
            <select value={refreshInterval} onChange={(e)=>setRefreshInterval(Number(e.target.value))} className="px-2 py-1 bg-sre-surface border border-sre-border rounded text-sm text-sre-text">
              <option value={10}>10s</option>
              <option value={30}>30s</option>
              <option value={60}>60s</option>
              <option value={300}>5m</option>
            </select>
          )}
        </div>
      </div>

      {error && (
        <Alert variant="error" className="mb-6">
          <strong>Error:</strong> {error}
        </Alert>
      )}

      <Card title="Search & Filter" subtitle="Build LogQL queries using labels and patterns" className="mb-6">
        <LogQueryForm
          queryMode={queryMode}
          customLogQL={customLogQL}
          setCustomLogQL={setCustomLogQL}
          labels={labels}
          selectedLabel={selectedLabel}
          setSelectedLabel={setSelectedLabel}
          labelValuesCache={labelValuesCache}
          loadingValues={loadingValues}
          selectedValue={selectedValue}
          setSelectedValue={setSelectedValue}
          pattern={pattern}
          setPattern={setPattern}
          rangeMinutes={rangeMinutes}
          setRangeMinutes={setRangeMinutes}
          maxLogs={maxLogs}
          setMaxLogs={setMaxLogs}
          addFilter={addFilter}
          selectedFilters={selectedFilters}
          clearAllFilters={clearAllFilters}
          runQuery={runQuery}
          onQueryModeChange={(e) => setQueryMode(e.target.value)}
          onLabelChange={loadLabelValues}
          loading={loading}
          onRemoveFilter={removeFilter}
        />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3">
          <Card title="Log Results" subtitle={queryResult?.data?.result?.length ? `Showing results` : 'Run a query'}>
            <div className="mb-4 flex items-center justify-between pb-4 border-b border-sre-border">
              <div className="flex items-center gap-4">
                <div className="flex gap-1 bg-sre-bg-alt rounded-lg p-1">
                  {['table', 'compact', 'raw'].map(mode => (
                    <button key={mode} onClick={() => setViewMode(mode)} className={`px-3 py-1 rounded text-xs font-medium transition-colors ${viewMode === mode ? 'bg-sre-primary text-white' : 'text-sre-text-muted hover:text-sre-text'}`}>
                      {mode.charAt(0).toUpperCase() + mode.slice(1)}
                    </button>
                  ))}
                </div>

                <input type="text" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Filter displayed logs..." className="px-3 py-1 bg-sre-surface border border-sre-border rounded text-sm text-sre-text w-64" />
              </div>

              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={downloadLogs}>Export</Button>
              </div>
            </div>

            <LogResults
              queryResult={queryResult}
              loading={loading}
              filterDisplayedLogs={filterDisplayedLogs}
              viewMode={viewMode}
              expandedLogs={expandedLogs}
              toggleLogExpand={toggleLogExpand}
              copyToClipboard={copyToClipboard}
            />
          </Card>
        </div>

        <div className="space-y-6">
          {volume.length > 0 && <LogVolume volume={volume} />}
          <LogQuickFilters
            labelValuesCache={labelValuesCache}
            topTerms={topTerms}
            onSelectLabelValue={handleSelectLabelValue}
            onSelectPattern={handleSelectPattern}
          />
          <LogLabels labels={labels} labelValuesCache={labelValuesCache} />
        </div>
      </div>
    </div>
  )
}
