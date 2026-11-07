// frontend/src/api/addresses.ts
/**
 * Addresses API. Все эндпоинты требуют авторизации.
 */
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type {
  AddressCreate,
  AddressResponse,
  AddressUpdate,
} from "../types/address";

export function fetchAddresses(): Promise<AddressResponse[]> {
  return apiGet<AddressResponse[]>("/api/v1/addresses");
}

export function createAddress(
  data: AddressCreate
): Promise<AddressResponse> {
  return apiPost<AddressResponse>("/api/v1/addresses", data);
}

export function updateAddress(
  addressId: number,
  data: AddressUpdate
): Promise<AddressResponse> {
  return apiPatch<AddressResponse>(`/api/v1/addresses/${addressId}`, data);
}

export function deleteAddress(addressId: number): Promise<void> {
  return apiDelete<void>(`/api/v1/addresses/${addressId}`);
}

export function setDefaultAddress(
  addressId: number
): Promise<AddressResponse> {
  return apiPost<AddressResponse>(
    `/api/v1/addresses/${addressId}/set-default`
  );
}
