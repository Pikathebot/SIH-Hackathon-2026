import React from 'react';
import { AnalysisSession } from '../types/contract';
import {
  Plus,
  Radar,
  Scan,
  GitCompare,
  Layers,
  Trash2,
  X,
  Globe2,
  Clock,
  HelpCircle,
} from 'lucide-react';

interface SidebarProps {
  sessions: AnalysisSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewAnalysis: () => void;
  onDeleteSession: (id: string) => void;
  onClearHistory: () => void;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewAnalysis,
  onDeleteSession,
  onClearHistory,
  isOpenMobile,
  onCloseMobile,
}) => {
  const getTaskIcon = (task?: string) => {
    switch (task) {
      case 'vqa':
      case 'captioning':
        return <Radar className="w-4 h-4 text-primary" />;
      case 'detection':
        return <Scan className="w-4 h-4 text-cyan-detection" />;
      case 'change_detection':
        return <GitCompare className="w-4 h-4 text-red-delta" />;
      case 'fusion':
        return <Layers className="w-4 h-4 text-secondary" />;
      default:
        return <Radar className="w-4 h-4 text-primary" />;
    }
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isOpenMobile && (
        <div
          onClick={onCloseMobile}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
        />
      )}

      <nav
        className={`fixed left-0 top-0 h-full w-[280px] flex flex-col z-50 bg-surface-panel border-r border-grid-hairline transition-transform duration-200 ease-in-out md:translate-x-0 ${
          isOpenMobile ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* ── Brand Header ── */}
        <div className="h-[52px] px-5 border-b border-grid-hairline flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 bg-primary/10 rounded-xl text-primary">
              <Globe2 className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-headline text-base font-bold text-text-primary tracking-tight leading-none">
                SatQuery AI
              </h1>
              <p className="text-[10px] text-text-muted mt-0.5">Earth Observation Platform</p>
            </div>
          </div>
          {isOpenMobile && (
            <button
              type="button"
              onClick={onCloseMobile}
              className="md:hidden p-1.5 text-text-muted hover:text-text-primary rounded-lg"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* ── New Chat Button ── */}
        <div className="px-3 py-3 flex-shrink-0">
          <button
            type="button"
            onClick={() => { onNewAnalysis(); onCloseMobile?.(); }}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-primary-container text-on-primary-container hover:bg-primary text-sm font-semibold rounded-xl transition-all shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>New Analysis</span>
          </button>
        </div>

        <div className="mx-3 border-t border-grid-hairline flex-shrink-0" />

        {/* ── Session List ── */}
        <div className="px-3 py-2 flex items-center justify-between flex-shrink-0">
          <p className="text-[11px] font-semibold uppercase text-text-muted tracking-wider">
            Chat History
          </p>
          <span className="text-[10px] bg-surface-container px-2 py-0.5 rounded-full text-text-muted">
            {sessions.length}
          </span>
        </div>

        <ul className="flex-1 overflow-y-auto px-2 pb-2 flex flex-col gap-0.5">
          {sessions.map((session) => {
            const isActive = session.id === activeSessionId;
            return (
              <li
                key={session.id}
                className={`group flex items-center gap-2.5 px-3 py-2.5 cursor-pointer transition-all rounded-xl ${
                  isActive
                    ? 'bg-surface-container border border-grid-hairline shadow-xs'
                    : 'hover:bg-surface-variant/40'
                }`}
                onClick={() => { onSelectSession(session.id); onCloseMobile?.(); }}
              >
                {/* Task icon */}
                <div className="flex-shrink-0 opacity-80">
                  {getTaskIcon(session.previewTask)}
                </div>

                {/* Session info */}
                <div className="flex flex-col min-w-0 flex-1">
                  <span className={`text-xs truncate font-medium ${isActive ? 'text-text-primary' : 'text-text-muted'}`}>
                    {session.title}
                  </span>
                  <div className="flex items-center gap-1.5 text-[11px] text-text-muted mt-0.5 opacity-70">
                    <Clock className="w-2.5 h-2.5" />
                    <span>{session.timestamp}</span>
                    <span>·</span>
                    <span>{session.queryCount} msg{session.queryCount !== 1 ? 's' : ''}</span>
                  </div>
                </div>

                {/* Delete button — appears on hover */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(session.id);
                  }}
                  title="Delete this conversation"
                  className="flex-shrink-0 p-1.5 rounded-lg text-text-muted opacity-0 group-hover:opacity-100 hover:text-red-delta hover:bg-red-delta/10 transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
            );
          })}

          {sessions.length === 0 && (
            <li className="px-4 py-10 text-center text-text-muted text-xs flex flex-col items-center gap-2">
              <HelpCircle className="w-6 h-6 opacity-40" />
              <span>No analyses yet. Start a new chat above.</span>
            </li>
          )}
        </ul>

        {/* ── Footer: Clear all ── */}
        {sessions.length > 0 && (
          <div className="px-3 py-2.5 border-t border-grid-hairline flex-shrink-0 bg-surface-container/30">
            <button
              type="button"
              onClick={onClearHistory}
              className="flex items-center justify-center gap-2 w-full px-3 py-2 text-text-muted hover:text-red-delta text-xs font-medium transition-colors rounded-lg hover:bg-red-delta/10 border border-grid-hairline/60"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Clear All History</span>
            </button>
          </div>
        )}
      </nav>
    </>
  );
};
