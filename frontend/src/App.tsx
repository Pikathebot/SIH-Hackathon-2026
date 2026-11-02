import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import { TelemetryBar } from './components/TelemetryBar';
import { Sidebar } from './components/Sidebar';
import { ReportCard } from './components/ReportCard';
import { LoadingTrace } from './components/LoadingTrace';
import { QueryComposer } from './components/QueryComposer';
import { ImageLightboxModal } from './components/ImageLightboxModal';
import { DemoPresetSelector, DemoPreset, SAMPLES_BASE } from './components/DemoPresetSelector';
import { submitQuery, isBrowserRenderable, uploadLargeImage } from './services/api';
import {
  assetPreviewUrl,
  createSession,
  deleteSession,
  fetchHistory,
  listSessions,
  renameSession,
} from './services/sessions';
import {
  ChatMessage,
  AnalysisSession,
  QueryImage,
  Modality,
  SessionDto,
  HistoryEntry,
} from './types/contract';
import { AlertOctagon, Sparkles, Globe2, Eye, Trash2, AlertTriangle, UploadCloud, Layers, Loader2, X } from 'lucide-react';

// ── Helpers: API DTOs → UI state ─────────────────────────────────────────────
const DEFAULT_TITLES = new Set(['new analysis']);

const formatTime = (iso: string) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' });
};

const nowLabel = () =>
  new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC';

const toUiSession = (s: SessionDto): AnalysisSession => ({
  id: s.id,
  title: s.title,
  timestamp: formatTime(s.updated_at),
  queryCount: s.query_count,
  imageCount: 0,
});

const historyToMessages = (entries: HistoryEntry[]): ChatMessage[] =>
  entries.flatMap((e) => {
    const images: QueryImage[] = (e.images?.length ? e.images : e.image_asset_ids.map((asset_id) => ({ asset_id })))
      .map((img: { asset_id: string; modality?: Modality | null; date?: string | null }, i) => ({
        id: img.asset_id,
        asset_id: img.asset_id,
        modality: img.modality || 'optical',
        date: img.date || undefined,
        url_or_base64: '',
        name: `Image #${i + 1}`,
      }));
    const user: ChatMessage = {
      id: `u_${e.id}`, sender: 'user', timestamp: formatTime(e.created_at), query: e.query_text, images,
    };
    const reply: ChatMessage = e.response
      ? { id: `a_${e.id}`, sender: 'assistant', timestamp: formatTime(e.created_at), response: e.response }
      : {
          id: `a_${e.id}`, sender: 'assistant', timestamp: formatTime(e.created_at),
          error: { code: e.error_code || 'INTERNAL_ERROR', message: 'This analysis did not complete.' },
        };
    return [user, reply];
  });

