/** Analysis sessions, history and asset previews — docs/API_CONTRACT.md §5. */
import { HistoryEntry, SessionDto } from '../types/contract';
import { apiFetch, apiJson } from './http';

export const listSessions = () => apiJson<SessionDto[]>('/api/v1/sessions');

export const createSession = (title?: string) =>
  apiJson<SessionDto>('/api/v1/sessions', { method: 'POST', json: title ? { title } : {} });

export const renameSession = (id: string, title: string) =>
  apiJson<SessionDto>(`/api/v1/sessions/${id}`, { method: 'PATCH', json: { title } });

export const deleteSession = (id: string) => apiJson<void>(`/api/v1/sessions/${id}`, { method: 'DELETE' });

export const fetchHistory = (id: string) => apiJson<HistoryEntry[]>(`/api/v1/sessions/${id}/queries`);

// Asset previews need the Bearer token, so they cannot be plain <img src> URLs:
// fetch once as a blob and hand out an object URL, cached for the page's lifetime.
const previewCache = new Map<string, Promise<string | null>>();

export function assetPreviewUrl(assetId: string): Promise<string | null> {
  let p = previewCache.get(assetId);
  if (!p) {
    p = (async () => {
      const res = await apiFetch(`/api/v1/assets/${assetId}/preview`);
      if (!res.ok) return null;
      return URL.createObjectURL(await res.blob());
    })().catch(() => null);
    previewCache.set(assetId, p);
  }
  return p;
}

export function clearPreviewCache() {
  previewCache.forEach((p) => p.then((url) => url && URL.revokeObjectURL(url)));
  previewCache.clear();
}
