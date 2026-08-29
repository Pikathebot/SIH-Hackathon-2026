import React, { useState, useRef } from 'react';
import { QueryImage, Modality } from '../types/contract';
import { isBrowserRenderable, uploadLargeImage } from '../services/api';
import { 
  Send, 
  Upload, 
  Trash2, 
  Calendar, 
  Layers, 
  AlertCircle, 
  Image as ImageIcon, 
  Sparkles,
  ChevronDown,
  ChevronUp,
  X,
  Eye,
  Loader2
} from 'lucide-react';

interface QueryComposerProps {
  onExecute: (query: string, images: QueryImage[]) => void;
  isLoading: boolean;
  onOpenPresets?: () => void;
  onPreviewImage?: (imageUrl: string, title?: string, modality?: string, date?: string) => void;
  initialQuery?: string;
  initialImages?: QueryImage[];
}

export const QueryComposer: React.FC<QueryComposerProps> = ({
  onExecute,
  isLoading,
  onOpenPresets,
  onPreviewImage,
  initialQuery = '',
  initialImages = [],
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [images, setImages] = useState<QueryImage[]>(initialImages);
  const [showImageDrawer, setShowImageDrawer] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync when initialQuery/initialImages changes
  React.useEffect(() => {
    if (initialQuery) setQuery(initialQuery);
    if (initialImages && initialImages.length > 0) {
      setImages(initialImages);
      setShowImageDrawer(false);
    }
  }, [initialQuery, initialImages]);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const remainingSlots = 2 - images.length;
    if (remainingSlots <= 0) {
      alert('A maximum of 2 satellite images can be attached per analysis.');
      return;
    }

    const filesToProcess = Array.from(files).slice(0, remainingSlots);

    filesToProcess.forEach(async (file, index) => {
      const imgId = `img_${Date.now()}_${index + 1}`;
      const fileSizeMB = (file.size / (1024 * 1024)).toFixed(1);

      // Create placeholder image slot immediately in drawer
      const newImage: QueryImage = {
        id: imgId,
        modality: 'optical',
        date: new Date().toISOString().split('T')[0],
        url_or_base64: '',
        previewUrl: undefined,
        name: `${file.name} (${fileSizeMB} MB)`,
      };
      setImages((prev) => [...prev, newImage].slice(0, 2));
      setShowImageDrawer(true);
      setUploadProgress((prev) => ({ ...prev, [imgId]: 0 }));

      try {
        const uploadRes = await uploadLargeImage(file, (pct) => {
          setUploadProgress((prev) => ({ ...prev, [imgId]: pct }));
        });

        // Once uploaded, set asset URL and server-generated preview
        setImages((prev) =>
          prev.map((img) =>
            img.id === imgId
              ? {
                  ...img,
                  url_or_base64: uploadRes.url,
                  previewUrl: uploadRes.preview_base64,
                  name: `${uploadRes.filename} (${fileSizeMB} MB)`,
                }
              : img
          )
        );
      } catch (err: any) {
        alert(`Failed to upload "${file.name}": ${err?.message || 'Upload failed'}`);
        setImages((prev) => prev.filter((img) => img.id !== imgId));
      } finally {
        setUploadProgress((prev) => {
          const next = { ...prev };
          delete next[imgId];
          return next;
        });
      }
    });

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleRemoveImage = (id: string) => {
    setImages((prev) => {
      const updated = prev.filter((img) => img.id !== id);
      if (updated.length === 0) setShowImageDrawer(false);
      return updated;
    });
  };

  const handleModalityChange = (id: string, modality: Modality) => {
    setImages((prev) =>
      prev.map((img) => (img.id === id ? { ...img, modality } : img))
    );
  };

  const handleDateChange = (id: string, date: string) => {
    setImages((prev) =>
      prev.map((img) => (img.id === id ? { ...img, date } : img))
    );
  };

  // Client-side validation per API_CONTRACT.md
  const getValidationWarning = (): string | null => {
    if (images.length === 0) {
      return 'Please attach 1 or 2 satellite images to analyze.';
    }
    if (images.length === 2) {
      const isBothOptical = images[0].modality === 'optical' && images[1].modality === 'optical';
      const isOpticalSar = (images[0].modality === 'optical' && images[1].modality === 'sar') ||
                           (images[0].modality === 'sar' && images[1].modality === 'optical');

      if (isBothOptical && images[0].date && images[1].date && images[0].date === images[1].date) {
        return 'Change detection requires two optical images with differing capture dates.';
      }
      if (!isBothOptical && !isOpticalSar) {
        return 'Supported 2-image tasks: 2 Optical images for Change Detection, or 1 Optical + 1 Radar (SAR) for Fusion.';
      }
    }
    return null;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || images.length === 0 || isLoading) return;
    
    // Dispatch query to parent
    onExecute(query.trim(), images);

    // Reset input fields
    setQuery('');
    setImages([]);
    setShowImageDrawer(false);
  };

  const validationWarning = getValidationWarning();

  return (
    <div className="w-full bg-surface-panel/95 backdrop-blur-md border-t border-grid-hairline shadow-2xl transition-all duration-200">
      {/* Attached Imagery Drawer (Collapsible) */}
      {showImageDrawer && images.length > 0 && (
        <div className="px-4 md:px-margin-page py-3.5 border-b border-grid-hairline/60 bg-surface-container/70 animate-in slide-in-from-bottom-2 duration-150">
          <div className="max-w-4xl mx-auto flex flex-col gap-3">
            <div className="flex items-center justify-between text-xs text-text-muted">
              <span className="font-semibold text-text-primary flex items-center gap-2">
                <span>Attached Satellite Images ({images.length}/2)</span>
              </span>

              <div className="flex items-center gap-3">
                {images.length < 2 && (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="text-primary hover:underline flex items-center gap-1.5 font-medium cursor-pointer"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    <span>Attach Second Image</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowImageDrawer(false)}
                  className="text-text-muted hover:text-text-primary p-1 rounded-md hover:bg-surface-variant flex items-center gap-1 text-xs cursor-pointer"
                  title="Hide image drawer"
                >
                  <span>Minimize</span>
                  <ChevronDown className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {images.map((img, idx) => (
                <div
                  key={img.id}
                  className="flex items-center gap-3 p-3 bg-background border border-grid-hairline rounded-xl shadow-xs"
                >
                  {/* Clickable Thumbnail with Lightbox */}
                  {(() => {
                    const isCurrentlyUploading = uploadProgress[img.id] !== undefined;
                    const safeThumb = (img.previewUrl && isBrowserRenderable(img.previewUrl))
                      ? img.previewUrl
                      : (isBrowserRenderable(img.url_or_base64) ? img.url_or_base64 : undefined);

                    return (
                      <div
                        onClick={() => {
                          if (!isCurrentlyUploading && (safeThumb || img.url_or_base64)) {
                            onPreviewImage?.(
                              safeThumb || img.url_or_base64,
                              img.name || `Image #${idx + 1}`,
                              img.modality,
                              img.date
                            );
                          }
                        }}
                        className="w-16 h-16 bg-surface-container border border-grid-hairline rounded-lg overflow-hidden flex-shrink-0 relative group cursor-pointer flex items-center justify-center"
                        title={isCurrentlyUploading ? `Uploading ${uploadProgress[img.id]}%` : "Click to view full image"}
                      >
                        {isCurrentlyUploading ? (
                          <div className="absolute inset-0 bg-black/80 flex flex-col items-center justify-center p-1.5 text-center">
                            <Loader2 className="w-4 h-4 text-cyan-detection animate-spin" />
                            <span className="text-[9px] text-cyan-detection font-bold font-mono mt-0.5">
                              {uploadProgress[img.id]}%
                            </span>
                            <div className="w-full bg-white/20 h-1 rounded-full mt-1 overflow-hidden">
                              <div
                                className="bg-cyan-detection h-full transition-all duration-150"
                                style={{ width: `${uploadProgress[img.id]}%` }}
                              />
                            </div>
                          </div>
                        ) : safeThumb ? (
                          <img
                            src={safeThumb}
                            alt={img.name || `Image ${idx + 1}`}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                          />
                        ) : (
                          <div className="flex flex-col items-center justify-center p-1 text-center">
                            <Loader2 className="w-5 h-5 text-primary animate-spin" />
                            <span className="text-[9px] text-text-muted mt-0.5">Processing</span>
                          </div>
                        )}
                        {!isCurrentlyUploading && safeThumb && (
                          <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                            <Eye className="w-4 h-4 text-white" />
                          </div>
                        )}
                        <span className="absolute bottom-0 right-0 bg-surface-panel/90 text-[10px] font-medium px-1 rounded-tl-md border-t border-l border-grid-hairline text-amber-signal">
                          #{idx + 1}
                        </span>
                      </div>
                    );
                  })()}

                  {/* Metadata Selectors */}
                  <div className="flex flex-col gap-1.5 flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs truncate text-text-primary font-medium">
                        {img.name || `Image #${idx + 1}`}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleRemoveImage(img.id)}
                        className="text-text-muted hover:text-red-delta p-1 rounded-md transition-colors cursor-pointer"
                        title="Remove image"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="flex items-center gap-2">
                      {/* Modality Selector */}
                      <div className="flex items-center gap-1.5 bg-surface-container px-2 py-1 border border-grid-hairline rounded-md text-xs">
                        <Layers className="w-3 h-3 text-cyan-detection" />
                        <select
                          value={img.modality}
                          onChange={(e) =>
                            handleModalityChange(img.id, e.target.value as Modality)
                          }
                          className="bg-transparent border-none outline-none text-text-primary capitalize cursor-pointer text-xs"
                        >
                          <option value="optical">Optical</option>
                          <option value="sar">Radar (SAR)</option>
                        </select>
                      </div>

                      {/* Date Selector */}
                      <div className="flex items-center gap-1.5 bg-surface-container px-2 py-1 border border-grid-hairline rounded-md text-xs">
                        <Calendar className="w-3 h-3 text-primary" />
                        <input
                          type="date"
                          value={img.date || ''}
                          onChange={(e) => handleDateChange(img.id, e.target.value)}
                          className="bg-transparent border-none outline-none text-text-primary text-xs cursor-pointer"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Validation Notice */}
            {validationWarning && (
              <div className="flex items-center gap-2 text-amber-signal text-xs bg-amber-signal/10 px-3 py-1.5 border border-amber-signal/30 rounded-lg">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{validationWarning}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main Command Input Row */}
      <form onSubmit={handleSubmit} className="p-3.5 md:px-margin-page">
        <div className="max-w-4xl mx-auto flex flex-col gap-2">
          {/* Quick status line above input */}
          <div className="flex items-center justify-between px-1 text-xs text-text-muted">
            <div className="flex items-center gap-2">
              <span>Ask a question about the satellite imagery</span>
              {images.length > 0 && !showImageDrawer && (
                <button
                  type="button"
                  onClick={() => setShowImageDrawer(true)}
                  className="flex items-center gap-1 text-primary font-medium bg-primary/10 hover:bg-primary/20 px-2 py-0.5 rounded-full transition-colors cursor-pointer"
                >
                  <span>{images.length} {images.length === 1 ? 'image' : 'images'} attached</span>
                  <ChevronUp className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {onOpenPresets && (
              <button
                type="button"
                onClick={onOpenPresets}
                className="text-xs text-amber-signal hover:underline flex items-center gap-1.5 font-medium cursor-pointer"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Sample Questions</span>
              </button>
            )}
          </div>

          <div className="relative flex items-center bg-background border border-grid-hairline focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 rounded-xl transition-all shadow-sm">
            {/* Attachment Button */}
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              multiple
              accept="image/*,.tif,.tiff,.jp2,.j2k,.jpx,.jpc,.jpf"
              className="hidden"
            />
            <button
              type="button"
              onClick={() => {
                if (images.length === 0) {
                  fileInputRef.current?.click();
                } else {
                  setShowImageDrawer(!showImageDrawer);
                }
              }}
              className={`p-3.5 text-text-muted hover:text-primary transition-colors border-r border-grid-hairline flex items-center gap-1.5 cursor-pointer ${
                images.length > 0 ? 'text-amber-signal font-semibold' : ''
              }`}
              title="Attach satellite imagery (1-2 images)"
            >
              <ImageIcon className="w-5 h-5" />
              {images.length > 0 && (
                <span className="text-xs font-bold bg-primary/20 px-1.5 py-0.5 rounded-full">
                  {images.length}
                </span>
              )}
            </button>

            {/* Natural-Language Input */}
            <input
              id="query-input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={
                images.length === 0
                  ? 'Attach satellite imagery or select a sample question above...'
                  : 'Ask about objects, counting, water bodies, urban change, or radar fusion...'
              }
              disabled={isLoading}
              className="flex-1 bg-transparent border-none outline-none text-sm text-text-primary px-4 py-3.5 placeholder:text-text-muted/50 disabled:opacity-50"
            />

            {/* Clear Input Button */}
            {query && !isLoading && (
              <button
                type="button"
                onClick={() => setQuery('')}
                className="p-2 text-text-muted hover:text-text-primary mr-1 cursor-pointer"
                title="Clear input"
              >
                <X className="w-4 h-4" />
              </button>
            )}

            {/* Analyze Button */}
            <button
              type="submit"
              disabled={!query.trim() || images.length === 0 || isLoading}
              className="px-5 py-3.5 bg-primary-container text-on-primary-container hover:bg-primary transition-all border-l border-grid-hairline text-xs font-bold uppercase flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer rounded-r-xl shadow-xs"
            >
              <span>{isLoading ? 'Analyzing...' : 'Analyze'}</span>
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
