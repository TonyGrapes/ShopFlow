import { act, render, screen } from '@testing-library/react'
import { useContext } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from './ToastProvider'
import { ToastContext } from './toastContext'

function Consumer() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('ToastContext is missing — wrap in ToastProvider')
  return (
    <div>
      <span data-testid="count">{ctx.toasts.length}</span>
      <span data-testid="ids">{ctx.toasts.map((t) => t.id).join(',')}</span>
      <span data-testid="messages">
        {ctx.toasts.map((t) => t.message).join('|')}
      </span>
      <span data-testid="types">{ctx.toasts.map((t) => t.type).join(',')}</span>
      <button type="button" onClick={() => ctx.showToast('hello')}>
        show-info
      </button>
      <button type="button" onClick={() => ctx.showToast('boom', 'error')}>
        show-error
      </button>
      <button
        type="button"
        onClick={() => ctx.removeToast(ctx.toasts[0]?.id ?? 0)}
      >
        remove-first
      </button>
    </div>
  )
}

function renderProvider() {
  return render(
    <ToastProvider>
      <Consumer />
    </ToastProvider>,
  )
}

describe('ToastProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts with no toasts', () => {
    renderProvider()
    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('adds a toast with the default info type', () => {
    renderProvider()
    act(() => {
      screen.getByText('show-info').click()
    })
    expect(screen.getByTestId('count')).toHaveTextContent('1')
    expect(screen.getByTestId('messages')).toHaveTextContent('hello')
    expect(screen.getByTestId('types')).toHaveTextContent('info')
  })

  it('increments ids for successive toasts', () => {
    renderProvider()
    act(() => {
      screen.getByText('show-info').click()
      screen.getByText('show-info').click()
    })
    expect(screen.getByTestId('ids')).toHaveTextContent('1,2')
  })

  it('respects an explicit toast type', () => {
    renderProvider()
    act(() => {
      screen.getByText('show-error').click()
    })
    expect(screen.getByTestId('types')).toHaveTextContent('error')
  })

  it('auto-dismisses after TOAST_TTL_MS (3500 ms)', () => {
    renderProvider()
    act(() => {
      screen.getByText('show-info').click()
    })
    expect(screen.getByTestId('count')).toHaveTextContent('1')

    act(() => {
      vi.advanceTimersByTime(3499)
    })
    expect(screen.getByTestId('count')).toHaveTextContent('1')

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('removes a toast manually via removeToast', () => {
    renderProvider()
    act(() => {
      screen.getByText('show-info').click()
    })
    act(() => {
      screen.getByText('remove-first').click()
    })
    expect(screen.getByTestId('count')).toHaveTextContent('0')
  })

  it('clears pending timers on unmount (no leak)', () => {
    const { unmount } = renderProvider()
    act(() => {
      screen.getByText('show-info').click()
    })
    expect(vi.getTimerCount()).toBe(1)

    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})