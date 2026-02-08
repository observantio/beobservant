/**
 * Permission enforcement hook
 * Checks user permissions for secure UI rendering
 */
import { useAuth } from '../contexts/AuthContext';

export function usePermissions() {
  const { user } = useAuth();
  
  const permissions = user?.permissions || [];
  
  const hasPermission = (permission) => {
    // Superusers have all permissions
    if (user?.is_superuser) return true;
    
    // Check if user has the specific permission
    return permissions.includes(permission);
  };
  
  const hasAnyPermission = (permissionList) => {
    if (user?.is_superuser) return true;
    return permissionList.some(p => permissions.includes(p));
  };
  
  const hasAllPermissions = (permissionList) => {
    if (user?.is_superuser) return true;
    return permissionList.every(p => permissions.includes(p));
  };
  
  return {
    permissions,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    isSuperuser: user?.is_superuser || false,
    canManageUsers: hasPermission('manage:users'),
    canManageGroups: hasPermission('manage:groups'),
    canReadAlerts: hasPermission('read:alerts'),
    canWriteAlerts: hasPermission('write:alerts'),
    canDeleteAlerts: hasPermission('delete:alerts'),
    canReadChannels: hasPermission('read:channels'),
    canWriteChannels: hasPermission('write:channels'),
    canDeleteChannels: hasPermission('delete:channels'),
  };
}
