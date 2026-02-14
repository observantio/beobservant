export function getRoleVariant(role) {
  if (role === 'admin') return 'error'
  if (role === 'user') return 'warning'
  if (role === 'viewer') return 'success'
  return 'default'
}

export function getRoleBorderColor(role) {
  if (role === 'admin') return 'border-red-500'
  if (role === 'user') return 'border-yellow-500'
  if (role === 'viewer') return 'border-green-500'
  return 'border-sre-border/50'
}

export function getUserInitials(user) {
  return (user?.full_name || user?.username || 'U')
    .split(' ')
    .map((part) => part[0])
    .join('')
    .substring(0, 2)
    .toUpperCase()
}
