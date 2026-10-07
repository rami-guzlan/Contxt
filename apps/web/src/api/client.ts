// A small fetch wrapper. The session is an HttpOnly cookie set by /auth/login, so every
// state-changing request also carries the CSRF header the server requires.

export interface ErrorBody {
  code: string;
  message: string;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorBody;

  constructor(status: number, body: ErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (method !== "GET") headers["X-Workspace-CSRF"] = "1";
  if (options.form) {
    payload = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(options.body);
  }
  const response = await fetch(path, {
    method,
    headers,
    body: payload,
    credentials: "same-origin",
    signal: options.signal,
  });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const data: unknown = text ? safeJson(text) : null;
  if (!response.ok) {
    const error = (data as { error?: ErrorBody } | null)?.error;
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(
      response.status,
      error ?? {
        code: response.status === 422 ? "invalid" : "error",
        message: typeof detail === "string" ? detail : describeValidation(detail) ?? response.statusText,
      },
    );
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function describeValidation(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  return detail
    .map((item: { loc?: unknown[]; msg?: string }) => `${(item.loc ?? []).slice(1).join(".")}: ${item.msg ?? ""}`)
    .join("; ");
}

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body ?? {} });
export const put = <T>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body });
export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });

export function query(params: Record<string, string | number | boolean | null | undefined | string[]>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) for (const each of value) search.append(key, each);
    else if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
