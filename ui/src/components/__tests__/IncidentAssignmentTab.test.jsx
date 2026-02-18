import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import IncidentAssignmentTab from '../IncidentAssignmentTab'

describe('IncidentAssignmentTab', () => {
  it('calls onAssign when a user or "Unassigned" is clicked', () => {
    const onAssign = vi.fn()
    const setAssigneeSearch = vi.fn()
    const setIncidentDrafts = vi.fn()

    const activeIncident = { id: 'i1', assignee: '' }
    const activeIncidentDraft = { assignee: '' }
    const users = [ { id: 'u1', username: 'alice', email: 'a@example.com' } ]

    render(
      <IncidentAssignmentTab
        canReadUsers
        assigneeSearch=""
        setAssigneeSearch={setAssigneeSearch}
        activeIncident={activeIncident}
        activeIncidentDraft={activeIncidentDraft}
        setIncidentDrafts={setIncidentDrafts}
        filteredIncidentUsers={users}
        getUserLabel={(u) => `${u.username}${u.email ? ` ${u.email}` : ''}`}
        onAssign={onAssign}
      />
    )

    // click user
    const userBtn = screen.getByText('alice')
    fireEvent.click(userBtn)
    expect(onAssign).toHaveBeenCalledWith('i1', 'u1')

    // click Unassigned
    const unassignedBtn = screen.getByText('Unassigned')
    fireEvent.click(unassignedBtn)
    expect(onAssign).toHaveBeenCalledWith('i1', '')
  })

  it('shows permission message when cannot read users', () => {
    render(
      <IncidentAssignmentTab
        canReadUsers={false}
        assigneeSearch=""
        setAssigneeSearch={() => {}}
        activeIncident={{ id: 'i1' }}
        activeIncidentDraft={{}}
        setIncidentDrafts={() => {}}
        filteredIncidentUsers={[]}
        getUserLabel={() => ''}
        onAssign={() => {}}
      />
    )

    expect(screen.getByText(/You do not have permission to list users/i)).toBeInTheDocument()
  })
})
