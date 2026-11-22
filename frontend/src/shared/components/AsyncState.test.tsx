import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AsyncState } from './AsyncState'

type Props = Parameters<typeof AsyncState>[0]

function renderState(overrides: Partial<Props> = {}) {
  const props: Props = {
    loading: false,
    error: null,
    empty: false,
    children: <p>Content</p>,
    ...overrides,
  }
  return render(<AsyncState {...props} />)
}

describe('AsyncState', () => {
  it('renders the default loading text', () => {
    renderState({ loading: true })
    expect(screen.getByText('Загрузка…')).toBeInTheDocument()
    expect(screen.queryByText('Content')).not.toBeInTheDocument()
  })

  it('renders a custom loading text', () => {
    renderState({ loading: true, loadingText: 'Подождите' })
    expect(screen.getByText('Подождите')).toBeInTheDocument()
  })

  it('renders an error with an alert role and no retry button by default', () => {
    renderState({ error: 'Something broke' })
    expect(screen.getByRole('alert')).toHaveTextContent('Something broke')
    expect(
      screen.queryByRole('button', { name: 'Повторить' }),
    ).not.toBeInTheDocument()
  })

  it('calls onRetry when the retry button is clicked', () => {
    const onRetry = vi.fn()
    renderState({ error: 'Network error', onRetry })

    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('renders the default empty text', () => {
    renderState({ empty: true })
    expect(screen.getByText('Нет данных')).toBeInTheDocument()
  })

  it('renders a custom empty text', () => {
    renderState({ empty: true, emptyText: 'Ничего не найдено' })
    expect(screen.getByText('Ничего не найдено')).toBeInTheDocument()
  })

  it('renders children when not loading, no error, and not empty', () => {
    renderState()
    expect(screen.getByText('Content')).toBeInTheDocument()
  })

  it('loading takes precedence over error and empty', () => {
    renderState({ loading: true, error: 'x', empty: true })
    expect(screen.getByText('Загрузка…')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('Нет данных')).not.toBeInTheDocument()
  })
})