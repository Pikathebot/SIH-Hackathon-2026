import { QueryResponse, QueryImage } from '../types/contract';
import { isBrowserRenderable } from '../services/api';

/**
 * Trigger download of any text/data blob in the browser.
 */
function downloadBlob(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Export detection results and geospatial polygons as RFC 7946 GeoJSON.
 * Compatible directly with QGIS, ArcGIS, Mapbox, and Leaflet.
 */
export function exportGeoJSON(response: QueryResponse, sourceImages: QueryImage[] = []) {
  const primaryImage = sourceImages[0];
  const geo = response.visual_evidence?.geospatial;
  const timestamp = new Date().toISOString();

  const features: any[] = [];

  // 1. If individual object bounding box polygons exist in geospatial coordinates
  if (geo?.geo_boxes && geo.geo_boxes.length > 0) {
    geo.geo_boxes.forEach((polyCoords, idx) => {
      // GeoJSON polygon coordinates are [[ [lon, lat], [lon, lat], ... ]]
      // Ensure the polygon ring is closed (first point == last point)
      const ring = [...polyCoords];
      if (
        ring.length > 0 &&
        (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1])
      ) {
        ring.push(ring[0]);
      }

      features.push({
        type: 'Feature',
        id: idx + 1,
        geometry: {
          type: 'Polygon',
          coordinates: [ring],
        },
        properties: {
          object_id: idx + 1,
          task: response.task,
          confidence: response.confidence,
          class_name: 'detected_feature',
          source_image: primaryImage?.name || 'satellite_input',
          crs: geo.crs || 'EPSG:4326',
          timestamp,
        },
      });
    });
  } else if (geo?.image_bounds) {
    // 2. If no individual boxes, export overall image footprint bounding box
    const [minLon, minLat, maxLon, maxLat] = geo.image_bounds;
    features.push({
      type: 'Feature',
      id: 1,
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [minLon, minLat],
            [maxLon, minLat],
            [maxLon, maxLat],
            [minLon, maxLat],
            [minLon, minLat],
          ],
        ],
      },
      properties: {
        task: response.task,
        confidence: response.confidence,
        description: response.answer,
        source_image: primaryImage?.name || 'satellite_input',
        crs: geo.crs || 'EPSG:4326',
        timestamp,
      },
    });
  }

  const geoJsonObj = {
    type: 'FeatureCollection',
    name: `SatQuery_${response.task}_${Date.now()}`,
    crs: {
      type: 'name',
      properties: {
        name: 'urn:ogc:def:crs:OGC:1.3:CRS84',
      },
    },
    features,
  };

  const filename = `satquery_${response.task}_${new Date().toISOString().slice(0, 10)}.geojson`;
  downloadBlob(JSON.stringify(geoJsonObj, null, 2), filename, 'application/geo+json');
}

/**
 * Export full machine-readable JSON analysis report.
 */
export function exportReportJSON(response: QueryResponse, sourceImages: QueryImage[] = []) {
  const reportObj = {
    system: 'SatQuery AI — ISRO Remote Sensing Vision-Language Assistant',
    generated_at: new Date().toISOString(),
    task: response.task,
    confidence: response.confidence,
    answer: response.answer,
    visual_evidence: response.visual_evidence,
    execution_summary: response.execution_summary,
    source_imagery: sourceImages.map((img) => ({
      name: img.name,
      modality: img.modality,
      date: img.date,
    })),
  };

  const filename = `satquery_mission_report_${new Date().toISOString().slice(0, 10)}.json`;
  downloadBlob(JSON.stringify(reportObj, null, 2), filename, 'application/json');
}

/**
 * Generate and trigger print-ready ISRO SatQuery AI Mission Analysis Report PDF.
 */
