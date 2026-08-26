import React from 'react';
import { X, ZoomIn, ZoomOut, RotateCcw, Calendar, Layers, Download } from 'lucide-react';

interface ImageLightboxModalProps {
  isOpen: boolean;
  onClose: () => void;
  imageUrl: string;
  title?: string;
  modality?: string;
  date?: string;
}

export const ImageLightboxModal: React.FC<ImageLightboxModalProps> = ({
  isOpen,
  onClose,
  imageUrl,
  title = 'Satellite Imagery View',
  modality,
  date,
}) => {
  const [zoom, setZoom] = React.useState(1);

  if (!isOpen || !imageUrl) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-150 select-none"
      onClick={onClose}
    >
      <div
        className="relative max-w-5xl w-full max-h-[90vh] bg-surface-panel border border-grid-hairline rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-3.5 border-b border-grid-hairline bg-surface-container/80">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-xl text-primary">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-headline font-semibold text-sm text-text-primary">
                {title}
              </h3>
              <div className="flex items-center gap-2 text-xs text-text-muted mt-0.5">
                {modality && (
                  <span className="capitalize text-amber-signal font-medium">
                    {modality === 'sar' ? 'Radar (SAR)' : 'Optical'}
                  </span>
                )}
                {date && (
                  <span className="flex items-center gap-1">
                    <span>•</span>
                    <Calendar className="w-3 h-3 text-text-muted" />
                    <span>{date}</span>
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Controls & Close */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(z + 0.25, 3))}
              className="p-2 bg-surface-container hover:bg-surface-variant border border-grid-hairline rounded-lg text-text-muted hover:text-text-primary transition-colors"
              title="Zoom in"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.max(z - 0.25, 0.5))}
              className="p-2 bg-surface-container hover:bg-surface-variant border border-grid-hairline rounded-lg text-text-muted hover:text-text-primary transition-colors"
              title="Zoom out"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setZoom(1)}
              className="p-2 bg-surface-container hover:bg-surface-variant border border-grid-hairline rounded-lg text-text-muted hover:text-text-primary transition-colors"
              title="Reset zoom"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <div className="h-4 w-px bg-grid-hairline mx-1" />
            <button
              type="button"
              onClick={onClose}
              className="p-2 text-text-muted hover:text-text-primary hover:bg-surface-variant rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Image Stage */}
        <div className="flex-1 overflow-auto p-4 flex items-center justify-center bg-background/95 min-h-[350px]">
          <div
            style={{
              transform: `scale(${zoom})`,
              transition: 'transform 0.15s ease-out',
            }}
            className="flex items-center justify-center"
          >
            <img
              src={imageUrl}
              alt={title}
              className="max-h-[70vh] w-auto max-w-full rounded-xl object-contain shadow-xl border border-grid-hairline"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
