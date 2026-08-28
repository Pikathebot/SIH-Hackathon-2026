import React, { useState, useEffect, useRef } from 'react';
import { ThemeProvider } from './context/ThemeContext';
import { TelemetryBar } from './components/TelemetryBar';
import { Sidebar } from './components/Sidebar';
import { ReportCard } from './components/ReportCard';
import { LoadingTrace } from './components/LoadingTrace';
import { QueryComposer } from './components/QueryComposer';
import { ImageLightboxModal } from './components/ImageLightboxModal';
import { DemoPresetSelector, DemoPreset } from './components/DemoPresetSelector';
import { submitQuery, isBrowserRenderable } from './services/api';
import { ChatMessage, AnalysisSession, QueryImage } from './types/contract';
import { AlertOctagon, Sparkles, Globe2, Eye, Trash2, AlertTriangle, UploadCloud, Layers } from 'lucide-react';

// ── Initial Clean Session State ──────────────────────────────────────────────
const INITIAL_SESSION_ID = 'session-1';
const INITIAL_SESSIONS: AnalysisSession[] = [
  {
    id: INITIAL_SESSION_ID,
    title: 'New Analysis',
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC',
    queryCount: 0,
    imageCount: 0,
  },
];

const INITIAL_MESSAGES: Record<string, ChatMessage[]> = {
  [INITIAL_SESSION_ID]: [],
};

