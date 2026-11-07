// frontend/src/pages/AddressesPage.tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteAddress,
  fetchAddresses,
  setDefaultAddress,
} from "../api/addresses";
import { AddressForm } from "../components/AddressForm";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";
import type { AddressResponse } from "../types/address";

export function AddressesPage() {
  const { showToast } = useToast();

  const [addresses, setAddresses] = useState<AddressResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [pendingId, setPendingId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchAddresses()
      .then((data) => {
        if (!cancelled) setAddresses(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(getErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  function handleCreated(address: AddressResponse) {
    setAddresses((prev) => {
      const withoutOldDefault = address.is_default
        ? prev.map((item) => ({ ...item, is_default: false }))
        : prev;
      return [...withoutOldDefault, address];
    });
    setShowForm(false);
  }

  async function handleDelete(addressId: number) {
    if (!window.confirm("Удалить этот адрес?")) {
      return;
    }

    setPendingId(addressId);
    try {
      await deleteAddress(addressId);
      setAddresses((prev) =>
        prev.filter((address) => address.id !== addressId)
      );
      showToast("Адрес удалён", "info");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPendingId(null);
    }
  }

  async function handleSetDefault(addressId: number) {
    setPendingId(addressId);
    try {
      const updated = await setDefaultAddress(addressId);
      setAddresses((prev) =>
        prev.map((address) =>
          address.id === updated.id
            ? updated
            : { ...address, is_default: false }
        )
      );
      showToast("Адрес по умолчанию обновлён", "success");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="addresses-page">
      <div className="page-heading">
        <h1>Адреса доставки</h1>
        <Link to="/">← В каталог</Link>
      </div>

      {loading && addresses.length === 0 && <LoadingState />}

      {error !== null && (
        <ErrorState
          message={error}
          onRetry={() => setReloadKey((key) => key + 1)}
        />
      )}

      {!loading && error === null && addresses.length === 0 && (
        <EmptyState message="Сохранённых адресов пока нет" />
      )}

      {addresses.length > 0 && (
        <div className="address-list">
          {addresses.map((address) => {
            const pending = pendingId === address.id;
            return (
              <div className="address-card" key={address.id}>
                <div className="address-card__body">
                  <p>
                    {address.city}, {address.address_line1}
                    {address.address_line2
                      ? `, ${address.address_line2}`
                      : ""}
                  </p>
                  <p className="muted">
                    {address.postal_code}, {address.country}
                  </p>
                  {address.is_default && (
                    <span className="badge badge--default">
                      По умолчанию
                    </span>
                  )}
                </div>

                <div className="address-card__actions">
                  {!address.is_default && (
                    <button
                      type="button"
                      className="btn btn--secondary btn--sm"
                      onClick={() => void handleSetDefault(address.id)}
                      disabled={pending}
                    >
                      Сделать основным
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn--danger btn--sm"
                    onClick={() => void handleDelete(address.id)}
                    disabled={pending}
                  >
                    Удалить
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!showForm && (
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => setShowForm(true)}
        >
          Добавить адрес
        </button>
      )}

      {showForm && (
        <section className="checkout-section">
          <h2>Новый адрес</h2>
          <AddressForm
            onCreated={handleCreated}
            onCancel={() => setShowForm(false)}
          />
        </section>
      )}
    </div>
  );
}
