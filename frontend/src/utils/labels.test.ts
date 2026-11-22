import { describe, expect, it } from 'vitest'
import {
  orderStatusLabel,
  paymentStatusLabel,
  productStatusLabel,
} from './labels'

describe('productStatusLabel', () => {
  it.each([
    ['available', 'В наличии'],
    ['out_of_stock', 'Нет в наличии'],
    ['discontinued', 'Снят с производства'],
  ] as const)('%s -> %s', (status, label) => {
    expect(productStatusLabel(status)).toBe(label)
  })

  it('falls back to the raw value for unknown statuses', () => {
    // The `as never` cast is the standard escape hatch for the default
    // branch of an exhaustive switch over a string union. Runtime is
    // what we care about here.
    expect(productStatusLabel('bogus' as never)).toBe('bogus')
  })
})

describe('orderStatusLabel', () => {
  it.each([
    ['pending', 'Ожидает оплаты'],
    ['paid', 'Оплачен'],
    ['shipped', 'Отправлен'],
    ['delivered', 'Доставлен'],
    ['canceled', 'Отменён'],
  ] as const)('%s -> %s', (status, label) => {
    expect(orderStatusLabel(status)).toBe(label)
  })

  it('falls back to the raw value for unknown statuses', () => {
    expect(orderStatusLabel('refunded' as never)).toBe('refunded')
  })
})

describe('paymentStatusLabel', () => {
  it.each([
    ['pending', 'Ожидает'],
    ['completed', 'Завершён'],
    ['failed', 'Ошибка'],
    ['refunded', 'Возврат'],
  ] as const)('%s -> %s', (status, label) => {
    expect(paymentStatusLabel(status)).toBe(label)
  })

  it('falls back to the raw value for unknown statuses', () => {
    expect(paymentStatusLabel('cancelled' as never)).toBe('cancelled')
  })
})