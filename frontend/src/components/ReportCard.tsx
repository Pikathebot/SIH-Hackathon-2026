import React from 'react';
import { QueryResponse, QueryImage } from '../types/contract';
import { CoordinateTickFrame } from './CoordinateTickFrame';
import { ExecutionSummaryPanel } from './ExecutionSummaryPanel';
import { DualImageSplitSlider } from './DualImageSplitSlider';
import { isBrowserRenderable } from '../services/api';
import { exportGeoJSON, exportReportJSON, exportMissionPDF } from '../utils/reportExport';
import { 
  Radar, 
  Scan, 
  Layers, 
  GitCompare, 
  Sparkles, 
  ShieldCheck, 
  AlertTriangle,
  FileDown,
  Compass,
  FileCode
} from 'lucide-react';

interface ReportCardProps {
  response: QueryResponse;
  sourceImages?: QueryImage[];
  timestamp?: string;
}

export const ReportCard: React.FC<ReportCardProps> = ({
  response,
  sourceImages = [],
  timestamp = new Date().toLocaleTimeString(),
}) => {
  const getTaskIcon = (task: string) => {
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
        return <Sparkles className="w-4 h-4 text-primary" />;
    }
  };

  const getTaskTitle = (task: string) => {
    switch (task) {
      case 'vqa':
        return 'Visual Q&A Report';
      case 'captioning':
        return 'Image Description Report';
      case 'detection':
        return 'Object & Feature Detection';
      case 'change_detection':
        return 'Temporal Change Analysis';
      case 'fusion':
        return 'Multi-Sensor Fusion Report';
      default:
        return 'Analysis Report';
    }
  };

  const confidencePercent = Math.round(response.confidence * 100);
  const isHighConfidence = confidencePercent >= 75;

  const primaryImage = sourceImages[0];
  const secondaryImage = sourceImages[1];

  const getSafeImageUrl = (img?: QueryImage): string | undefined => {
    if (!img) return undefined;
    if (img.previewUrl && isBrowserRenderable(img.previewUrl)) {
      return img.previewUrl;
    }
    if (img.url_or_base64 && isBrowserRenderable(img.url_or_base64)) {
      return img.url_or_base64;
    }
    return undefined;
  };

  const safePrimaryUrl = getSafeImageUrl(primaryImage);
  const safeSecondaryUrl = getSafeImageUrl(secondaryImage);

  const hasVisualEvidence = response.visual_evidence && response.visual_evidence.type !== 'none';
  const hasGeospatialData = Boolean(response.visual_evidence?.geospatial?.image_bounds);

  return (
    <div className="w-full bg-surface-panel border border-grid-hairline shadow-md relative rounded-2xl overflow-hidden transition-all">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4 border-b border-grid-hairline bg-surface-container/60">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-surface-variant/70 border border-grid-hairline rounded-xl shadow-xs">
            {getTaskIcon(response.task)}
          </div>
          <div>
            <div className="font-headline font-semibold text-base text-text-primary flex items-center gap-2.5">
              <span>{getTaskTitle(response.task)}</span>
              <span className="text-text-muted text-xs font-normal">• {timestamp}</span>
            </div>
          </div>
        </div>

        {/* Right Controls: Confidence & Export Action Group */}
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
          {/* Confidence Badge */}
          <div
            className={`flex items-center gap-1.5 px-3 py-1.5 border text-xs font-medium rounded-full ${
              isHighConfidence
                ? 'bg-amber-signal/10 border-amber-signal/40 text-amber-signal'
                : 'bg-red-delta/10 border-red-delta/40 text-red-delta'
            }`}
          >
            {isHighConfidence ? (
              <ShieldCheck className="w-4 h-4" />
            ) : (
              <AlertTriangle className="w-4 h-4" />
            )}
            <span>{confidencePercent}% Confidence</span>
          </div>

          {/* Export Action Buttons */}
          <div className="flex items-center gap-1 bg-surface-variant/70 border border-grid-hairline p-1 rounded-xl shadow-xs">
            <button
              type="button"
              onClick={() => exportMissionPDF(response, sourceImages, timestamp)}
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-text-primary hover:text-primary hover:bg-surface-container rounded-lg transition-colors cursor-pointer"
              title="Download print-ready PDF Mission Analysis Report"
            >
              <FileDown className="w-3.5 h-3.5 text-primary" />
              <span>PDF Report</span>
            </button>

            {hasGeospatialData && (
              <button
                type="button"
                onClick={() => exportGeoJSON(response, sourceImages)}
                className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-cyan-detection hover:bg-cyan-detection/10 rounded-lg transition-colors cursor-pointer"
                title="Export WGS84 GeoJSON layer for QGIS / ArcGIS"
              >
                <Compass className="w-3.5 h-3.5" />
                <span>GeoJSON</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => exportReportJSON(response, sourceImages)}
              className="p-1.5 text-text-muted hover:text-text-primary hover:bg-surface-container rounded-lg transition-colors cursor-pointer"
              title="Export Machine-Readable JSON Analysis"
            >
              <FileCode className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Report Content Body */}
      <div className="p-6 flex flex-col gap-5">
        {/* Natural-Language Answer Text */}
        <div className="text-base leading-relaxed text-text-primary bg-surface-container/30 p-4 border-l-3 border-primary rounded-xl shadow-xs">
          {response.answer || 'Analysis complete. Visual results are shown below.'}
        </div>

        {/* Unverified Band Ordering Warning */}
        {response.execution_summary?.parameters?.band_resolution_warning && (
          <div className="flex items-start gap-2.5 p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-300 text-xs">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-amber-200">Band Order Unverified: </span>
              <span className="opacity-90">{String(response.execution_summary.parameters.band_resolution_warning)}</span>
            </div>
          </div>
        )}

        {/* Multi-Image Interactive Split Slider (For Change Detection & Fusion) */}
        {sourceImages.length === 2 && safePrimaryUrl && safeSecondaryUrl && (
          <div className="flex flex-col gap-3">
            <div className="text-xs font-semibold text-text-muted uppercase tracking-wider flex items-center gap-2">
              <GitCompare className="w-4 h-4 text-primary" />
              <span>Multi-Observation Synchronized Comparison</span>
            </div>

            <DualImageSplitSlider
              primaryUrl={safePrimaryUrl}
              secondaryUrl={safeSecondaryUrl}
              primaryLabel={primaryImage?.name ? `${primaryImage.name} (${primaryImage.modality || 'T1'})` : 'Capture T1 (Optical)'}
              secondaryLabel={secondaryImage?.name ? `${secondaryImage.name} (${secondaryImage.modality || 'T2'})` : 'Capture T2 (Comparison)'}
              overlayUrl={
                response.visual_evidence?.mask_base64
                  ? response.visual_evidence.mask_base64.startsWith('data:')
                    ? response.visual_evidence.mask_base64
                    : `data:image/png;base64,${response.visual_evidence.mask_base64}`
                  : undefined
              }
              task={response.task}
            />
          </div>
        )}

        {/* Visual Evidence Viewports */}
        {hasVisualEvidence ? (
          <div className="flex flex-col gap-3">
            <div className="text-xs font-semibold text-text-muted uppercase tracking-wider flex items-center gap-2">
              <Scan className="w-4 h-4 text-cyan-detection" />
              <span>Visual Detection & Map Overlays</span>
            </div>
            
            <CoordinateTickFrame
              imageUrl={safePrimaryUrl}
              visualEvidence={response.visual_evidence}
              modality={primaryImage?.modality}
              date={primaryImage?.date}
              caption={primaryImage?.name || 'Satellite Imagery Viewport'}
            />
          </div>
        ) : sourceImages.length === 1 && safePrimaryUrl ? (
          /* Plain image display for single-image VQA/Captioning */
          <div className="flex flex-col gap-3">
            <CoordinateTickFrame
              imageUrl={safePrimaryUrl}
              modality={primaryImage?.modality}
              date={primaryImage?.date}
              caption={primaryImage?.name || 'Input Imagery'}
            />
          </div>
        ) : null}
      </div>

      {/* Execution Trace Panel */}
      {response.execution_summary && (
        <ExecutionSummaryPanel summary={response.execution_summary} />
      )}
    </div>
  );
};
