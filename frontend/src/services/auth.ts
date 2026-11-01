/** Auth endpoints — docs/API_CONTRACT.md §5. */
import { AuthResponse, User } from '../types/contract';
import { apiJson, BASE_URL, refreshAccessToken, setAccessToken, toApiError } from './http';

async function authPost(path: string, body: unknown): Promise<AuthResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/auth/${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await toApiError(res);
  const auth = (await res.json()) as AuthResponse;
  setAccessToken(auth.access_token);
  return auth;
}

export const register = (email: string, password: string) => authPost('register', { email, password });

export const login = (email: string, password: string) => authPost('login', { email, password });

/** Restore a session from the refresh cookie (e.g. after a page reload). */
export const restoreSession = () => refreshAccessToken();

export async function logout(): Promise<void> {
  try {
    await fetch(`${BASE_URL}/api/v1/auth/logout`, { method: 'POST', credentials: 'include' });
  } finally {
    setAccessToken(null);
  }
}

export const fetchMe = () => apiJson<User>('/api/v1/auth/me');
