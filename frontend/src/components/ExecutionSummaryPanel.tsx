import React, { useState } from 'react';
import { ExecutionSummary } from '../types/contract';
import { ChevronRight, Cpu, Clock, CheckCircle2, Copy, Check, Sliders } from 'lucide-react';

interface ExecutionSummaryPanelProps {
  summary: ExecutionSummary;
}

export const ExecutionSummaryPanel: React.FC<ExecutionSummaryPanelProps> = ({ summary }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [viewJson, setViewJson] = useState(false);

  const handleCopyJson = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(JSON.stringify(summary, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getToolDisplayName = (tool: string) => {
    switch (tool) {
      case 'rsunivlm_vqa':
        return 'Visual Question Answering';
      case 'rsunivlm_cap':
        return 'Image Captioning';
      case 'rsunivlm_vg':
        return 'Object Localization';
      case 'rsunivlm_seg':
        return 'Semantic Segmentation';
      case 'rsunivlm_ccd':
        return 'Change Detection';
      case 'fusion_classifier':
        return 'Optical–Radar Fusion';
      default:
        return tool.replace(/_/g, ' ');
    }
  };

  const paramEntries = Object.entries(summary.parameters || {});

  return (
    <div className="border-t border-grid-hairline bg-surface-container/30 text-text-primary text-xs select-text">
      {/* Header Bar */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-5 py-3 hover:bg-surface-variant/40 transition-colors text-left focus:outline-none"
      >
        <div className="flex items-center gap-2.5 text-xs text-text-muted">
          <ChevronRight
            className={`w-4 h-4 transition-transform duration-200 ${
              isOpen ? 'rotate-90 text-primary' : 'text-text-muted'
            }`}
          />
          <span className="font-semibold text-text-primary">Analysis Details & Technical Summary</span>
          <span className="opacity-40">•</span>
          <span className="text-amber-signal font-medium">{getToolDisplayName(summary.tool_used)}</span>
        </div>

        <div className="flex items-center gap-3.5 text-xs text-text-muted">
          <div className="flex items-center gap-1.5 font-mono">
            <Clock className="w-3.5 h-3.5 text-cyan-detection" />
            <span>{(summary.latency_ms / 1000).toFixed(2)}s</span>
          </div>
          {summary.inputs_validated && (
            <div className="flex items-center gap-1 text-emerald-sensor font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Verified</span>
            </div>
          )}
        </div>
      </button>

      {/* Expanded Accordion Body */}
      {isOpen && (
        <div className="px-5 py-4 border-t border-grid-hairline/60 bg-surface-panel/90 flex flex-col gap-3.5 rounded-b-xl">
          {/* Top Controls */}
          <div className="flex items-center justify-between text-xs pb-1 border-b border-grid-hairline/40">
            <div className="flex items-center gap-2 text-text-muted">
              <Cpu className="w-4 h-4 text-primary" />
              <span className="font-medium">Model & Execution Info</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setViewJson(!viewJson)}
                className={`px-2.5 py-1 rounded-md border text-[11px] font-medium transition-colors ${
                  viewJson
                    ? 'border-primary text-primary bg-primary/10'
                    : 'border-grid-hairline text-text-muted hover:text-text-primary'
                }`}
              >
                {viewJson ? 'Standard View' : 'Raw Data'}
              </button>
              <button
                type="button"
                onClick={handleCopyJson}
                className="flex items-center gap-1 px-2.5 py-1 border border-grid-hairline text-text-muted hover:text-text-primary rounded-md text-[11px] transition-colors"
                title="Copy Summary JSON"
              >
                {copied ? <Check className="w-3 h-3 text-emerald-sensor" /> : <Copy className="w-3 h-3" />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
          </div>

          {viewJson ? (
            <pre className="p-3.5 bg-background border border-grid-hairline text-[11px] text-text-primary overflow-x-auto rounded-lg max-h-48 font-mono">
              {JSON.stringify(summary, null, 2)}
            </pre>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="bg-surface-container/60 p-3 border border-grid-hairline/60 rounded-lg flex flex-col">
                <span className="text-text-muted text-[11px]">Analysis Task</span>
                <span className="font-semibold text-text-primary capitalize mt-1 text-sm">
                  {summary.selected_task.replace(/_/g, ' ')}
                </span>
              </div>

              <div className="bg-surface-container/60 p-3 border border-grid-hairline/60 rounded-lg flex flex-col">
                <span className="text-text-muted text-[11px]">AI Model</span>
                <span className="font-semibold text-amber-signal mt-1 text-sm truncate" title={summary.tool_used}>
                  {getToolDisplayName(summary.tool_used)}
                </span>
              </div>

              <div className="bg-surface-container/60 p-3 border border-grid-hairline/60 rounded-lg flex flex-col">
                <span className="text-text-muted text-[11px]">Response Time</span>
                <span className="font-semibold text-cyan-detection mt-1 text-sm font-mono">
                  {(summary.latency_ms / 1000).toFixed(2)} seconds
                </span>
              </div>

              <div className="bg-surface-container/60 p-3 border border-grid-hairline/60 rounded-lg flex flex-col">
                <span className="text-text-muted text-[11px]">Input Verification</span>
                <span className="font-semibold text-emerald-sensor mt-1 text-sm">
                  {summary.inputs_validated ? 'Passed' : 'Pending'}
                </span>
              </div>

              {/* Parameters Table */}
              <div className="col-span-full bg-surface-container/40 p-3.5 border border-grid-hairline/60 rounded-lg">
                <div className="flex items-center gap-2 text-text-muted text-xs font-semibold mb-2">
                  <Sliders className="w-3.5 h-3.5 text-primary" />
                  <span>Model Parameters & Metadata</span>
                </div>
                {paramEntries.length > 0 ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
                    {paramEntries.map(([key, val]) => (
                      <div key={key} className="flex flex-col bg-background/70 px-3 py-2 border border-grid-hairline/40 rounded-md">
                        <span className="text-text-muted text-[10px] uppercase truncate" title={key}>
                          {key.replace(/_/g, ' ')}
                        </span>
                        <span className="text-text-primary font-medium text-xs truncate mt-0.5" title={String(val)}>
                          {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-text-muted italic text-xs">Standard parameters used.</span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
