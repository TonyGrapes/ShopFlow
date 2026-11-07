// frontend/src/utils/validation.ts
/**
 * Клиентские проверки форм.
 *
 * Источник ограничений — backend app/schemas/auth.py:
 * - email: EmailStr;
 * - password: 8..128;
 * - first_name/last_name: 1..100;
 * - phone_number: 5..20.
 *
 * Телефон дополнительно проверяем на допустимые символы,
 * чтобы не отправлять заведомо неверные данные.
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_RE = /^[+\d][\d\s()-]{4,19}$/;

export function isValidEmail(value: string): boolean {
  return EMAIL_RE.test(value.trim());
}

export function isValidPhone(value: string): boolean {
  return PHONE_RE.test(value.trim());
}

export function isValidPassword(value: string): boolean {
  return value.length >= 8 && value.length <= 128;
}
