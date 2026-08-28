import React, { useState, useRef, useCallback, useEffect } from 'react';
import { 
  ChevronsLeftRight, 
  Columns, 
  Layers, 
  Sliders, 
  Maximize2, 
  Minimize2
} from 'lucide-react';

interface DualImageSplitSliderProps {
  primaryUrl: string;
  secondaryUrl: string;
  primaryLabel?: string;
  secondaryLabel?: string;
  overlayUrl?: string;
  task?: string;
  aspectRatio?: 'video' | 'square' | 'auto';
}

type ViewMode = 'split' | 'side-by-side' | 'blend';

export const DualImageSplitSlider: React.FC<DualImageSplitSliderProps> = ({
  primaryUrl,
  secondaryUrl,
  primaryLabel = 'Primary Capture (T1)',
  secondaryLabel = 'Comparison Capture (T2)',
  overlayUrl,
  aspectRatio = 'video',
}) => {
  const [viewMode, setViewMode] = useState<ViewMode>('split');
  const [sliderPosition, setSliderPosition] = useState<number>(50); // percentage 0-100
  const [blendOpacity, setBlendOpacity] = useState<number>(50); // percentage 0-100
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  const containerRef = useRef<HTMLDivElement>(null);

  const handleMove = useCallback(
    (clientX: number) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = clientX - rect.left;
      const percent = Math.min(Math.max((x / rect.width) * 100, 0), 100);
      setSliderPosition(percent);
    },
    []
  );

  const handleMouseDown = () => setIsDragging(true);
  const handleTouchStart = () => setIsDragging(true);

  useEffect(() => {
    const handleMouseUp = () => setIsDragging(false);
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) handleMove(e.clientX);
    };
    const handleTouchMove = (e: TouchEvent) => {
      if (isDragging && e.touches.length > 0) handleMove(e.touches[0].clientX);
    };

    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      window.addEventListener('touchmove', handleTouchMove);
      window.addEventListener('touchend', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleMouseUp);
    };
  }, [isDragging, handleMove]);

  const aspectClass =
    aspectRatio === 'square'
      ? 'aspect-square'
      : aspectRatio === 'video'
      ? 'aspect-video'
      : 'aspect-[16/10]';

  return (
    <div
      className={`flex flex-col gap-2 w-full transition-all ${
        isFullscreen
          ? 'fixed inset-0 z-50 bg-background/95 backdrop-blur-md p-6 overflow-y-auto flex items-center justify-center'
          : 'relative'
      }`}
    >
      <div className={`${isFullscreen ? 'max-w-6xl w-full flex flex-col gap-3' : 'w-full'}`}>
        {/* Controls Toolbar */}
        <div className="flex items-center justify-between px-2 py-1 bg-surface-container/60 border border-grid-hairline rounded-xl text-xs">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setViewMode('split')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg font-medium transition-all ${
                viewMode === 'split'
                  ? 'bg-primary-container text-on-primary-container shadow-xs'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Swipe Split Slider</span>
            </button>

            <button
              type="button"
              onClick={() => setViewMode('side-by-side')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg font-medium transition-all ${
                viewMode === 'side-by-side'
                  ? 'bg-primary-container text-on-primary-container shadow-xs'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              <Columns className="w-3.5 h-3.5" />
              <span>Side-by-Side</span>
            </button>

            <button
              type="button"
              onClick={() => setViewMode('blend')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg font-medium transition-all ${
                viewMode === 'blend'
                  ? 'bg-primary-container text-on-primary-container shadow-xs'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Opacity Blend</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            {viewMode === 'blend' && (
              <div className="flex items-center gap-2 px-2 py-0.5 bg-surface-variant rounded-md text-[11px]">
                <span className="text-text-muted">Blend:</span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={blendOpacity}
                  onChange={(e) => setBlendOpacity(Number(e.target.value))}
                  className="w-20 h-1 bg-surface-container rounded-lg appearance-none cursor-pointer accent-primary"
                />
                <span className="font-mono text-primary">{blendOpacity}%</span>
              </div>
            )}

            <button
              type="button"
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-1 text-text-muted hover:text-text-primary hover:bg-surface-variant rounded-md transition-colors"
              title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen Inspection'}
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Viewport Canvas */}
        {viewMode === 'side-by-side' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Primary */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-[11px] text-text-muted px-1">
                <span className="font-semibold text-text-primary">{primaryLabel}</span>
                <span className="bg-surface-variant px-1.5 py-0.2 rounded text-[10px] uppercase font-mono">T1</span>
              </div>
              <div className={`w-full ${aspectClass} rounded-xl overflow-hidden border border-grid-hairline bg-black relative`}>
                <img src={primaryUrl} alt={primaryLabel} className="w-full h-full object-cover" />
              </div>
            </div>

            {/* Secondary */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-[11px] text-text-muted px-1">
                <span className="font-semibold text-text-primary">{secondaryLabel}</span>
                <span className="bg-surface-variant px-1.5 py-0.2 rounded text-[10px] uppercase font-mono">T2</span>
              </div>
              <div className={`w-full ${aspectClass} rounded-xl overflow-hidden border border-grid-hairline bg-black relative`}>
                <img src={secondaryUrl} alt={secondaryLabel} className="w-full h-full object-cover" />
              </div>
            </div>
          </div>
        ) : viewMode === 'blend' ? (
          /* Opacity Blend View */
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-[11px] text-text-muted px-1">
              <span>{primaryLabel} (Base)</span>
              <span className="text-amber-signal font-semibold">{secondaryLabel} (Overlay @ {blendOpacity}%)</span>
            </div>
            <div className={`w-full ${aspectClass} rounded-xl overflow-hidden border border-grid-hairline bg-black relative`}>
              <img src={primaryUrl} alt="Base" className="absolute inset-0 w-full h-full object-cover" />
              <img
                src={overlayUrl || secondaryUrl}
                alt="Overlay"
                style={{ opacity: blendOpacity / 100 }}
                className="absolute inset-0 w-full h-full object-cover transition-opacity duration-75"
              />
            </div>
          </div>
        ) : (
          /* Swipe Split Slider View */
          <div className="flex flex-col gap-1.5">
            <div
              ref={containerRef}
              onClick={(e) => handleMove(e.clientX)}
              className={`w-full ${aspectClass} rounded-xl overflow-hidden border border-grid-hairline bg-black relative select-none cursor-ew-resize group shadow-inner`}
            >
              {/* Secondary (Right Image - Full Canvas) */}
              <img
                src={secondaryUrl}
                alt={secondaryLabel}
                className="absolute inset-0 w-full h-full object-cover pointer-events-none"
              />

              {/* Primary (Left Image - Clipped at sliderPosition %) */}
              <div
                style={{ width: `${sliderPosition}%` }}
                className="absolute inset-y-0 left-0 overflow-hidden pointer-events-none border-r-2 border-primary shadow-xl"
              >
                <div
                  style={{
                    width: containerRef.current ? `${containerRef.current.clientWidth}px` : '100%',
                    height: '100%',
                  }}
                  className="relative max-w-none h-full"
                >
                  <img
                    src={primaryUrl}
                    alt={primaryLabel}
                    className="absolute inset-0 w-full h-full object-cover pointer-events-none"
                  />
                </div>
              </div>

              {/* Draggable Divider Handle */}
              <div
                style={{ left: `${sliderPosition}%` }}
                onMouseDown={handleMouseDown}
                onTouchStart={handleTouchStart}
                className="absolute inset-y-0 -ml-3.5 w-7 flex items-center justify-center cursor-ew-resize z-20 group"
              >
                <div className="w-7 h-7 rounded-full bg-primary text-on-primary shadow-lg border-2 border-surface-panel flex items-center justify-center transition-transform group-hover:scale-110">
                  <ChevronsLeftRight className="w-4 h-4" />
                </div>
              </div>

              {/* Floating Labels on Canvas */}
              <div className="absolute top-3 left-3 bg-black/75 backdrop-blur-md px-2.5 py-1 rounded-lg text-[10px] font-semibold text-text-primary border border-grid-hairline flex items-center gap-1.5 pointer-events-none z-10 shadow-md">
                <span className="w-2 h-2 rounded-full bg-primary" />
                <span className="truncate max-w-[140px]">{primaryLabel}</span>
              </div>

              <div className="absolute top-3 right-3 bg-black/75 backdrop-blur-md px-2.5 py-1 rounded-lg text-[10px] font-semibold text-text-primary border border-grid-hairline flex items-center gap-1.5 pointer-events-none z-10 shadow-md">
                <span className="w-2 h-2 rounded-full bg-amber-signal" />
                <span className="truncate max-w-[140px]">{secondaryLabel}</span>
              </div>

              {/* Slider Position Indicator */}
              <div className="absolute bottom-3 left-1/2 -translate-x-1/2 bg-black/70 backdrop-blur-xs px-2 py-0.5 rounded-full text-[10px] font-mono text-text-muted pointer-events-none">
                Split: {Math.round(sliderPosition)}%
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
