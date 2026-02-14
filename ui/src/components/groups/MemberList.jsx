import { useState } from 'react'
import PropTypes from 'prop-types'
import { Input, Checkbox } from '../ui'

export default function MemberList({ users, selectedMembers, toggleMember }) {
  const [searchQuery, setSearchQuery] = useState('')

  if (!users.length) {
    return <div className="text-sm text-sre-text-muted">No users available.</div>
  }

  const filteredUsers = users.filter((user) => {
    const query = searchQuery.toLowerCase()
    return (
      (user.full_name || user.username).toLowerCase().includes(query) ||
      user.email.toLowerCase().includes(query)
    )
  })

  const displayedUsers = filteredUsers.slice(0, 5)
  const hasMore = filteredUsers.length > 5

  return (
    <div className="space-y-3">
      <Input
        placeholder="Search users by name or email..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="text-sm"
      />

      <div className="max-h-64 overflow-y-auto space-y-2 pr-2">
        {displayedUsers.length === 0 ? (
          <div className="text-sm text-sre-text-muted">
            {searchQuery ? 'No users match your search.' : 'No users available.'}
          </div>
        ) : (
          <>
            {displayedUsers.map((user) => (
              <label
                key={user.id}
                className="flex items-center gap-3 p-2 border border-sre-border rounded hover:bg-sre-surface/50 cursor-pointer"
              >
                <Checkbox
                  checked={selectedMembers.includes(user.id)}
                  onChange={() => toggleMember(user.id)}
                />
                <div className="text-sm text-sre-text">
                  {user.full_name || user.username}
                  <span className="text-xs text-sre-text-muted ml-2">{user.email}</span>
                </div>
              </label>
            ))}
            {hasMore && (
              <div className="text-xs text-sre-text-muted text-center py-2">
                Showing first 5 of {filteredUsers.length} users. Use search to find specific users.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

MemberList.propTypes = {
  users: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.string.isRequired,
    username: PropTypes.string,
    full_name: PropTypes.string,
    email: PropTypes.string.isRequired,
  })).isRequired,
  selectedMembers: PropTypes.arrayOf(PropTypes.string).isRequired,
  toggleMember: PropTypes.func.isRequired,
}
