import { afterEach, expect, it, vi } from "vitest";
import { api, refreshSession, session } from "../src/api";

function deferredResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
afterEach(() => {
  vi.unstubAllGlobals();
  session.value = null;
});
it("shares overlapping refreshes, but starts a fresh request after completion or failure", async () => {
  const deferred = deferredResponse();
  const fetch = vi.fn().mockReturnValueOnce(deferred.promise);
  vi.stubGlobal("fetch", fetch);
  const first = refreshSession();
  const second = refreshSession();
  expect(fetch).toHaveBeenCalledTimes(1);
  deferred.resolve(Response.json({ authenticated: true, name: "A" }));
  expect(await first).toEqual(await second);
  fetch.mockRejectedValueOnce(new Error("offline"));
  await expect(refreshSession()).rejects.toThrow("offline");
  fetch.mockResolvedValueOnce(Response.json({ authenticated: false }));
  await refreshSession();
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(session.value?.authenticated).toBe(false);
});
it("does not reuse or apply a refresh from before an authentication change", async () => {
  const stale = deferredResponse();
  const fresh = deferredResponse();
  const fetch = vi
    .fn()
    .mockReturnValueOnce(stale.promise)
    .mockResolvedValueOnce(Response.json({ ok: true }))
    .mockReturnValueOnce(fresh.promise);
  vi.stubGlobal("fetch", fetch);
  const old = refreshSession();
  await api("/auth/logout", {});
  const current = refreshSession();
  stale.resolve(Response.json({ authenticated: true, name: "old" }));
  await old;
  expect(session.value).toBeNull();
  expect(refreshSession()).toBe(current);
  fresh.resolve(Response.json({ authenticated: false }));
  await current;
  expect(session.value?.authenticated).toBe(false);
});
