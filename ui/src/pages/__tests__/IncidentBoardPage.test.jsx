import { describe, it, expect } from 'vitest'
import { clearDroppedState } from '../IncidentBoardPage'

describe('clearDroppedState', () => {
  it('removes dropped id key when id is defined', () => {
    const prev = { a: true, b: true }
    const next = clearDroppedState(prev, 'a')

    expect(next).toEqual({ b: true })
    expect(prev).toEqual({ a: true, b: true })
  })

  it('returns previous state when dropped id is undefined', () => {
    const prev = { a: true }
    const next = clearDroppedState(prev, undefined)

    expect(next).toBe(prev)
  })

  it('returns previous state when dropped id is empty', () => {
    const prev = { a: true }
    const next = clearDroppedState(prev, '')

    expect(next).toBe(prev)
  })
})
