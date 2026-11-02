import React from 'react';
import { Modality, TaskType } from '../types/contract';
import { 
  X, 
  ArrowRight,
  Sparkles
} from 'lucide-react';

/** One bundled sample image, served from frontend/public/samples/ (see scripts/build_demo_samples.py). */
export interface PresetSample {
  file: string;
  modality: Modality;
  date?: string;
}

export interface DemoPreset {
  id: string;
  title: string;
  task: TaskType;
  category: string;
  query: string;
  description: string;
  samples: PresetSample[];
}

export const SAMPLES_BASE = '/samples/';

// Every preset runs on the repo's sample_data imagery, uploaded like a user's file,
// so answers, boxes and map coordinates match what the question asks about.
export const DEMO_PRESETS: DemoPreset[] = [
  {
    id: 'preset-caption',
    title: 'Scene Description',
    task: 'captioning',
    category: 'Sentinel-2',
    query: 'Describe this scene.',
    description: 'A real Sentinel-2 true-colour tile, summarised in plain language.',
    samples: [{ file: 'real_sentinel2_austria_tci.tif', modality: 'optical' }],
  },
  {
    id: 'preset-vqa',
    title: 'Object Counting & Question Answering',
    task: 'vqa',
    category: 'Visual Q&A',
    query: 'How many ships are in the harbour?',
    description: 'Ask any question about items, facilities, or terrain in a satellite image.',
    samples: [{ file: 'optical_port_rotterdam.tif', modality: 'optical' }],
  },
  {
    id: 'preset-bbox',
    title: 'Object & Facility Localization',
    task: 'detection',
    category: 'Target Finding',
    query: 'Locate all aircraft on the airbase.',
    description: 'Find and pinpoint specific objects with bounding boxes and map coordinates.',
    samples: [{ file: 'optical_airbase_runway.tif', modality: 'optical' }],
  },
  {
    id: 'preset-seg',
    title: 'Water & Land Cover Highlight',
    task: 'detection',
    category: 'Precision Mapping',
    query: 'Highlight the water bodies in this image.',
    description: 'Pixel-level overlay of lakes, rivers or flood zones (JPEG 2000 input).',
    samples: [{ file: 'optical_sentinel2_lake.jp2', modality: 'optical' }],
  },
  {
    id: 'preset-change',
    title: 'Temporal Change Detection',
    task: 'change_detection',
    category: 'Monitoring',
    query: 'What changed between these two dates, and where did new construction occur?',
    description: 'Compare two captures of the same location over time to spot developments.',
    samples: [
      { file: 'urban_expansion_t1_2021.tif', modality: 'optical', date: '2021-01-01' },
      { file: 'urban_expansion_t2_2024.tif', modality: 'optical', date: '2024-01-01' },
    ],
  },
  {
    id: 'preset-fusion',
    title: 'Optical + Radar (SAR) Fusion',
    task: 'fusion',
    category: 'All-Weather',
    query: 'Use optical and radar images together to classify land cover under the clouds.',
    description: 'Combines optical imagery with penetrating radar data to see through cloud cover.',
    samples: [
      { file: 'cloudy_optical_scene.tif', modality: 'optical' },
      { file: 'penetrating_sar_scene.tif', modality: 'sar' },
    ],
  },
];

interface DemoPresetSelectorProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectPreset: (preset: DemoPreset) => void;
}

export const DemoPresetSelector: React.FC<DemoPresetSelectorProps> = ({
  isOpen,
  onClose,
  onSelectPreset,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="bg-surface-panel border border-grid-hairline w-full max-w-3xl rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-grid-hairline bg-surface-container/80">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-headline text-lg font-bold text-text-primary">
                Explore Sample Scenarios
              </h2>
              <p className="text-xs text-text-muted">
                Choose a pre-configured satellite analysis to test the capabilities instantly
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-text-muted hover:text-text-primary hover:bg-surface-variant rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Presets List */}
        <div className="overflow-y-auto p-6 flex flex-col gap-3.5">
          {DEMO_PRESETS.map((preset) => (
            <div
              key={preset.id}
              onClick={() => {
                onSelectPreset(preset);
                onClose();
              }}
              className="group p-4 bg-surface-container/50 hover:bg-surface-variant/70 border border-grid-hairline hover:border-primary/60 transition-all rounded-xl cursor-pointer flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm hover:shadow-md"
            >
              <div className="flex flex-col gap-1 flex-1">
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-0.5 bg-primary/10 text-primary text-[11px] font-medium rounded-full">
                    {preset.category}
                  </span>
                  <span className="text-text-muted text-xs">
                    {preset.samples.length === 1 
                      ? '1 Image' 
                      : `2 Images (${preset.samples.map(i => i.modality.toUpperCase()).join(' + ')})`}
                  </span>
                </div>
                <h3 className="font-headline font-semibold text-base text-text-primary group-hover:text-primary transition-colors mt-0.5">
                  {preset.title}
                </h3>
                <p className="text-xs text-text-muted leading-relaxed">
                  {preset.description}
                </p>
                <div className="text-xs text-primary font-medium mt-1 bg-surface-panel/80 px-2.5 py-1.5 rounded-md border border-grid-hairline/60 inline-block max-w-xl truncate">
                  "{preset.query}"
                </div>
              </div>

              <button
                type="button"
                className="flex items-center gap-2 px-4 py-2 bg-primary-container text-on-primary-container text-xs font-semibold rounded-lg group-hover:bg-primary transition-colors whitespace-nowrap shadow-sm"
              >
                <span>Try Scenario</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-grid-hairline bg-surface-container/60 flex justify-between items-center text-xs text-text-muted">
          <span>{DEMO_PRESETS.length} ready-to-use analyses on bundled sample imagery</span>
          <button
            type="button"
            onClick={onClose}
            className="hover:text-text-primary font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