// ── Main workspace ────────────────────────────────────────────────────────────
const WorkspaceMain: React.FC = () => {
  const [sessions, setSessions] = useState<AnalysisSession[]>(INITIAL_SESSIONS);
  const [activeSessionId, setActiveSessionId] = useState<string>(INITIAL_SESSION_ID);
  const [sessionMessages, setSessionMessages] = useState<Record<string, ChatMessage[]>>(INITIAL_MESSAGES);
  const [isLoading, setIsLoading] = useState(false);
  const [isPresetsOpen, setIsPresetsOpen] = useState(false);
  const [isSidebarOpenMobile, setIsSidebarOpenMobile] = useState(false);
  const [showClearConfirmModal, setShowClearConfirmModal] = useState(false);
  const [lightboxImage, setLightboxImage] = useState<{
    url: string;
    title?: string;
    modality?: string;
    date?: string;
  } | null>(null);

  const [composerState, setComposerState] = useState<{ query: string; images: QueryImage[] }>({
    query: '',
    images: [],
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  const activeMessages = sessionMessages[activeSessionId] || [];

  // Auto-scroll when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeMessages, isLoading]);

  // ── Session management ──────────────────────────────────────────────────────
  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
  };

  const handleNewAnalysis = () => {
    const newId = `session-${Date.now()}`;
    const newSession: AnalysisSession = {
      id: newId,
      title: 'New Analysis',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC',
      queryCount: 0,
      imageCount: 0,
    };
    setSessions((prev) => [newSession, ...prev]);
    setSessionMessages((prev) => ({ ...prev, [newId]: [] }));
    setActiveSessionId(newId);
    setComposerState({ query: '', images: [] });
  };

  const handleDeleteSession = (id: string) => {
    setSessions((prev) => {
      const updated = prev.filter((s) => s.id !== id);
      if (id === activeSessionId) {
        if (updated.length > 0) {
          setActiveSessionId(updated[0].id);
        } else {
          const newId = `session-${Date.now()}`;
          const newSession: AnalysisSession = {
            id: newId,
            title: 'New Analysis',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC',
            queryCount: 0,
            imageCount: 0,
          };
          setSessionMessages((msgs) => ({ ...msgs, [newId]: [] }));
          setActiveSessionId(newId);
          return [newSession];
        }
      }
      return updated;
    });
    setSessionMessages((prev) => {
      const updated = { ...prev };
      delete updated[id];
      return updated;
    });
  };

  const handleConfirmClearAll = () => {
    const newId = `session-${Date.now()}`;
    const fresh: AnalysisSession = {
      id: newId,
      title: 'New Analysis',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC',
      queryCount: 0,
      imageCount: 0,
    };
    setSessions([fresh]);
    setSessionMessages({ [newId]: [] });
    setActiveSessionId(newId);
    setComposerState({ query: '', images: [] });
    setShowClearConfirmModal(false);
  };

  const handleSelectPreset = (preset: DemoPreset) => {
    setComposerState({ query: preset.query, images: preset.images });
  };

  // ── Query submission ────────────────────────────────────────────────────────
  const handleExecute = async (queryText: string, attachedImages: QueryImage[]) => {
    const timestamp =
      new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC';

    const userMsg: ChatMessage = {
      id: `usr_${Date.now()}`,
      sender: 'user',
      timestamp,
      query: queryText,
      images: attachedImages,
    };

    setSessionMessages((prev) => ({
      ...prev,
      [activeSessionId]: [...(prev[activeSessionId] || []), userMsg],
    }));

    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSessionId
          ? {
              ...s,
              title: queryText.slice(0, 36) + (queryText.length > 36 ? '…' : ''),
              queryCount: s.queryCount + 1,
              imageCount: Math.max(s.imageCount, attachedImages.length),
            }
          : s
      )
    );

    setIsLoading(true);

    try {
      const response = await submitQuery({ query: queryText, images: attachedImages });

      const assistantMsg: ChatMessage = {
        id: `asst_${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC',
        response,
      };

      setSessionMessages((prev) => ({
        ...prev,
        [activeSessionId]: [...(prev[activeSessionId] || []), assistantMsg],
      }));

      setSessions((prev) =>
        prev.map((s) => (s.id === activeSessionId ? { ...s, previewTask: response.task } : s))
      );
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: `err_${Date.now()}`,
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC',
        error: {
          code: err.code || 'MODEL_INFERENCE_FAILED',
          message:
            err.message || 'Unable to complete the analysis. Please check your imagery and try again.',
          detail: err.detail || err.stack,
        },
      };

      setSessionMessages((prev) => ({
        ...prev,
        [activeSessionId]: [...(prev[activeSessionId] || []), errorMsg],
      }));
    } finally {
      setIsLoading(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-screen overflow-hidden bg-background text-text-primary font-body select-none">
      {/* Sidebar */}
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewAnalysis={handleNewAnalysis}
        onDeleteSession={handleDeleteSession}
        onClearHistory={() => setShowClearConfirmModal(true)}
        isOpenMobile={isSidebarOpenMobile}
        onCloseMobile={() => setIsSidebarOpenMobile(false)}
      />

      {/* Main content area */}
      <div className="flex-1 flex flex-col md:ml-[280px] h-full relative overflow-hidden">
        {/* Header */}
        <TelemetryBar
          onToggleSidebar={() => setIsSidebarOpenMobile((v) => !v)}
          onOpenPresets={() => setIsPresetsOpen(true)}
        />

        {/* Chat canvas */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto pt-[52px] pb-[130px] px-4 md:px-8 flex flex-col gap-5 scroll-smooth"
        >
          {/* Clean Initial Empty State */}
          {activeMessages.length === 0 && (
            <div className="max-w-xl mx-auto my-auto flex flex-col items-center text-center gap-5 py-16 animate-in fade-in duration-300">
              <div className="p-4 bg-surface-panel border border-grid-hairline rounded-2xl shadow-md">
                <Globe2 className="w-10 h-10 text-primary" />
              </div>
              <div>
                <h2 className="font-headline text-xl font-bold tracking-tight text-text-primary">
                  SatQuery AI Assistant
                </h2>
                <p className="text-sm text-text-muted mt-1.5 leading-relaxed max-w-md mx-auto">
                  Ask natural-language questions about satellite imagery. The AI automatically identifies your intent to perform object detection, land cover segmentation, change analysis, or radar fusion.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full mt-1">
                <button
                  type="button"
                  onClick={() => setIsPresetsOpen(true)}
                  className="p-4 bg-surface-panel hover:bg-surface-container border border-grid-hairline hover:border-primary transition-all text-left flex items-start gap-3 rounded-2xl group shadow-sm cursor-pointer"
                >
                  <div className="p-2 bg-primary/10 rounded-xl text-primary group-hover:scale-110 transition-transform">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-text-primary">Sample Scenarios</p>
                    <p className="text-xs text-text-muted mt-0.5">Explore ready-made questions & imagery</p>
                  </div>
                </button>

                <div
                  className="p-4 bg-surface-panel border border-grid-hairline text-left flex items-start gap-3 rounded-2xl shadow-sm"
                >
                  <div className="p-2 bg-cyan-detection/10 rounded-xl text-cyan-detection">
                    <UploadCloud className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-text-primary">Attach & Ask Below</p>
                    <p className="text-xs text-text-muted mt-0.5">Upload 1-2 satellite images to begin</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Messages Timeline */}
          {activeMessages.map((msg, index) => {
            if (msg.sender === 'user') {
              return (
                <div key={msg.id} className="flex justify-end w-full max-w-4xl mx-auto">
                  <div className="bg-surface-variant border border-grid-hairline px-5 py-4 max-w-[85%] rounded-2xl shadow-sm flex flex-col gap-3">
                    <p className="text-sm text-text-primary leading-relaxed">{msg.query}</p>

                    {/* Attached Uploaded Images — Clickable Gallery */}
                    {msg.images && msg.images.length > 0 && (
                      <div className="flex flex-wrap gap-2.5 pt-2 border-t border-grid-hairline/60">
                        {msg.images.map((img, imgIdx) => {
                          const safeUrl = (img.previewUrl && isBrowserRenderable(img.previewUrl))
                            ? img.previewUrl
                            : (isBrowserRenderable(img.url_or_base64) ? img.url_or_base64 : undefined);

                          return (
                            <div
                              key={img.id || imgIdx}
                              onClick={() => {
                                if (safeUrl || img.url_or_base64) {
                                  setLightboxImage({
                                    url: safeUrl || img.url_or_base64,
                                    title: img.name || `Uploaded Image #${imgIdx + 1}`,
                                    modality: img.modality,
                                    date: img.date,
                                  });
                                }
                              }}
                              className="group relative w-24 h-24 sm:w-28 sm:h-28 bg-background border border-grid-hairline rounded-xl overflow-hidden cursor-pointer shadow-xs hover:border-primary transition-all"
                              title="Click to view full image"
                            >
                              {safeUrl ? (
                                <img
                                  src={safeUrl}
                                  alt={img.name || `Image #${imgIdx + 1}`}
                                  className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                                />
                              ) : (
                                <div className="w-full h-full flex flex-col items-center justify-center p-2 bg-surface-container text-center">
                                  <Layers className="w-5 h-5 text-amber-signal animate-pulse" />
                                  <span className="text-[10px] text-text-muted mt-1 truncate max-w-[80px]">
                                    {img.name || 'Raster'}
                                  </span>
                                </div>
                              )}

                              {/* Hover overlay with eye icon */}
                              {safeUrl && (
                                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                                  <Eye className="w-5 h-5 text-white" />
                                </div>
                              )}

                              {/* Modality & Date Badge */}
                              <div className="absolute bottom-0 inset-x-0 bg-black/75 backdrop-blur-xs text-[10px] px-1.5 py-0.5 text-text-primary flex items-center justify-between">
                                <span className="capitalize text-amber-signal font-semibold truncate">
                                  {img.modality === 'sar' ? 'SAR' : 'Optical'}
                                </span>
                                {img.date && (
                                  <span className="text-text-muted truncate text-[9px]">
                                    {img.date.slice(5)}
                                  </span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    <p className="text-[11px] text-text-muted text-right">{msg.timestamp}</p>
                  </div>
                </div>
              );
            }

            if (msg.error) {
              return (
                <div key={msg.id} className="w-full max-w-4xl mx-auto">
                  <div className="bg-red-delta/10 border border-red-delta/40 p-4 rounded-2xl flex items-start gap-3 text-sm shadow-sm">
                    <AlertOctagon className="w-4 h-4 text-red-delta flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold text-red-delta text-xs mb-1">Analysis Notice</p>
                      <p className="text-text-primary">{msg.error.message}</p>
                    </div>
                  </div>
                </div>
              );
            }

            if (msg.response) {
              const prevUser = activeMessages
                .slice(0, index)
                .reverse()
                .find((m) => m.sender === 'user');

              return (
                <div key={msg.id} className="w-full max-w-4xl mx-auto">
                  <ReportCard
                    response={msg.response}
                    sourceImages={prevUser?.images}
                    timestamp={msg.timestamp}
                  />
                </div>
              );
            }

            return null;
          })}

          {/* Loading Animation */}
          {isLoading && (
            <div className="w-full max-w-4xl mx-auto">
              <LoadingTrace />
            </div>
          )}
        </div>

        {/* Fixed composer bar */}
        <div className="absolute bottom-0 left-0 right-0 z-30">
          <QueryComposer
            onExecute={handleExecute}
            isLoading={isLoading}
            onOpenPresets={() => setIsPresetsOpen(true)}
            onPreviewImage={(url, title, modality, date) =>
              setLightboxImage({ url, title, modality, date })
            }
            initialQuery={composerState.query}
            initialImages={composerState.images}
          />
        </div>
      </div>

      {/* Presets modal */}
      <DemoPresetSelector
        isOpen={isPresetsOpen}
        onClose={() => setIsPresetsOpen(false)}
        onSelectPreset={handleSelectPreset}
      />

      {/* Lightbox Modal for full image view */}
      {lightboxImage && (
        <ImageLightboxModal
          isOpen={!!lightboxImage}
          onClose={() => setLightboxImage(null)}
          imageUrl={lightboxImage.url}
          title={lightboxImage.title}
          modality={lightboxImage.modality}
          date={lightboxImage.date}
        />
      )}

      {/* Clear All History Confirmation Modal */}
      {showClearConfirmModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-150"
          onClick={() => setShowClearConfirmModal(false)}
        >
          <div
            className="bg-surface-panel border border-grid-hairline w-full max-w-md rounded-2xl shadow-2xl p-6 flex flex-col gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-red-delta/10 text-red-delta rounded-xl">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-headline font-bold text-base text-text-primary">
                  Clear All History?
                </h3>
                <p className="text-xs text-text-muted mt-0.5">
                  This will remove all saved analysis sessions and conversations.
                </p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-grid-hairline">
              <button
                type="button"
                onClick={() => setShowClearConfirmModal(false)}
                className="px-4 py-2 bg-surface-container hover:bg-surface-variant border border-grid-hairline rounded-xl text-xs font-semibold text-text-primary transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmClearAll}
                className="px-4 py-2 bg-red-delta text-white hover:bg-red-delta/90 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Clear All</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Root ──────────────────────────────────────────────────────────────────────
export const App: React.FC = () => (
  <ThemeProvider>
    <WorkspaceMain />
  </ThemeProvider>
);

export default App;
