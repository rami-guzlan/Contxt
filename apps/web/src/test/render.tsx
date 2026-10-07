import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { vi } from "vitest";

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

type Reply = unknown | { status: number; body?: unknown };
type Handler = (call: Call) => Reply;

// A fake server: "GET /api/home" -> JSON. Unmatched requests fail loudly.
export function mockApi(routes: Record<string, Reply | Handler>) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = (init?.headers ?? {}) as Record<string, string>;
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body ?? null;
    const call = { method, path: url.pathname + url.search, body, headers };
    calls.push(call);
    const route = routes[`${method} ${url.pathname + url.search}`] ?? routes[`${method} ${url.pathname}`];
    if (route === undefined) {
      return new Response(JSON.stringify({ error: { code: "not_found", message: `unmocked ${method} ${url.pathname}` } }), {
        status: 404,
      });
    }
    const reply = typeof route === "function" ? (route as Handler)(call) : route;
    // A reply is an HTTP status wrapper only when its status is a number: records such as
    // Brain entries carry their own string `status`.
    const shaped = reply as { status?: unknown; body?: unknown };
    const wrapped = typeof shaped === "object" && shaped !== null && typeof shaped.status === "number";
    const status = wrapped ? (shaped.status as number) : 200;
    const payload = wrapped ? shaped.body : reply;
    if (status === 204) return new Response(null, { status });
    return new Response(JSON.stringify(payload ?? null), { status, headers: { "Content-Type": "application/json" } });
  });
  return calls;
}

export function renderAt(element: ReactElement, { path = "/", route = "/" } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={element} />
          <Route path="*" element={<p>navigated away</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export const workspace = {
  id: "ws_1",
  name: "Test workspace",
  timezone: "America/New_York",
  settings: {},
  created_at: "2026-09-28T13:00:00.000000Z",
  updated_at: "2026-09-28T13:00:00.000000Z",
  version: 1,
};

export const actors = [
  { id: "act_owner", kind: "human", name: "Owner", provider: null },
  { id: "act_claude", kind: "model", name: "Claude Code", provider: "claude-code" },
];
