// frontend/src/components/AddressForm.tsx
import { useState } from "react";
import type { FormEvent } from "react";
import { createAddress } from "../api/addresses";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";
import type { AddressResponse } from "../types/address";

interface Props {
  onCreated?: (address: AddressResponse) => void;
  onCancel?: () => void;
  submitLabel?: string;
}

export function AddressForm({
  onCreated,
  onCancel,
  submitLabel = "Сохранить адрес",
}: Props) {
  const { showToast } = useToast();

  const [line1, setLine1] = useState("");
  const [line2, setLine2] = useState("");
  const [city, setCity] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [country, setCountry] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    if (!line1.trim() || !city.trim() || !postalCode.trim() || !country.trim()) {
      setFormError("Заполните обязательные поля адреса");
      return;
    }

    setSubmitting(true);
    try {
      const address = await createAddress({
        address_line1: line1.trim(),
        address_line2: line2.trim() ? line2.trim() : null,
        city: city.trim(),
        postal_code: postalCode.trim(),
        country: country.trim(),
        is_default: isDefault,
      });

      setLine1("");
      setLine2("");
      setCity("");
      setPostalCode("");
      setCountry("");
      setIsDefault(false);

      showToast("Адрес сохранён", "success");
      onCreated?.(address);
    } catch (err) {
      setFormError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form" onSubmit={handleSubmit}>
      <label className="form__field">
        <span>Адрес (строка 1) *</span>
        <input
          type="text"
          value={line1}
          onChange={(e) => setLine1(e.target.value)}
          maxLength={500}
          required
        />
      </label>

      <label className="form__field">
        <span>Адрес (строка 2)</span>
        <input
          type="text"
          value={line2}
          onChange={(e) => setLine2(e.target.value)}
          maxLength={500}
        />
      </label>

      <label className="form__field">
        <span>Город *</span>
        <input
          type="text"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          maxLength={100}
          required
        />
      </label>

      <label className="form__field">
        <span>Почтовый индекс *</span>
        <input
          type="text"
          value={postalCode}
          onChange={(e) => setPostalCode(e.target.value)}
          maxLength={20}
          required
        />
      </label>

      <label className="form__field">
        <span>Страна *</span>
        <input
          type="text"
          value={country}
          onChange={(e) => setCountry(e.target.value)}
          maxLength={100}
          required
        />
      </label>

      <label className="form__checkbox">
        <input
          type="checkbox"
          checked={isDefault}
          onChange={(e) => setIsDefault(e.target.checked)}
        />
        <span>Сделать адресом по умолчанию</span>
      </label>

      {formError !== null && <p className="form__error">{formError}</p>}

      <div className="form__actions">
        <button
          type="submit"
          className="btn btn--primary"
          disabled={submitting}
        >
          {submitting ? "Сохраняем..." : submitLabel}
        </button>
        {onCancel !== undefined && (
          <button
            type="button"
            className="btn btn--secondary"
            onClick={onCancel}
            disabled={submitting}
          >
            Отмена
          </button>
        )}
      </div>
    </form>
  );
}
