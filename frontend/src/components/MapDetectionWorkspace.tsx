import React, { useState, useRef } from 'react';
import { submitQuery } from '../services/api';
import { QueryImage, QueryResponse } from '../types/contract';
import { ExecutionSummaryPanel } from './ExecutionSummaryPanel';
import {
  Crosshair,
  MapPin,
  Compass,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Scan,
  ShieldCheck,
  Grid,
  Loader2,
  AlertCircle,
  Upload,
  Sparkles,
  ChevronRight,
} from 'lucide-react';

interface GeoPreset {
  id: string;
  name: string;
  category: string;
  lat: number;
  lon: number;
  defaultQuery: string;
  imageUrl: string;
}

const GEO_PRESETS: GeoPreset[] = [
  {
    id: 'airfield',
    name: 'Military Airbase',
    category: 'Aviation',
    lat: 34.0522,
    lon: -118.2437,
    defaultQuery: 'Detect all military and civilian aircraft on the runway and tarmac',
    imageUrl: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?q=80&w=1200&auto=format&fit=crop',
  },
  {
    id: 'harbor',
    name: 'Shipping Terminal',
    category: 'Maritime',
    lat: 37.7749,
    lon: -122.4194,
    defaultQuery: 'Detect all cargo ships, tankers, and vessels docked or anchored in the harbor',
    imageUrl: 'https://images.unsplash.com/photo-1508873696983-2df5293cb32f?q=80&w=1200&auto=format&fit=crop',
  },
  {
    id: 'reservoir',
    name: 'Coastal Reservoir',
    category: 'Hydrology',
    lat: 25.2048,
    lon: 55.2708,
    defaultQuery: 'Locate and highlight all water reservoirs, lakes, and drainage channels',
    imageUrl: 'https://images.unsplash.com/photo-1524661135-423995f22d0b?q=80&w=1200&auto=format&fit=crop',
  },
  {
    id: 'industrial',
    name: 'Energy & Storage Complex',
    category: 'Infrastructure',
    lat: 29.9792,
    lon: 31.1342,
    defaultQuery: 'Detect all oil storage tanks, chemical silos, and industrial buildings',
    imageUrl: 'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?q=80&w=1200&auto=format&fit=crop',
  },
];

