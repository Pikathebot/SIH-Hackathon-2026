import { QueryRequest, QueryResponse, ApiError, HealthResponse } from '../types/contract';

const BASE_URL = (import.meta as any).env?.VITE_API_URL || '';

/**
 * Submit a natural-language query with 1-2 satellite images.
 * Adheres strictly to docs/API_CONTRACT.md POST /api/v1/query
 *
 * Timeout note from API_CONTRACT.md §3: [SEG] segmentation can take up to ~35s,
 * so the frontend does not enforce an aggressive client-side timeout below 60s.
 */
export async function submitQuery(
  request: QueryRequest,
  signal?: AbortSignal
): Promise<QueryResponse> {
  const endpoint = `${BASE_URL}/api/v1/query`;

  const payload = {
    query: request.query,
    images: request.images.map((img) => ({
      id: img.id,
      modality: img.modality,
      date: img.date || undefined,
      url_or_base64: img.url_or_base64,
    })),
  };

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal,
    });

    let data: any;
    try {
      data = await response.json();
    } catch {
      throw new Error(`Server returned HTTP ${response.status} with an unparseable response.`);
    }

    if (!response.ok) {
      const apiError = data as ApiError;
      const errorObj = new Error(
        apiError.error?.message || `Request failed with HTTP status ${response.status}`
      );
      (errorObj as any).code = apiError.error?.code || 'INTERNAL_ERROR';
      (errorObj as any).detail = apiError.error?.detail;
      throw errorObj;
    }

    return data as QueryResponse;
  } catch (err: any) {
    if (err.name === 'AbortError') {
      const abortErr = new Error('Analysis query timed out or was cancelled.');
      (abortErr as any).code = 'INTERNAL_ERROR';
      throw abortErr;
    }
    throw err;
  }
}

/**
 * Check backend system health and loaded model status.
 * Adheres strictly to docs/API_CONTRACT.md GET /api/v1/health
 */
export async function checkHealth(): Promise<HealthResponse> {
  const endpoint = `${BASE_URL}/api/v1/health`;
  try {
    const response = await fetch(endpoint, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      return {
        status: 'offline',
        rsunivlm_loaded: false,
        fusion_loaded: false,
      };
    }

    return (await response.json()) as HealthResponse;
  } catch {
    return {
      status: 'offline',
      rsunivlm_loaded: false,
      fusion_loaded: false,
    };
  }
}

export interface PreviewResult {
  preview_base64: string;
  format: 'geotiff' | 'standard';
  geospatial?: {
    crs: string;
    image_bounds: [number, number, number, number];
    secondary_image_bounds?: [number, number, number, number] | null;
  } | null;
  width: number;
  height: number;
}

/**
 * Generate a web-friendly PNG preview for any satellite image or GeoTIFF.
 */
export async function generatePreview(urlOrBase64: string): Promise<PreviewResult> {
  const endpoint = `${BASE_URL}/api/v1/preview`;
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url_or_base64: urlOrBase64 }),
  });

  if (!response.ok) {
    throw new Error(`Preview generation failed with status ${response.status}`);
  }

  return (await response.json()) as PreviewResult;
}

/**
 * Checks if a given image URL or data URI is natively renderable by standard web browsers.
 * Uses a strict whitelist: only PNG, JPEG, WebP, GIF, SVG, Blob, and HTTP URLs.
 * Raw GeoTIFFs, BigTIFFs, JPEG 2000, and octet-streams are NOT directly renderable in <img> tags.
 */
export function isBrowserRenderable(url?: string): boolean {
  if (!url) return false;
  const trimmed = url.trim();
  const lower = trimmed.toLowerCase();

  // Web URLs and Blob URLs
  if (lower.startsWith('http://') || lower.startsWith('https://') || lower.startsWith('blob:')) {
    return true;
  }

  // Strictly web-renderable data URIs
  if (
    lower.startsWith('data:image/png') ||
    lower.startsWith('data:image/jpeg') ||
    lower.startsWith('data:image/jpg') ||
    lower.startsWith('data:image/webp') ||
    lower.startsWith('data:image/gif') ||
    lower.startsWith('data:image/svg+xml')
  ) {
    return true;
  }

  // All other formats (TIFF, JP2, binary streams) require backend /api/v1/preview conversion
  return false;
}

export interface UploadResult {
  asset_id: string;
  filename: string;
  url: string;
  preview_base64: string;
  format: 'geotiff' | 'standard';
  width: number;
  height: number;
  size_bytes: number;
  geospatial?: {
    crs: string;
    image_bounds: [number, number, number, number];
  } | null;
}

/**
 * Stream large satellite imagery (>150MB to multi-GB GeoTIFFs) directly to server disk cache.
 * Tracks upload percentage via XMLHttpRequest and returns lightweight browser preview.
 */
export function uploadLargeImage(
  file: File,
  onProgress?: (percent: number) => void
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const endpoint = `${BASE_URL}/api/v1/upload`;
    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', endpoint);

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const pct = Math.round((event.loaded / event.total) * 100);
          onProgress(pct);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const res = JSON.parse(xhr.responseText) as UploadResult;
          resolve(res);
        } catch (e) {
          reject(new Error('Failed to parse upload response.'));
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.error?.message || `Upload failed with status ${xhr.status}`));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => {
      reject(new Error('Network error during file upload.'));
    };

    xhr.send(formData);
  });
}
