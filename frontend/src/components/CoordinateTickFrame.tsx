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
  aspectRatio?: 'video' | 'square' | 'auto';
  centerLat?: number;
  centerLon?: number;
}

export const CoordinateTickFrame: React.FC<CoordinateTickFrameProps> = ({
  imageUrl,
  altText = 'Satellite Viewport',
  visualEvidence,
  modality,
  date,
  caption,
  aspectRatio = 'video',
  centerLat = 34.0522,
  centerLon = -118.2437,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [crosshairPos, setCrosshairPos] = useState({ x: 0, y: 0, percentX: 50, percentY: 50 });
  const [currentCoords, setCurrentCoords] = useState({ lat: centerLat, lon: centerLon });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const y = Math.max(0, Math.min(e.clientY - rect.top, rect.height));
    
    const percentX = (x / rect.width) * 100;
    const percentY = (y / rect.height) * 100;

    setCrosshairPos({ x, y, percentX, percentY });

    const deltaLat = ((0.5 - percentY / 100) * 0.05).toFixed(4);
    const deltaLon = (((percentX / 100) - 0.5) * 0.05).toFixed(4);
    setCurrentCoords({
      lat: Number((centerLat + parseFloat(deltaLat)).toFixed(4)),
      lon: Number((centerLon + parseFloat(deltaLon)).toFixed(4)),
    });
  };

  const hasBoxes = visualEvidence?.type === 'bbox' && visualEvidence.boxes && visualEvidence.boxes.length > 0;
  const maskSrc = visualEvidence?.type === 'mask' 
    ? (visualEvidence.overlay_base64 || visualEvidence.mask_base64)
    : null;

  const rawImage = imageUrl && isBrowserRenderable(imageUrl) ? imageUrl : undefined;

  const displayImage = maskSrc 
    ? (maskSrc.startsWith('data:') ? maskSrc : `data:image/png;base64,${maskSrc}`)
    : rawImage;

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {/* Top Telemetry Tag */}
      <div className="flex items-center justify-between text-xs text-text-muted px-1">
        <div className="flex items-center gap-2">
          {modality && (
            <span className="capitalize px-2 py-0.5 bg-surface-variant border border-grid-hairline text-text-primary rounded-md font-medium text-[11px]">
              {modality === 'sar' ? 'Radar (SAR)' : 'Optical'}
            </span>
          )}
          {date && <span>Date: {date}</span>}
          {caption && <span className="truncate max-w-xs font-medium text-text-primary">{caption}</span>}
        </div>
        <div className="flex items-center gap-1.5 text-cyan-detection font-medium text-[11px]">
          <Crosshair className="w-3.5 h-3.5" />
          <span>Calibrated Coordinates</span>
        </div>
      </div>

      {/* Frame Container */}
      <div
        ref={containerRef}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onMouseMove={handleMouseMove}
        className={`tick-frame tick-frame-corners relative w-full ${
          aspectRatio === 'video' ? 'aspect-video' : 'aspect-square min-h-[300px]'
        } bg-background overflow-hidden cursor-crosshair group rounded-xl shadow-inner border border-grid-hairline`}
      >
        {/* L-shaped corner markers */}
        <div className="corner-tr-h" />
        <div className="corner-tr-v" />
        <div className="corner-bl-h" />
        <div className="corner-bl-v" />
        <div className="corner-br-h" />
        <div className="corner-br-v" />

        {/* Top and Left Axis Ruler Ticks */}
        <div className="absolute top-0 left-0 w-full h-1 ruler-tick-x z-10 pointer-events-none opacity-80" />
        <div className="absolute top-0 left-0 h-full w-1 ruler-tick-y z-10 pointer-events-none opacity-80" />

        {/* Image Content */}
        <div className="absolute inset-1.5 border border-grid-hairline bg-surface-container overflow-hidden rounded-lg">
          {displayImage ? (
            <div className="relative w-full h-full">
              <img
                src={displayImage}
                alt={altText}
                className="w-full h-full object-cover select-none"
              />

              {/* Bounding Boxes SVG Layer */}
              {hasBoxes && (
                <svg
                  className="absolute inset-0 w-full h-full pointer-events-none z-15"
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                >
                  {visualEvidence!.boxes!.map((box, idx) => {
                    const [x1, y1, x2, y2] = box;
                    const width = Math.abs(x2 - x1);
                    const height = Math.abs(y2 - y1);
                    const minX = Math.min(x1, x2);
                    const minY = Math.min(y1, y2);

                    return (
                      <g key={idx}>
                        <rect
                          x={minX}
                          y={minY}
                          width={width}
                          height={height}
                          fill="rgba(79, 214, 196, 0.15)"
                          stroke="#4FD6C4"
                          strokeWidth="2.5"
                          strokeDasharray="6 3"
                          rx="4"
                        />
                        <rect
                          x={minX}
                          y={Math.max(0, minY - 26)}
                          width={Math.min(130, width)}
                          height={22}
                          fill="#121B2E"
                          stroke="#4FD6C4"
                          strokeWidth="1"
                          rx="3"
                        />
                        <text
                          x={minX + 8}
                          y={Math.max(15, minY - 10)}
                          fill="#4FD6C4"
                          fontSize="12"
                          fontFamily="Space Grotesk"
                          fontWeight="600"
                        >
                          Detection #{idx + 1}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-text-muted text-xs gap-2">
              <Layers className="w-8 h-8 opacity-40" />
              <span>No Satellite Image Attached</span>
            </div>
          )}

          {/* Interactive Hover Crosshair */}
          {isHovered && (
            <>
              {/* Vertical Crosshair Line */}
              <div
                className="absolute top-0 bottom-0 w-px bg-amber-signal/70 pointer-events-none z-30"
                style={{ left: `${crosshairPos.x}px` }}
              />
              {/* Horizontal Crosshair Line */}
              <div
                className="absolute left-0 right-0 h-px bg-amber-signal/70 pointer-events-none z-30"
                style={{ top: `${crosshairPos.y}px` }}
              />

              {/* Floating Coordinate Tag */}
              <div
                className="absolute pointer-events-none z-40 bg-surface-panel/95 border border-amber-signal text-amber-signal text-xs font-mono px-2.5 py-1 shadow-lg flex items-center gap-2 backdrop-blur-sm rounded-md"
                style={{
                  left: `${Math.min(crosshairPos.x + 12, (containerRef.current?.clientWidth || 400) - 170)}px`,
                  top: `${Math.min(crosshairPos.y + 12, (containerRef.current?.clientHeight || 300) - 45)}px`,
                }}
              >
                <span>Lat: {currentCoords.lat}°</span>
                <span className="opacity-40">|</span>
                <span>Lon: {currentCoords.lon}°</span>
              </div>
            </>
          )}
        </div>

        {/* Bottom Right Resolution Badge */}
        <div className="absolute bottom-3 right-3 z-20 bg-surface-panel/90 border border-grid-hairline px-2.5 py-1 text-[11px] text-text-muted flex items-center gap-1.5 rounded-md shadow-sm">
          <Maximize2 className="w-3 h-3" />
          <span>Resolution: 0.5m/pixel</span>
        </div>
      </div>
    </div>
  );
};
