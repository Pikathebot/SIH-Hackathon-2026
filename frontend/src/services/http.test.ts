import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiRequestError, apiFetch, apiJson, getAccessToken, refreshAccessToken, setAccessToken,
  setSessionExpiredHandler, toApiError,
} from './http';
import { isBrowserRenderable } from './api';

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
const auth = (token: string) => json(200, { access_token: token, token_type: 'bearer', user: { id: 'u', email: 'a@b.c' } });

let fetchMock: ReturnType<typeof vi.fn>;
let expired: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  expired = vi.fn();
  setSessionExpiredHandler(expired);
  setAccessToken('old-token');
});

const authHeader = (call: unknown[]) => new Headers((call[1] as RequestInit).headers).get('Authorization');

describe('apiFetch', () => {
  it('sends the in-memory bearer token and cookies', async () => {
    fetchMock.mockResolvedValueOnce(json(200, {}));
    await apiFetch('/api/v1/storage');
    expect(authHeader(fetchMock.mock.calls[0])).toBe('Bearer old-token');
    expect((fetchMock.mock.calls[0][1] as RequestInit).credentials).toBe('include');
  });

  it('on 401 refreshes once and retries with the new token', async () => {
    fetchMock
      .mockResolvedValueOnce(json(401, { error: { code: 'UNAUTHORIZED', message: 'expired' } }))
      .mockResolvedValueOnce(auth('new-token'))
      .mockResolvedValueOnce(json(200, { ok: true }));
    const res = await apiFetch('/api/v1/storage');
    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain('/api/v1/auth/refresh');
    expect(authHeader(fetchMock.mock.calls[2])).toBe('Bearer new-token');
    expect(getAccessToken()).toBe('new-token');
    expect(expired).not.toHaveBeenCalled();
  });

  it('parallel 401s share one refresh (a reused refresh token revokes every session)', async () => {
    let refreshes = 0;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes('/auth/refresh')) {
        refreshes += 1;
        await new Promise((r) => setTimeout(r, 10));
        return auth('fresh');
      }
      return new Headers(init?.headers).get('Authorization') === 'Bearer fresh' ? json(200, {}) : json(401, {});
    });
    const results = await Promise.all([1, 2, 3, 4].map(() => apiFetch('/api/v1/sessions')));
    expect(results.map((r) => r.status)).toEqual([200, 200, 200, 200]);
    expect(refreshes).toBe(1);
  });

  it('signs the user out when the refresh is refused', async () => {
    fetchMock.mockResolvedValueOnce(json(401, {})).mockResolvedValueOnce(json(401, {}));
    const res = await apiFetch('/api/v1/sessions');
    expect(res.status).toBe(401);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
  });

  it.each([429, 500, 503])('does not sign the user out when the refresh fails with %i', async (status) => {
    fetchMock.mockResolvedValueOnce(json(401, {}))
      .mockResolvedValueOnce(json(status, { error: { code: 'RATE_LIMITED', message: 'slow down' } }));
    await expect(apiFetch('/api/v1/sessions')).rejects.toBeInstanceOf(ApiRequestError);
    expect(expired).not.toHaveBeenCalled();
  });

  it('turns a network failure during refresh into a retryable NETWORK_ERROR', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(refreshAccessToken()).rejects.toMatchObject({ code: 'NETWORK_ERROR', status: 0 });
    expect(expired).not.toHaveBeenCalled();
  });

  it('does not refresh for non-401 errors', async () => {
    fetchMock.mockResolvedValueOnce(json(403, {}));
    expect((await apiFetch('/api/v1/sessions')).status).toBe(403);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('apiJson / toApiError', () => {
  it('sends JSON and maps a contract error body', async () => {
    fetchMock.mockResolvedValueOnce(json(503, { error: { code: 'QUEUE_FULL', message: 'Busy', request_id: 'rid-1' } }));
    const err = await apiJson('/api/v1/query', { method: 'POST', json: { q: 1 } }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect(err).toMatchObject({ status: 503, code: 'QUEUE_FULL', message: 'Busy', requestId: 'rid-1' });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json');
    expect(init.body).toBe('{"q":1}');
  });

  it('returns undefined for 204', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    expect(await apiJson('/api/v1/assets/x', { method: 'DELETE' })).toBeUndefined();
  });

  it('copes with a non-JSON error body (e.g. an nginx 502 page) and keeps the request id header', async () => {
    const err = await toApiError(new Response('<html>Bad Gateway</html>', { status: 502, headers: { 'X-Request-ID': 'rid-2' } }));
    expect(err).toMatchObject({ status: 502, code: 'INTERNAL_ERROR', requestId: 'rid-2' });
    expect(err.message).toContain('502');
  });
});

describe('isBrowserRenderable', () => {
  it.each([
    ['https://example.com/a.png', true],
    ['blob:http://localhost/123', true],
    ['data:image/png;base64,AAAA', true],
    ['  DATA:IMAGE/JPEG;base64,AAAA', true],
    ['data:image/tiff;base64,SUkqAA==', false],
    ['data:application/octet-stream;base64,AA', false],
    ['data:text/html,<script>alert(1)</script>', false],
    ['javascript:alert(1)', false],
    ['/api/v1/assets/123', false],
    ['', false],
    [undefined, false],
  ])('%s -> %s', (url, expected) => {
    expect(isBrowserRenderable(url as string | undefined)).toBe(expected);
  });
});
