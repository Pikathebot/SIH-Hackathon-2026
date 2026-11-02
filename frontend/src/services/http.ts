/**
 * Authenticated HTTP for docs/API_CONTRACT.md v2 (§5).
 *
 * - The access token lives only in memory (never localStorage); the refresh token is an
 *   httpOnly cookie the browser sends to /api/v1/auth/* by itself.
 * - On a 401, apiFetch refreshes once and retries once. Refreshes are single-flight:
 *   the backend treats a reused (already rotated) refresh token as theft and revokes
 *   every session, so two parallel refresh calls must never happen.
 */
import { ApiError, AuthResponse } from '../types/contract';

export const BASE_URL: string = (import.meta as any).env?.VITE_API_URL || '';

let accessToken: string | null = null;
let refreshInFlight: Promise<AuthResponse | null> | null = null;
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Called when a refresh fails, i.e. the user must sign in again. */
export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler;
}

export class ApiRequestError extends Error {
  code: string;
  status: number;
  detail?: string;
  requestId?: string;

  constructor(status: number, code: string, message: string, detail?: string, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.requestId = requestId;
  }
}

export async function toApiError(response: Response): Promise<ApiRequestError> {
  let body: ApiError | null = null;
  try {
    body = (await response.json()) as ApiError;
  } catch {
    /* non-JSON error body */
  }
  return new ApiRequestError(
    response.status,
    body?.error?.code || (response.status === 401 ? 'UNAUTHORIZED' : 'INTERNAL_ERROR'),
    body?.error?.message || `Request failed with HTTP status ${response.status}`,
    body?.error?.detail,
    body?.error?.request_id || response.headers.get('X-Request-ID') || undefined,
  );
}

/**
 * Exchange the refresh cookie for a new access token. Single-flight.
 * Resolves null only when the server says the session is gone (401/403). A transient
 * failure (429 rate limit, 5xx, network error) rejects with an ApiRequestError instead,
 * so callers show a retryable error rather than signing the user out.
 */
export function refreshAccessToken(): Promise<AuthResponse | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      let res: Response;
      try {
        res = await fetch(`${BASE_URL}/api/v1/auth/refresh`, { method: 'POST', credentials: 'include' });
      } catch {
        throw new ApiRequestError(0, 'NETWORK_ERROR', 'Cannot reach the server. Check your connection and try again.');
      }
      try {
        if (res.status === 401 || res.status === 403) {
          setAccessToken(null);
          return null;
        }
        if (!res.ok) throw await toApiError(res);
        const auth = (await res.json()) as AuthResponse;
        setAccessToken(auth.access_token);
        return auth;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

function withAuth(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  return { ...init, headers, credentials: 'include' };
}

/** fetch() for authenticated endpoints: adds the Bearer token, refreshes and retries once on 401. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = `${BASE_URL}${path}`;
  let res = await fetch(url, withAuth(init));
  if (res.status !== 401) return res;

  const refreshed = await refreshAccessToken();
  if (!refreshed) {
    onSessionExpired?.();
    return res;
  }
  res = await fetch(url, withAuth(init));
  if (res.status === 401) onSessionExpired?.();
  return res;
}

/** apiFetch + JSON body/response + contract error handling. */
export async function apiJson<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (json !== undefined) headers.set('Content-Type', 'application/json');
  const res = await apiFetch(path, { ...rest, headers, body: json !== undefined ? JSON.stringify(json) : rest.body });
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
