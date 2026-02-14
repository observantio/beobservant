import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { Card, Spinner } from '../components/ui'
import PasswordLoginForm from '../components/auth/PasswordLoginForm'
import OIDCLoginButton from '../components/auth/OIDCLoginButton'
import { OIDC_PROVIDER_LABEL } from '../utils/constants'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [oidcLoading, setOidcLoading] = useState(false)
  const { login, startOIDCLogin, authMode, authModeLoading } = useAuth()
  const navigate = useNavigate()

  const hasOIDC = Boolean(authMode?.oidc_enabled)
  const hasPassword = Boolean(authMode?.password_enabled)
  const showDivider = hasOIDC && hasPassword

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (!hasPassword) {
      setError('Password login is disabled. Use Single Sign-On.')
      return
    }

    if (!username.trim()) {
      setError('Username is required')
      return
    }
    if (!password) {
      setError('Password is required')
      return
    }

    setLoading(true)
    try {
      await login(username.trim(), password)
      navigate('/')
    } catch {
      setError('Invalid username or password. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleOIDCLogin = async () => {
    setError('')
    setOidcLoading(true)
    try {
      await startOIDCLogin()
    } catch (err) {
      setError(err?.message || 'Unable to start Single Sign-On')
      setOidcLoading(false)
    }
  }

  const providerLabel = hasOIDC ? OIDC_PROVIDER_LABEL : 'Single Sign-On'

  return (
    <div className="min-h-screen flex items-center justify-center bg-sre-bg p-4">
      <Card className="w-full max-w-md">
        <div className="text-center mb-8">
          <span className="material-icons text-7xl text-sre-black eye-blink" aria-hidden="true">visibility</span>
          <h1 className="text-3xl font-bold text-sre-text mb-2">
            Be Observant
          </h1>
          <p className="text-sre-text-muted">
            Observing your entire Infrastructure
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-500 text-sm" role="alert">
            <span className="material-icons text-sm">error_outline</span>
            {error}
          </div>
        )}

        {authModeLoading && (
          <div className="flex items-center justify-center py-6">
            <Spinner size="md" />
          </div>
        )}

        {!authModeLoading && hasOIDC && (
          <OIDCLoginButton
            loading={oidcLoading}
            onClick={handleOIDCLogin}
            providerLabel={providerLabel}
          />
        )}

        {!authModeLoading && showDivider && (
          <div className="my-4 text-center text-xs text-sre-text-muted uppercase tracking-wide">
            or use password
          </div>
        )}

        {!authModeLoading && hasPassword && (
          <PasswordLoginForm
            username={username}
            password={password}
            onUsernameChange={setUsername}
            onPasswordChange={setPassword}
            onSubmit={handleSubmit}
            loading={loading}
            disabled={oidcLoading}
          />
        )}

        {!authModeLoading && !hasOIDC && !hasPassword && (
          <p className="text-sm text-red-500 text-center">
            Authentication is not configured. Contact your administrator.
          </p>
        )}

        <p className="text-xs text-sre-text-muted text-center mt-6">
          Contact your administrator if you need access or have forgotten your credentials.
        </p>
      </Card>
    </div>
  )
}
