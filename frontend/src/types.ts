export interface CustomFilter {
  field: number;
  op: string;
  value: unknown;
}
export interface Choice {
  id: number;
  name: string;
}
export interface CustomField extends Choice {
  data_type: string;
  operators: string[];
  options: { id: string; label: string }[];
}
export interface Catalog {
  storage_paths: Choice[];
  correspondents: Choice[];
  document_types: Choice[];
  custom_fields: CustomField[];
}
export interface SearchSettings {
  custom_field_ids: number[];
}
export interface Rules {
  all_documents: boolean;
  document_ids: number[];
  storage_paths: number[];
  correspondents: number[];
  custom_fields: CustomFilter[];
}
export interface Profile {
  id: number;
  name: string;
  rules: Rules;
  error?: string | null;
}
export interface Document {
  id: number;
  title: string;
  created: string | null;
  correspondent: string | null;
  storage_path: string | null;
  document_type: string | null;
  custom_fields: { field: number; name: string; value: unknown }[];
  paperless_url: string;
}
export interface User {
  allow_download: boolean;
  id: number;
  name: string;
  active: boolean;
  is_admin: boolean;
  profile_id: number | null;
  issuer: string | null;
  subject: string | null;
  local: boolean;
}
export interface Code {
  allow_download: boolean;
  id: number;
  name: string;
  profile_id: number;
  expires_at: number;
  revoked: boolean;
}
export interface Session {
  authenticated: boolean;
  csrf: string;
  name?: string;
  is_admin?: boolean;
  has_access?: boolean;
  allow_download?: boolean;
  oidc_enabled: boolean;
}
export const emptyRules = (): Rules => ({
  all_documents: false,
  document_ids: [],
  storage_paths: [],
  correspondents: [],
  custom_fields: [],
});
export const emptyCatalog = (): Catalog => ({
  document_types: [],
  storage_paths: [],
  correspondents: [],
  custom_fields: [],
});
