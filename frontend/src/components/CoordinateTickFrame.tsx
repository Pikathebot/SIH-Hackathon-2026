import React, { useState, useRef } from 'react';
import { VisualEvidence } from '../types/contract';
import { Crosshair, Layers, Maximize2 } from 'lucide-react';
import { isBrowserRenderable } from '../services/api';

interface CoordinateTickFrameProps {
  imageUrl?: string;
  altText?: string;
  visualEvidence?: VisualEvidence;
  modality?: string;
  date?: string;
  caption?: string;
}

/** Ground extent of a WGS84 bounding box, in km (equirectangular approximation). */
function extentKm([minLon, minLat, maxLon, maxLat]: [number, number, number, number]) {
  const midLat = ((minLat + maxLat) / 2) * (Math.PI / 180);
  return {
    w: Math.abs(maxLon - minLon) * 111.32 * Math.cos(midLat),
    h: Math.abs(maxLat - minLat) * 110.57,
  };
}

const fmtKm = (km: number) => (km >= 10 ? km.toFixed(0) : km >= 1 ? km.toFixed(1) : km.toFixed(2));

export const CoordinateTickFrame: React.FC<CoordinateTickFrameProps> = ({
  imageUrl,
  altText = 'Satellite Viewport',
  visualEvidence,
  modality,
  date,
  caption,
}) => {
  const imageBoxRef = useRef<HTMLDivElement>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [showBoxes, setShowBoxes] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [cursor, setCursor] = useState({ x: 0, y: 0, fx: 0.5, fy: 0.5 });

  const bounds = visualEvidence?.geospatial?.image_bounds ?? null;
  const hasBoxes = visualEvidence?.type === 'bbox' && !!visualEvidence.boxes && visualEvidence.boxes.length > 0;
  const maskSrc = visualEvidence?.type === 'mask'
    ? (visualEvidence.overlay_base64 || visualEvidence.mask_base64)
    : null;

  const rawImage = imageUrl && isBrowserRenderable(imageUrl) ? imageUrl : undefined;
  const displayImage = maskSrc
    ? (maskSrc.startsWith('data:') ? maskSrc : `data:image/png;base64,${maskSrc}`)
    : rawImage;

  // Boxes are pixel coordinates in the grid the server names (API v2.4.0 image_size);
  // older responses fall back to the displayed image's own size.
  const boxSpace = visualEvidence?.image_size
    ? { w: visualEvidence.image_size[0], h: visualEvidence.image_size[1] }
    : natural;
  // The frame takes the image's aspect ratio so nothing is cropped and overlays line up.
  const ratio = natural ? natural.w / natural.h : boxSpace ? boxSpace.w / boxSpace.h : 16 / 9;

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = imageBoxRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const y = Math.max(0, Math.min(e.clientY - rect.top, rect.height));
    setCursor({ x, y, fx: x / rect.width, fy: y / rect.height });
  };

  // Hover read-out: real WGS84 coordinates when the image is georeferenced, pixels otherwise.
  let readout: string;
  if (bounds) {
    const [minLon, minLat, maxLon, maxLat] = bounds;
    const lon = minLon + cursor.fx * (maxLon - minLon);
    const lat = maxLat - cursor.fy * (maxLat - minLat);
    readout = `Lat ${lat.toFixed(5)}°  |  Lon ${lon.toFixed(5)}°`;
  } else {
    const grid = boxSpace ?? natural;
    readout = grid
      ? `x ${Math.round(cursor.fx * grid.w)}  |  y ${Math.round(cursor.fy * grid.h)} px`
      : `${Math.round(cursor.fx * 100)}%, ${Math.round(cursor.fy * 100)}%`;
  }
  const extent = bounds ? extentKm(bounds) : null;
  const imageBoxWidth = imageBoxRef.current?.clientWidth ?? 400;
  const imageBoxHeight = imageBoxRef.current?.clientHeight ?? 300;

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {/* Top Telemetry Tag & Layer Controls */}
      <div className="flex items-center justify-between text-xs text-text-muted px-1 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          {modality && (
            <span className="capitalize px-2 py-0.5 bg-surface-variant border border-grid-hairline text-text-primary rounded-md font-medium text-[11px]">
              {modality === 'sar' ? 'Radar (SAR)' : 'Optical'}
            </span>
          )}
          {date && <span>Date: {date}</span>}
          {caption && <span className="truncate max-w-xs font-medium text-text-primary">{caption}</span>}
        </div>

        {/* Viewport Layer Toggles */}
        <div className="flex items-center gap-2">
          {hasBoxes && (
            <button
              type="button"
              onClick={() => setShowBoxes(!showBoxes)}
              className={`px-2 py-0.5 rounded text-[10px] font-medium border transition-colors cursor-pointer ${
                showBoxes
                  ? 'bg-cyan-detection/10 border-cyan-detection/40 text-cyan-detection'
                  : 'bg-surface-variant/40 border-grid-hairline text-text-muted opacity-60'
              }`}
            >
              Boxes ({visualEvidence?.boxes?.length})
            </button>
          )}

          <button
            type="button"
            onClick={() => setShowGrid(!showGrid)}
            className={`px-2 py-0.5 rounded text-[10px] font-medium border transition-colors cursor-pointer ${
              showGrid
                ? 'bg-primary/10 border-primary/40 text-primary'
                : 'bg-surface-variant/40 border-grid-hairline text-text-muted opacity-60'
            }`}
          >
            Grid
          </button>

          <div
            className={`flex items-center gap-1 font-medium text-[11px] ml-1 ${bounds ? 'text-cyan-detection' : 'text-text-muted'}`}
            title={bounds ? `WGS84 bounds ${bounds.map((v) => v.toFixed(4)).join(', ')}` : 'This image has no georeferencing'}
          >
            <Crosshair className="w-3.5 h-3.5" />
            <span>{bounds ? 'Georeferenced (WGS84)' : 'Pixel coordinates'}</span>
          </div>
        </div>
      </div>

      {/* Frame Container */}
      <div
        className="tick-frame tick-frame-corners relative w-full bg-background overflow-hidden rounded-xl shadow-inner border border-grid-hairline p-1.5"
      >
        {/* L-shaped corner markers */}
        <div className="corner-tr-h" />
        <div className="corner-tr-v" />
        <div className="corner-bl-h" />
        <div className="corner-bl-v" />
        <div className="corner-br-h" />
        <div className="corner-br-v" />

        {/* Top and Left Axis Ruler Ticks */}
        {showGrid && (
          <>
            <div className="absolute top-0 left-0 w-full h-1 ruler-tick-x z-10 pointer-events-none opacity-80" />
            <div className="absolute top-0 left-0 h-full w-1 ruler-tick-y z-10 pointer-events-none opacity-80" />
          </>
        )}

        {/* Image box: exactly the image's aspect ratio, at most 70% of the viewport height */}
        <div
          ref={imageBoxRef}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          onMouseMove={handleMouseMove}
          className="relative mx-auto border border-grid-hairline bg-surface-container overflow-hidden rounded-lg cursor-crosshair"
          style={{ aspectRatio: `${ratio}`, width: `min(100%, calc(70vh * ${ratio}))` }}
        >
          {displayImage ? (
            <>
              <img
                src={displayImage}
                alt={altText}
                onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
                className="absolute inset-0 w-full h-full object-fill select-none"
              />

              {/* Bounding boxes, positioned as fractions of the box pixel grid */}
              {hasBoxes && showBoxes && boxSpace && visualEvidence!.boxes!.map((box, idx) => {
                const [x1, y1, x2, y2] = box;
                const left = (Math.min(x1, x2) / boxSpace.w) * 100;
                const top = (Math.min(y1, y2) / boxSpace.h) * 100;
                const width = (Math.abs(x2 - x1) / boxSpace.w) * 100;
                const height = (Math.abs(y2 - y1) / boxSpace.h) * 100;
                return (
                  <div
                    key={idx}
                    className="absolute pointer-events-none z-20 border-2 border-dashed border-cyan-detection bg-cyan-detection/15 rounded"
                    style={{ left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%` }}
                  >
                    <span
                      className="absolute left-0 whitespace-nowrap bg-surface-panel border border-cyan-detection text-cyan-detection text-[11px] font-semibold px-1.5 py-px rounded"
                      style={top < 6 ? { top: '2px', left: '2px' } : { bottom: 'calc(100% + 2px)' }}
                    >
                      Detection #{idx + 1}
                    </span>
                  </div>
                );
              })}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-text-muted text-xs gap-2">
              <Layers className="w-8 h-8 opacity-40" />
              <span>No Satellite Image Attached</span>
            </div>
          )}

          {/* Interactive Hover Crosshair */}
          {isHovered && displayImage && (
            <>
              <div
                className="absolute top-0 bottom-0 w-px bg-amber-signal/70 pointer-events-none z-30"
                style={{ left: `${cursor.x}px` }}
              />
              <div
                className="absolute left-0 right-0 h-px bg-amber-signal/70 pointer-events-none z-30"
                style={{ top: `${cursor.y}px` }}
              />
              <div
                className="absolute pointer-events-none z-40 bg-surface-panel/95 border border-amber-signal text-amber-signal text-xs font-mono px-2.5 py-1 shadow-lg whitespace-nowrap backdrop-blur-sm rounded-md"
                style={{
                  left: `${Math.max(4, Math.min(cursor.x + 12, imageBoxWidth - 250))}px`,
                  top: `${Math.max(4, Math.min(cursor.y + 12, imageBoxHeight - 32))}px`,
                }}
              >
                {readout}
              </div>
            </>
          )}

          {/* Bottom Right Extent Badge (only when the ground footprint is known) */}
          {extent && (
            <div className="absolute bottom-2 right-2 z-20 bg-surface-panel/90 border border-grid-hairline px-2.5 py-1 text-[11px] text-text-muted flex items-center gap-1.5 rounded-md shadow-sm pointer-events-none">
              <Maximize2 className="w-3 h-3" />
              <span>Extent: {fmtKm(extent.w)} × {fmtKm(extent.h)} km</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
