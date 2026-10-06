import { ref } from "vue";
import type { Session } from "./types";
export const session = ref<Session | null>(null);
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  body?: unknown,
  method = body === undefined ? "GET" : "POST",
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      "X-CSRF-Token": session.value?.csrf ?? "",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      session.value = null;
      window.dispatchEvent(new Event("session-expired"));
    }
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : "Die Anfrage ist fehlgeschlagen.",
      response.status,
    );
  }
  return data as T;
}
export async function refreshSession() {
  session.value = await api<Session>("/auth/session");
  return session.value;
}
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Ein Fehler ist aufgetreten.";
