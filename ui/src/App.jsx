import React, { useEffect, useState } from 'react'
import { HashRouter as Router, Routes, Route } from 'react-router-dom'
import { ThemeProvider } from './contexts/ThemeContext'
import Header from './components/Header'
import Dashboard from './components/Dashboard'
import TempoPage from './pages/TempoPage'
import LokiPage from './pages/LokiPage'
import AlertManagerPage from './pages/AlertManagerPage'
import GrafanaPage from './pages/GrafanaPage'
import { fetchInfo } from './api'

export default function App() {
  const [info, setInfo] = useState(null)
  
  useEffect(() => {
    fetchInfo()
      .then(setInfo)
      .catch(() => setInfo(null))
  }, [])

  return (
    <ThemeProvider>
      <Router>
        <div className="min-h-screen bg-gradient-to-b from-sre-bg via-sre-bg-alt to-sre-bg">
          <Header />
          <main className="container">
            <Routes>
              <Route path="/" element={<Dashboard info={info} />} />
              <Route path="/tempo" element={<TempoPage />} />
              <Route path="/loki" element={<LokiPage />} />
              <Route path="/alertmanager" element={<AlertManagerPage />} />
              <Route path="/grafana" element={<GrafanaPage />} />
            </Routes>
          </main>
        </div>
      </Router>
    </ThemeProvider>
  )
}
