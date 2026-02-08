import { useState } from 'react'
import PropTypes from 'prop-types'
import { Modal, Button, Input, Spinner } from './ui'
import { useToast } from '../contexts/ToastContext'
import * as api from '../api'

export default function ChangePasswordModal({ isOpen, onClose, userId, isForced = false }) {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  })

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (formData.newPassword.length < 8) {
      toast.error('Password must be at least 8 characters long')
      return
    }
    
    if (formData.newPassword !== formData.confirmPassword) {
      toast.error('New passwords do not match')
      return
    }
    
    setLoading(true)
    try {
      await api.updateUserPassword(userId, {
        current_password: formData.currentPassword,
        new_password: formData.newPassword
      })
      toast.success('Password updated successfully')
      setFormData({ currentPassword: '', newPassword: '', confirmPassword: '' })
      onClose()
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={isForced ? undefined : onClose}
      title={isForced ? 'Password Change Required' : 'Change Password'}
      size="md"
      className="bg-sre-bg-card rounded-xl shadow-2xl w-full mx-auto border border-sre-border/50 animate-slide-up flex flex-col max-w-2xl"
    >
      {isForced && (
        <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500 rounded text-yellow-500 text-sm">
          You must change your password before continuing. Please choose a secure password with at least 8 characters.
        </div>
      )}
      
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="currentPassword" className="block text-sm font-medium text-sre-text mb-1">
            Current Password
          </label>
          <Input
            id="currentPassword"
            type="password"
            value={formData.currentPassword}
            onChange={(e) => handleChange('currentPassword', e.target.value)}
            placeholder="Enter current password"
            required
            autoFocus
          />
        </div>

        <div>
          <label htmlFor="newPassword" className="block text-sm font-medium text-sre-text mb-1">
            New Password
          </label>
          <Input
            id="newPassword"
            type="password"
            value={formData.newPassword}
            onChange={(e) => handleChange('newPassword', e.target.value)}
            placeholder="Enter new password (min 8 characters)"
            required
            minLength={8}
          />
        </div>

        <div>
          <label htmlFor="confirmPassword" className="block text-sm font-medium text-sre-text mb-1">
            Confirm New Password
          </label>
          <Input
            id="confirmPassword"
            type="password"
            value={formData.confirmPassword}
            onChange={(e) => handleChange('confirmPassword', e.target.value)}
            placeholder="Confirm new password"
            required
            minLength={8}
          />
        </div>

        <div className="flex gap-3 justify-end pt-4">
          {!isForced && (
            <Button onClick={onClose} variant="ghost" disabled={loading}>
              Cancel
            </Button>
          )}
          <Button type="submit" variant="primary" disabled={loading}>
            {loading ? <Spinner size="sm" /> : 'Update Password'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

ChangePasswordModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  userId: PropTypes.string.isRequired,
  isForced: PropTypes.bool
}