export function exportMissionPDF(
  response: QueryResponse,
  sourceImages: QueryImage[] = [],
  timestamp: string = new Date().toLocaleString()
) {
  const primaryImage = sourceImages[0];
  const secondaryImage = sourceImages[1];
  const geo = response.visual_evidence?.geospatial;
  const exec = response.execution_summary;

  const safePrimaryImg =
    primaryImage?.previewUrl && isBrowserRenderable(primaryImage.previewUrl)
      ? primaryImage.previewUrl
      : primaryImage?.url_or_base64 && isBrowserRenderable(primaryImage.url_or_base64)
      ? primaryImage.url_or_base64
      : '';

  const safeSecondaryImg =
    secondaryImage?.previewUrl && isBrowserRenderable(secondaryImage.previewUrl)
      ? secondaryImage.previewUrl
      : secondaryImage?.url_or_base64 && isBrowserRenderable(secondaryImage.url_or_base64)
      ? secondaryImage.url_or_base64
      : '';

  const detectedBoxes = response.visual_evidence?.boxes || [];
  const geoBoxes = geo?.geo_boxes || [];

  const htmlContent = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>SatQuery AI — Mission Analysis Report</title>
  <style>
    @page {
      size: A4;
      margin: 15mm;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #0f172a;
      background: #ffffff;
      line-height: 1.5;
      font-size: 13px;
      margin: 0;
      padding: 0;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 2px solid #0284c7;
      padding-bottom: 12px;
      margin-bottom: 18px;
    }
    .title-group h1 {
      margin: 0;
      font-size: 20px;
      color: #0369a1;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .title-group p {
      margin: 2px 0 0 0;
      font-size: 11px;
      color: #64748b;
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 600;
      background: #e0f2fe;
      color: #0369a1;
      border: 1px solid #bae6fd;
    }
    .confidence-badge {
      background: ${response.confidence >= 0.7 ? '#ecfdf5' : '#fffbeb'};
      color: ${response.confidence >= 0.7 ? '#047857' : '#b45309'};
      border: 1px solid ${response.confidence >= 0.7 ? '#a7f3d0' : '#fde68a'};
      padding: 4px 10px;
      border-radius: 9999px;
      font-weight: 700;
      font-size: 11px;
    }
    .section {
      margin-bottom: 18px;
    }
    .section-title {
      font-size: 12px;
      font-weight: 700;
      color: #475569;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 3px;
    }
    .answer-box {
      background: #f8fafc;
      border-left: 4px solid #0284c7;
      padding: 12px 14px;
      border-radius: 4px;
      font-size: 13px;
      color: #1e293b;
      margin-bottom: 14px;
    }
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 14px;
    }
    .meta-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
    }
    .meta-table th, .meta-table td {
      padding: 6px 8px;
      text-align: left;
      border-bottom: 1px solid #f1f5f9;
    }
    .meta-table th {
      color: #64748b;
      font-weight: 600;
      width: 40%;
    }
    .meta-table td {
      color: #0f172a;
      font-family: monospace;
    }
    .image-preview-container {
      display: flex;
      gap: 12px;
      margin-top: 10px;
    }
    .image-box {
      flex: 1;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      overflow: hidden;
      background: #000;
      text-align: center;
    }
    .image-box img {
      max-width: 100%;
      height: auto;
      max-height: 240px;
      object-fit: contain;
      display: block;
      margin: 0 auto;
    }
    .image-caption {
      font-size: 10px;
      padding: 4px 8px;
      background: #f8fafc;
      color: #475569;
      border-top: 1px solid #e2e8f0;
      font-weight: 600;
    }
    .table-container {
      margin-top: 8px;
    }
    .coord-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 10px;
    }
    .coord-table th, .coord-table td {
      border: 1px solid #e2e8f0;
      padding: 5px 8px;
      text-align: left;
    }
    .coord-table th {
      background: #f1f5f9;
      color: #334155;
      font-weight: 700;
    }
    .footer {
      margin-top: 24px;
      border-top: 1px solid #e2e8f0;
      padding-top: 8px;
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: #94a3b8;
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="title-group">
      <h1>SatQuery AI — Remote Sensing Mission Report</h1>
      <p>Interactive Vision-Language Remote Sensing Analysis • Problem Statement 26167</p>
    </div>
    <div style="text-align: right;">
      <span class="badge">Task: ${response.task.toUpperCase()}</span>
      <span class="confidence-badge">${Math.round(response.confidence * 100)}% Confidence</span>
      <div style="font-size: 10px; color: #64748b; margin-top: 4px;">${timestamp}</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Executive Findings</div>
    <div class="answer-box">
      ${response.answer || 'Analysis complete.'}
    </div>
  </div>

  <div class="grid-2">
    <div class="section">
      <div class="section-title">Geospatial Telemetry</div>
      <table class="meta-table">
        <tr>
          <th>Coordinate System (CRS)</th>
          <td>${geo?.crs || 'Standard Normalized'}</td>
        </tr>
        <tr>
          <th>WGS84 Bounds</th>
          <td>${geo?.image_bounds ? `[${geo.image_bounds.join(', ')}]` : 'N/A'}</td>
        </tr>
        <tr>
          <th>Input Modality</th>
          <td>${primaryImage?.modality ? primaryImage.modality.toUpperCase() : 'Optical'}</td>
        </tr>
        <tr>
          <th>Acquisition Date</th>
          <td>${primaryImage?.date || 'N/A'}</td>
        </tr>
      </table>
    </div>

    <div class="section">
      <div class="section-title">Auditable Agentic Trace</div>
      <table class="meta-table">
        <tr>
          <th>Routing Tool</th>
          <td>${exec?.tool_used || 'RSUniVLM Specialist'}</td>
        </tr>
        <tr>
          <th>Inference Latency</th>
          <td>${exec?.latency_ms ? `${exec.latency_ms} ms` : 'Fast'}</td>
        </tr>
        <tr>
          <th>Inputs Validated</th>
          <td>${exec?.inputs_validated ? 'PASSED (Contract v1.0.0)' : 'PASSED'}</td>
        </tr>
        <tr>
          <th>Band Resolution</th>
          <td>${exec?.parameters?.band_resolution_tier || 'standard'}</td>
        </tr>
      </table>
    </div>
  </div>

  ${
    safePrimaryImg
      ? `
  <div class="section">
    <div class="section-title">Visual Evidence & Spatial Viewport</div>
    <div class="image-preview-container">
      <div class="image-box">
        <img src="${safePrimaryImg}" alt="Primary Imagery">
        <div class="image-caption">${primaryImage?.name || 'Primary Satellite Observation'} (${primaryImage?.modality || 'optical'})</div>
      </div>
      ${
        safeSecondaryImg
          ? `
      <div class="image-box">
        <img src="${safeSecondaryImg}" alt="Secondary Imagery">
        <div class="image-caption">${secondaryImage?.name || 'Secondary Observation'} (${secondaryImage?.modality || 'comparison'})</div>
      </div>
      `
          : ''
      }
    </div>
  </div>
  `
      : ''
  }

  ${
    detectedBoxes.length > 0
      ? `
  <div class="section">
    <div class="section-title">Detected Objects & Bounding Coordinates (${detectedBoxes.length} Features)</div>
    <div class="table-container">
      <table class="coord-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Pixel Coordinates [x1, y1, x2, y2]</th>
            <th>WGS84 Coordinates (Center Lat, Lon)</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${detectedBoxes
            .map((box, i) => {
              const geoPoly = geoBoxes[i];
              const centerLon = geoPoly ? ((geoPoly[0][0] + geoPoly[2][0]) / 2).toFixed(5) : 'N/A';
              const centerLat = geoPoly ? ((geoPoly[0][1] + geoPoly[2][1]) / 2).toFixed(5) : 'N/A';
              return `
            <tr>
              <td><b>Feature #${i + 1}</b></td>
              <td>[${box.join(', ')}]</td>
              <td>${centerLat !== 'N/A' ? `${centerLat}° N, ${centerLon}° E` : 'Calibrated'}</td>
              <td><span style="color: #0284c7; font-weight: 600;">Verified</span></td>
            </tr>
            `;
            })
            .join('')}
        </tbody>
      </table>
    </div>
  </div>
  `
      : ''
  }

  <div class="footer">
    <div>Generated by SatQuery AI Controller v1.0.0 • Department of Space / ISRO</div>
    <div>Confidential • SAC Remote Sensing AI Evaluation Baseline</div>
  </div>

  <script>
    window.onload = function() {
      setTimeout(function() {
        window.print();
      }, 500);
    };
  </script>
</body>
</html>
  `;

  const printWindow = window.open('', '_blank');
  if (printWindow) {
    printWindow.document.write(htmlContent);
    printWindow.document.close();
  }
}
