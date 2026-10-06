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
  const changesAuthentication =
    path === "/auth/code" || path === "/auth/logout";
  if (changesAuthentication) {
    sessionGeneration++;
    sessionRequest = undefined;
  }
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
  if (changesAuthentication) {
    // A focus refresh may have started while authentication was in flight.
    sessionGeneration++;
    sessionRequest = undefined;
  }
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
let sessionRequest: Promise<Session> | undefined;
let sessionGeneration = 0;
export function refreshSession() {
  if (!sessionRequest) {
    const generation = sessionGeneration;
    const pending = api<Session>("/auth/session")
      .then((value) => {
        if (generation === sessionGeneration) session.value = value;
        return value;
      })
      .finally(() => {
        if (sessionRequest === pending) sessionRequest = undefined;
      });
    sessionRequest = pending;
  }
  return sessionRequest;
}
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Ein Fehler ist aufgetreten.";