// ── Main workspace ────────────────────────────────────────────────────────────
const WorkspaceMain: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>();
  const activeSessionId = routeSessionId ?? null;

  const [sessions, setSessions] = useState<AnalysisSession[]>([]);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [sessionMessages, setSessionMessages] = useState<Record<string, ChatMessage[]>>({});
  const [historyLoading, setHistoryLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
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
  const requestedHistory = useRef<Set<string>>(new Set());
  const activeMessages = (activeSessionId && sessionMessages[activeSessionId]) || [];

  // Auto-scroll when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeMessages, isLoading]);

  // ── Load the user's sessions once ──────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    listSessions()
      .then((list) => {
        if (cancelled) return;
        setSessions(list.map(toUiSession));
        setSessionsLoaded(true);
        if (!routeSessionId && list.length > 0) navigate(`/s/${list[0].id}`, { replace: true });
      })
      .catch((err) => !cancelled && setLoadError(err?.message || 'Could not load your analyses.'));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // An unknown or foreign session id in the URL → back to the workspace root
  useEffect(() => {
    if (sessionsLoaded && activeSessionId && !sessions.some((s) => s.id === activeSessionId)) {
      navigate('/', { replace: true });
    }
  }, [sessionsLoaded, activeSessionId, sessions, navigate]);

  // Thumbnails for history images come from the authenticated preview endpoint.
  const hydratePreviews = useCallback((sid: string, messages: ChatMessage[]) => {
    messages.forEach((m) =>
      m.images?.forEach((img) => {
        if (!img.asset_id || img.previewUrl) return;
        assetPreviewUrl(img.asset_id).then((url) => {
          if (!url) return;
          setSessionMessages((prev) => ({
            ...prev,
            [sid]: (prev[sid] || []).map((pm) =>
              pm.id !== m.id
                ? pm
                : { ...pm, images: pm.images?.map((pi) => (pi.asset_id === img.asset_id ? { ...pi, previewUrl: url } : pi)) }
            ),
          }));
        });
      })
    );
  }, []);

  // ── Load a session's history the first time it is opened ───────────────────
  useEffect(() => {
    const sid = activeSessionId;
    if (!sid || requestedHistory.current.has(sid) || !sessions.some((s) => s.id === sid)) return;
    requestedHistory.current.add(sid);
    setHistoryLoading(true);
    fetchHistory(sid)
      .then((entries) => {
        const messages = historyToMessages(entries);
        setSessionMessages((prev) => ({ ...prev, [sid]: [...messages, ...(prev[sid] || [])] }));
        hydratePreviews(sid, messages);
        const lastTask = [...entries].reverse().find((e) => e.response)?.response?.task;
        if (lastTask) setSessions((prev) => prev.map((s) => (s.id === sid ? { ...s, previewTask: lastTask } : s)));
      })
      .catch((err) => {
        requestedHistory.current.delete(sid);
        setLoadError(err?.message || 'Could not load this analysis.');
      })
      .finally(() => setHistoryLoading(false));
  }, [activeSessionId, sessions, hydratePreviews]);

  // ── Session management ──────────────────────────────────────────────────────
  const openSession = (id: string | null) => navigate(id ? `/s/${id}` : '/');

  const handleSelectSession = (id: string) => {
    openSession(id);
  };

  const startSession = async (): Promise<string> => {
    const created = await createSession();
    requestedHistory.current.add(created.id); // brand new: nothing to fetch
    setSessions((prev) => [toUiSession(created), ...prev]);
    setSessionMessages((prev) => ({ ...prev, [created.id]: [] }));
    openSession(created.id);
    return created.id;
  };

  const handleNewAnalysis = async () => {
    try {
      await startSession();
      setComposerState({ query: '', images: [] });
    } catch (err: any) {
      setLoadError(err?.message || 'Could not start a new analysis.');
    }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await deleteSession(id);
    } catch (err: any) {
      setLoadError(err?.message || 'Could not delete this analysis.');
      return;
    }
    const remaining = sessions.filter((s) => s.id !== id);
    setSessions(remaining);
    setSessionMessages((prev) => {
      const updated = { ...prev };
      delete updated[id];
      return updated;
    });
    if (id === activeSessionId) openSession(remaining[0]?.id ?? null);
  };

  const handleConfirmClearAll = async () => {
    setShowClearConfirmModal(false);
    const results = await Promise.allSettled(sessions.map((s) => deleteSession(s.id)));
    const failed = sessions.filter((_, i) => results[i].status === 'rejected');
    setSessions(failed);
    setSessionMessages({});
    requestedHistory.current.clear();
    setComposerState({ query: '', images: [] });
    if (failed.length) setLoadError(`${failed.length} analyses could not be deleted.`);
    openSession(failed[0]?.id ?? null);
  };

  const handleSelectPreset = async (preset: DemoPreset) => {
    setComposerState({ query: preset.query, images: [] });
    try {
      // Upload the bundled sample files exactly as if the user had attached them.
      const images = await Promise.all(
        preset.samples.map(async (s, i): Promise<QueryImage> => {
          const res = await fetch(`${SAMPLES_BASE}${s.file}`);
          // A missing static file comes back as the SPA's index.html with 200, so check the type too.
          if (!res.ok || (res.headers.get('content-type') || '').includes('text/html')) {
            throw new Error(`Sample image ${s.file} is missing. Run scripts/build_demo_samples.py.`);
          }
          const blob = await res.blob();
          const up = await uploadLargeImage(new File([blob], s.file, { type: blob.type || 'image/tiff' }));
          return {
            id: `preset_${Date.now()}_${i + 1}`,
            modality: s.modality,
            date: s.date,
            url_or_base64: up.url,
            asset_id: up.asset_id,
            previewUrl: up.preview_base64,
            name: `${up.filename} (${(blob.size / (1024 * 1024)).toFixed(1)} MB)`,
          };
        })
      );
      setComposerState({ query: preset.query, images });
    } catch (err: any) {
      setLoadError(err?.message || 'Could not load the sample images.');
    }
  };

  const handleSignOut = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  // ── Query submission ────────────────────────────────────────────────────────
  const handleExecute = async (queryText: string, attachedImages: QueryImage[]) => {
    let sid = activeSessionId;
    try {
      if (!sid) sid = await startSession();
    } catch (err: any) {
      setLoadError(err?.message || 'Could not start a new analysis.');
      return;
    }
    const sessionKey = sid;

    // Free massive multi-megabyte raw TIFF data from persistent React chat history state.
    // Chat history only requires lightweight web-displayable preview thumbnails (~80 KB PNGs).
    const displayImages: QueryImage[] = attachedImages.map((img) => {
      const lightweightUrl = img.previewUrl || (isBrowserRenderable(img.url_or_base64) && img.url_or_base64.length < 500000 ? img.url_or_base64 : undefined);
      return {
        ...img,
        url_or_base64: lightweightUrl || '',
        previewUrl: lightweightUrl,
      };
    });

    const userMsg: ChatMessage = {
      id: `usr_${Date.now()}`,
      sender: 'user',
      timestamp: nowLabel(),
      query: queryText,
      images: displayImages,
    };

    setSessionMessages((prev) => ({
      ...prev,
      [sessionKey]: [...(prev[sessionKey] || []), userMsg],
    }));

    // First question in an untitled session names it (saved on the server too).
    const current = sessions.find((s) => s.id === sessionKey);
    const newTitle = queryText.slice(0, 60) + (queryText.length > 60 ? '…' : '');
    if (!current || (current.queryCount === 0 && DEFAULT_TITLES.has(current.title.toLowerCase()))) {
      renameSession(sessionKey, newTitle).catch(() => undefined);
      setSessions((prev) => prev.map((s) => (s.id === sessionKey ? { ...s, title: newTitle } : s)));
    }

    setIsLoading(true);

    try {
      const response = await submitQuery({ query: queryText, images: attachedImages, session_id: sessionKey });

      const assistantMsg: ChatMessage = {
        id: `asst_${Date.now()}`,
        sender: 'assistant',
        timestamp: nowLabel(),
        response,
      };

      setSessionMessages((prev) => ({
        ...prev,
        [sessionKey]: [...(prev[sessionKey] || []), assistantMsg],
      }));

      // Saved on the server: bump the count and move the session to the top.
      setSessions((prev) => {
        const updated = prev.map((s) =>
          s.id === sessionKey
            ? { ...s, previewTask: response.task, queryCount: s.queryCount + 1, timestamp: formatTime(new Date().toISOString()) }
            : s
        );
        const idx = updated.findIndex((s) => s.id === sessionKey);
        return idx > 0 ? [updated[idx], ...updated.slice(0, idx), ...updated.slice(idx + 1)] : updated;
      });
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: `err_${Date.now()}`,
        sender: 'assistant',
        timestamp: nowLabel(),
        error: {
          code: err.code || 'MODEL_INFERENCE_FAILED',
          message:
            err.message || 'Unable to complete the analysis. Please check your imagery and try again.',
          detail: err.detail || err.stack,
          requestId: err.requestId,
        },
      };

      setSessionMessages((prev) => ({
        ...prev,
        [sessionKey]: [...(prev[sessionKey] || []), errorMsg],
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
        userEmail={user?.email}
        onSignOut={handleSignOut}
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
          {loadError && (
            <div role="alert" className="w-full max-w-4xl mx-auto bg-red-delta/10 border border-red-delta/40 px-4 py-3 rounded-2xl flex items-start gap-3 text-sm">
              <AlertOctagon className="w-4 h-4 text-red-delta flex-shrink-0 mt-0.5" />
              <p className="flex-1 text-text-primary">{loadError}</p>
              <button type="button" onClick={() => setLoadError(null)} aria-label="Dismiss" className="text-text-muted hover:text-text-primary">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {historyLoading && activeMessages.length === 0 && (
            <div className="my-auto flex items-center justify-center gap-2 text-text-muted text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Loading analysis…</span>
            </div>
          )}

          {/* Clean Initial Empty State */}
          {activeMessages.length === 0 && !historyLoading && (
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
                      {msg.error.requestId && (
                        <p className="mt-1 font-mono text-[10px] text-text-muted select-text">
                          Request ID: {msg.error.requestId}
                        </p>
                      )}
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
export const App: React.FC = () => <WorkspaceMain />;

export default App;
