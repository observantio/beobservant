import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { api_keys: [ { id: 'k1', name: 'SharedKey', is_shared: true, owner_user_id: 'owner1', key: 'org-1', is_enabled: true, is_default: false } ] }, updateUser: () => {} })
}))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))

import ApiKeyPage from '../ApiKeyPage'

describe('ApiKeyPage', () => {
  it('displays "shared by" for keys that are shared to the current user', () => {
    render(<ApiKeyPage />)

    expect(screen.getByText(/Shared by owner1/i)).toBeInTheDocument()
  })
})
