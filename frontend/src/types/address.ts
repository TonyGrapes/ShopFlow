// frontend/src/types/address.ts
/**
 * Типы, синхронные с backend app/schemas/address.py.
 */

// app/schemas/address.py — AddressCreate
export interface AddressCreate {
  address_line1: string;
  address_line2?: string | null;
  city: string;
  postal_code: string;
  country: string;
  is_default?: boolean;
}

// app/schemas/address.py — AddressUpdate
export interface AddressUpdate {
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  postal_code?: string | null;
  country?: string | null;
  is_default?: boolean | null;
}

// app/schemas/address.py — AddressResponse
export interface AddressResponse {
  id: number;
  address_line1: string;
  address_line2: string | null;
  city: string;
  postal_code: string;
  country: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

// app/schemas/address.py — AddressBrief
export interface AddressBrief {
  id: number;
  city: string;
  address_line1: string;
  postal_code: string;
  country: string;
}