export const MapDetectionWorkspace: React.FC = () => {
  const [selectedPreset, setSelectedPreset] = useState<GeoPreset>(GEO_PRESETS[0]);
  const [customImage, setCustomImage] = useState<string | null>(null);
  const [query, setQuery] = useState(GEO_PRESETS[0].defaultQuery);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [hoveredBox, setHoveredBox] = useState<number | null>(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [showGrid, setShowGrid] = useState(true);
  const [cursorCoords, setCursorCoords] = useState({ lat: GEO_PRESETS[0].lat, lon: GEO_PRESETS[0].lon });

  const mapRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeImageUrl = customImage || selectedPreset.imageUrl;
  const detectedBoxes = result?.visual_evidence?.boxes ?? [];

  const handleSelectPreset = (preset: GeoPreset) => {
    setSelectedPreset(preset);
    setCustomImage(null);
    setQuery(preset.defaultQuery);
    setResult(null);
    setErrorMsg(null);
    setZoomLevel(1);
  };

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setCustomImage(ev.target?.result as string);
      setResult(null);
      setErrorMsg(null);
    };
    reader.readAsDataURL(file);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!mapRef.current) return;
    const rect = mapRef.current.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width;
    const py = (e.clientY - rect.top) / rect.height;
    setCursorCoords({
      lat: parseFloat((selectedPreset.lat + (0.5 - py) * 0.02).toFixed(4)),
      lon: parseFloat((selectedPreset.lon + (px - 0.5) * 0.02).toFixed(4)),
    });
  };

  const handleRunDetection = async () => {
    if (!query.trim() || isLoading) return;
    setIsLoading(true);
    setErrorMsg(null);

    const imagePayload: QueryImage = {
      id: `map_${Date.now()}`,
      modality: 'optical',
      date: new Date().toISOString().split('T')[0],
      url_or_base64: activeImageUrl,
      name: customImage ? 'Custom Upload' : selectedPreset.name,
    };

    try {
      const res = await submitQuery({ query: query.trim(), images: [imagePayload] });
      setResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Detection failed. Please check backend connectivity.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-full overflow-hidden bg-background text-text-primary">

      {/* ── Left Control Panel ── */}
      <div className="w-[340px] flex-shrink-0 flex flex-col h-full border-r border-grid-hairline bg-surface-panel overflow-y-auto">

        {/* Section: Query */}
        <div className="p-4 border-b border-grid-hairline">
          <label className="block text-xs font-semibold text-text-primary mb-2">Detection Query</label>
          <textarea
            rows={2}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe what to find on the map…"
            className="w-full bg-background border border-grid-hairline focus:border-primary focus:ring-1 focus:ring-primary/30 rounded-xl p-3 text-sm text-text-primary placeholder:text-text-muted/50 resize-none outline-none transition-all"
          />
          <button
            type="button"
            onClick={handleRunDetection}
            disabled={!query.trim() || isLoading}
            className="mt-2.5 w-full py-2.5 bg-primary-container text-on-primary-container hover:bg-primary text-sm font-semibold rounded-xl flex items-center justify-center gap-2 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <><Loader2 className="w-4 h-4 animate-spin" /><span>Analyzing…</span></>
            ) : (
              <><Sparkles className="w-4 h-4" /><span>Run Object Detection</span></>
            )}
          </button>
          {errorMsg && (
            <div className="mt-2 flex items-start gap-2 text-xs text-red-delta bg-red-delta/10 border border-red-delta/30 p-3 rounded-lg">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}
        </div>

        {/* Section: Target Sectors */}
        <div className="p-4 border-b border-grid-hairline">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-xs font-semibold text-text-primary">Target Sectors</span>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-1 text-xs text-primary hover:underline font-medium"
            >
              <Upload className="w-3.5 h-3.5" />
              Upload Image
            </button>
            <input type="file" ref={fileInputRef} onChange={handleUpload} accept="image/*" className="hidden" />
          </div>

          <div className="flex flex-col gap-1.5">
            {GEO_PRESETS.map((preset) => {
              const active = selectedPreset.id === preset.id && !customImage;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => handleSelectPreset(preset)}
                  className={`flex items-center gap-3 p-3 rounded-xl border text-left transition-all ${
                    active
                      ? 'bg-surface-container border-primary/60 shadow-sm'
                      : 'bg-surface-container/40 border-grid-hairline hover:bg-surface-variant/40'
                  }`}
                >
                  <MapPin className={`w-4 h-4 flex-shrink-0 ${active ? 'text-primary' : 'text-text-muted/50'}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-text-primary truncate">{preset.name}</p>
                    <p className="text-[11px] text-text-muted font-mono">{preset.lat}° N, {Math.abs(preset.lon)}° W</p>
                  </div>
                  <span className="text-[10px] bg-surface-variant px-2 py-0.5 rounded-full text-text-muted whitespace-nowrap">
                    {preset.category}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Section: Detection Results */}
        {result && (
          <div className="p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-text-primary">
                Results <span className="text-text-muted font-normal">({detectedBoxes.length} objects)</span>
              </span>
              <span className="text-xs font-semibold text-amber-signal bg-amber-signal/10 px-2.5 py-1 rounded-full border border-amber-signal/30 flex items-center gap-1">
                <ShieldCheck className="w-3 h-3" />
                {Math.round(result.confidence * 100)}%
              </span>
            </div>

            <p className="text-sm text-text-primary bg-surface-container/60 p-3 rounded-xl border border-grid-hairline leading-relaxed">
              {result.answer}
            </p>

            {detectedBoxes.length > 0 && (
              <div className="flex flex-col gap-1.5 max-h-44 overflow-y-auto">
                {detectedBoxes.map((box, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onMouseEnter={() => setHoveredBox(idx)}
                    onMouseLeave={() => setHoveredBox(null)}
                    className={`flex items-center justify-between px-3 py-2 text-xs rounded-lg border transition-all text-left ${
                      hoveredBox === idx
                        ? 'bg-cyan-detection/10 border-cyan-detection text-text-primary'
                        : 'bg-surface-container/40 border-grid-hairline text-text-muted hover:bg-surface-variant/30'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-cyan-detection flex-shrink-0" />
                      <span className="font-medium text-text-primary">Object #{idx + 1}</span>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 opacity-50" />
                  </button>
                ))}
              </div>
            )}

            {result.execution_summary && (
              <ExecutionSummaryPanel summary={result.execution_summary} />
            )}
          </div>
        )}
      </div>

      {/* ── Right Map Canvas ── */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">

        {/* Map Toolbar */}
        <div className="h-[44px] px-4 border-b border-grid-hairline bg-surface-panel/90 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <MapPin className="w-3.5 h-3.5 text-primary" />
            <span className="font-medium text-text-primary">
              {customImage ? 'Custom Upload' : selectedPreset.name}
            </span>
            <span className="opacity-40">•</span>
            <span className="font-mono">{cursorCoords.lat}° N, {Math.abs(cursorCoords.lon)}° W</span>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setShowGrid(!showGrid)}
              className={`p-1.5 rounded-lg border text-xs transition-colors ${
                showGrid ? 'bg-primary/10 border-primary text-primary' : 'bg-surface-container border-grid-hairline text-text-muted hover:text-text-primary'
              }`}
              title="Toggle grid"
            >
              <Grid className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={() => setZoomLevel((z) => Math.min(z + 0.25, 2.5))} className="p-1.5 bg-surface-container hover:bg-surface-variant border border-grid-hairline rounded-lg text-text-muted hover:text-text-primary" title="Zoom in">
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={() => setZoomLevel((z) => Math.max(z - 0.25, 0.75))} className="p-1.5 bg-surface-container hover:bg-surface-variant border border-grid-hairline rounded-lg text-text-muted hover:text-text-primary" title="Zoom out">
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={() => setZoomLevel(1)} className="p-1.5 bg-surface-container hover:bg-surface-variant border border-grid-hairline rounded-lg text-text-muted hover:text-text-primary" title="Reset zoom">
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Canvas Stage */}
        <div
          ref={mapRef}
          onMouseMove={handleMouseMove}
          className="flex-1 relative overflow-hidden bg-surface-container flex items-center justify-center cursor-crosshair"
        >
          <div
            style={{ transform: `scale(${zoomLevel})`, transition: 'transform 0.15s ease-out' }}
            className="relative w-full h-full max-w-5xl max-h-[90vh] m-auto p-4 flex items-center justify-center"
          >
            <div className="relative w-full aspect-video rounded-2xl overflow-hidden border border-grid-hairline shadow-2xl bg-black">
              {/* Satellite Image */}
              <img
                src={activeImageUrl}
                alt="Satellite canvas"
                className="w-full h-full object-cover select-none pointer-events-none"
              />

              {/* Grid overlay */}
              {showGrid && (
                <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff0a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff0a_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />
              )}

              {/* Bounding box overlays */}
              {detectedBoxes.length > 0 && (
                <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 1000 1000" preserveAspectRatio="none">
                  {detectedBoxes.map((box, idx) => {
                    const [x1, y1, x2, y2] = box;
                    const mx = Math.min(x1, x2);
                    const my = Math.min(y1, y2);
                    const w = Math.abs(x2 - x1);
                    const h = Math.abs(y2 - y1);
                    const active = hoveredBox === idx;
                    return (
                      <g key={idx}>
                        <rect
                          x={mx} y={my} width={w} height={h}
                          fill={active ? 'rgba(79,214,196,0.25)' : 'rgba(79,214,196,0.12)'}
                          stroke="#4FD6C4"
                          strokeWidth={active ? 3 : 2}
                          strokeDasharray={active ? 'none' : '6 3'}
                          rx="4"
                        />
                        <rect x={mx} y={Math.max(0, my - 22)} width={100} height={18} fill="#121B2E" stroke="#4FD6C4" strokeWidth="1" rx="3" />
                        <text x={mx + 6} y={Math.max(14, my - 8)} fill="#4FD6C4" fontSize="11" fontFamily="monospace" fontWeight="600">
                          #{idx + 1}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              )}

              {/* Coordinate HUD */}
              <div className="absolute bottom-3 left-3 bg-surface-panel/90 backdrop-blur-md border border-grid-hairline px-3 py-1.5 rounded-xl font-mono text-xs text-text-primary flex items-center gap-2 shadow-lg">
                <Compass className="w-3.5 h-3.5 text-primary" />
                <span>{cursorCoords.lat}°</span>
                <span className="opacity-40">|</span>
                <span>{cursorCoords.lon}°</span>
              </div>

              {/* Top-right sensor badge */}
              <div className="absolute top-3 right-3 bg-surface-panel/90 backdrop-blur-md border border-grid-hairline px-3 py-1.5 rounded-xl text-xs flex items-center gap-1.5 shadow-lg">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-sensor animate-pulse" />
                <span className="text-text-primary font-medium">Optical Layer</span>
              </div>

              {/* Crosshair on hover */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-10">
                <Crosshair className="w-8 h-8 text-primary" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
