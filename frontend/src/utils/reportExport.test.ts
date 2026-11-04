import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { exportGeoJSON, exportMissionPDF, exportReportJSON } from './reportExport';
import type { QueryImage, QueryResponse } from '../types/contract';

const XSS = '<img src=x onerror=alert(1)><script>alert(2)</script>';

function response(over: Partial<QueryResponse> = {}): QueryResponse {
  return {
    answer: 'Two ships are visible.',
    confidence: 0.82,
    task: 'detection',
    visual_evidence: {
      type: 'bbox',
      boxes: [[10, 20, 110, 220], [300, 300, 400, 380]],
      image_size: [1000, 800],
      geospatial: {
        crs: 'EPSG:4326',
        image_bounds: [4.0, 51.9, 4.1, 52.0],
        geo_boxes: [
          [[4.0, 52.0], [4.01, 52.0], [4.01, 51.99], [4.0, 51.99]], // open ring
          [[4.05, 51.95], [4.06, 51.95], [4.06, 51.94], [4.05, 51.94], [4.05, 51.95]], // closed
        ],
      },
    },
    execution_summary: {
      selected_task: 'detection', tool_used: 'qwen_vl_vg', parameters: {}, inputs_validated: true, latency_ms: 1234,
    },
    ...over,
  };
}

const image = (over: Partial<QueryImage> = {}): QueryImage => ({
  id: 'a', modality: 'optical', url_or_base64: '/api/v1/assets/x', name: 'port.tif', ...over,
});

// Capture what the export functions hand to the browser
let blobs: { text: Promise<string>; name: string; type: string }[] = [];

beforeEach(() => {
  blobs = [];
  const created: Blob[] = [];
  vi.stubGlobal('URL', Object.assign(URL, {
    createObjectURL: vi.fn((b: Blob) => { created.push(b); return `blob:test/${created.length}`; }),
    revokeObjectURL: vi.fn(),
  }));
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    const b = created[Number(this.href.split('/').pop()) - 1];
    const text = new Promise<string>((res) => {
      const fr = new FileReader();
      fr.onload = () => res(String(fr.result));
      fr.readAsText(b);
    });
    blobs.push({ text, name: this.download, type: b.type });
  });
});

afterEach(() => vi.unstubAllGlobals());

describe('exportGeoJSON', () => {
  it('writes one closed polygon per detected box', async () => {
    exportGeoJSON(response(), [image()]);
    expect(blobs).toHaveLength(1);
    expect(blobs[0].type).toBe('application/geo+json');
    expect(blobs[0].name).toMatch(/^satquery_detection_\d{4}-\d{2}-\d{2}\.geojson$/);
    const fc = JSON.parse(await blobs[0].text);
    expect(fc.type).toBe('FeatureCollection');
    expect(fc.features).toHaveLength(2);
    for (const f of fc.features) {
      const ring = f.geometry.coordinates[0];
      expect(f.geometry.type).toBe('Polygon');
      expect(ring[0]).toEqual(ring[ring.length - 1]);
      expect(ring.length).toBeGreaterThanOrEqual(4);
      expect(f.properties.source_image).toBe('port.tif');
    }
    expect(fc.features[0].geometry.coordinates[0]).toHaveLength(5); // the open ring was closed
    expect(fc.features[1].geometry.coordinates[0]).toHaveLength(5); // the closed one was left alone
  });

  it('falls back to the image footprint when there are no geo boxes', async () => {
    const r = response();
    r.visual_evidence.geospatial!.geo_boxes = null;
    exportGeoJSON(r);
    const fc = JSON.parse(await blobs[0].text);
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0].geometry.coordinates[0]).toEqual(
      [[4.0, 51.9], [4.1, 51.9], [4.1, 52.0], [4.0, 52.0], [4.0, 51.9]]);
  });

  it('writes an empty collection for a non-georeferenced result', async () => {
    const r = response();
    r.visual_evidence.geospatial = null;
    exportGeoJSON(r);
    expect(JSON.parse(await blobs[0].text).features).toEqual([]);
  });
});

describe('exportReportJSON', () => {
  it('includes the answer, evidence and source images without previews', async () => {
    exportReportJSON(response(), [image({ previewUrl: 'data:image/png;base64,AAAA', date: '2024-06-01' })]);
    const j = JSON.parse(await blobs[0].text);
    expect(j.task).toBe('detection');
    expect(j.visual_evidence.image_size).toEqual([1000, 800]);
    expect(j.source_imagery).toEqual([{ name: 'port.tif', modality: 'optical', date: '2024-06-01' }]);
    expect(JSON.stringify(j)).not.toContain('base64,AAAA');
  });
});

describe('exportMissionPDF', () => {
  function capture(r: QueryResponse, imgs: QueryImage[], ts?: string) {
    let html = '';
    const win = { document: { write: (s: string) => { html += s; }, close: vi.fn() }, focus: vi.fn(), print: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(win as unknown as Window);
    vi.useFakeTimers();
    exportMissionPDF(r, imgs, ts);
    vi.runAllTimers();
    vi.useRealTimers();
    return new DOMParser().parseFromString(html, 'text/html');
  }

  it('escapes every model- and user-controlled field', () => {
    const r = response({ answer: `**${XSS}**\n- ${XSS}`, task: XSS as QueryResponse['task'] });
    r.visual_evidence.geospatial!.crs = XSS;
    r.execution_summary.tool_used = XSS;
    r.execution_summary.parameters = { band_resolution_tier: XSS };
    const doc = capture(r, [image({ name: XSS, modality: XSS as 'optical', date: XSS, previewUrl: 'data:image/png;base64,AAAA' })], XSS);
    // The only script is the report's own print trigger
    const scripts = [...doc.querySelectorAll('script')];
    expect(scripts).toHaveLength(1);
    expect(scripts[0].textContent?.replace(/\s+/g, ' ').trim())
      .toBe('window.onload = function() { setTimeout(function() { window.print(); }, 500); };');
    const imgs = [...doc.querySelectorAll('img')];
    expect(imgs.map((i) => i.getAttribute('src'))).toEqual(['data:image/png;base64,AAAA']);
    expect([...doc.querySelectorAll('*')].some((el) => [...el.attributes].some((a) => a.name.startsWith('on')))).toBe(false);
    expect(doc.body.textContent).toContain('<script>alert(2)</script>');
  });

  it('never embeds a non-renderable or javascript: image source', () => {
    const doc = capture(response(), [
      image({ previewUrl: 'javascript:alert(1)', url_or_base64: 'data:text/html,<script>alert(1)</script>' }),
      image({ id: 'b', previewUrl: undefined, url_or_base64: 'data:image/tiff;base64,SUkqAA==' }),
    ]);
    expect(doc.querySelectorAll('img')).toHaveLength(0);
  });

  it('lists each detected box and prints', () => {
    const doc = capture(response(), [image()]);
    expect(doc.body.textContent).toContain('(2 Features)');
    expect(doc.body.textContent).toContain('[10, 20, 110, 220]');
  });
});
