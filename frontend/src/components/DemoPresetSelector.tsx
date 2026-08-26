import React from 'react';
import { QueryImage, TaskType } from '../types/contract';
import { 
  X, 
  ArrowRight,
  Sparkles
} from 'lucide-react';

export interface DemoPreset {
  id: string;
  title: string;
  task: TaskType;
  category: string;
  query: string;
  description: string;
  images: QueryImage[];
}

export const DEMO_PRESETS: DemoPreset[] = [
  {
    id: 'preset-vqa',
    title: 'Object Counting & Question Answering',
    task: 'vqa',
    category: 'Visual Q&A',
    query: 'How many aircraft are parked on the military tarmac?',
    description: 'Ask any question about items, facilities, or terrain in a satellite photo.',
    images: [
      {
        id: 'img1',
        modality: 'optical',
        date: '2024-06-15',
        name: 'Airbase_Optical.tif',
        url_or_base64: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?q=80&w=1200&auto=format&fit=crop',
        previewUrl: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?q=80&w=1200&auto=format&fit=crop',
      },
    ],
  },
  {
    id: 'preset-bbox',
    title: 'Object & Facility Localization',
    task: 'detection',
    category: 'Target Finding',
    query: 'Where is the main reservoir and water body in this sector?',
    description: 'Find and pinpoint coordinates of specific landmarks with bounding boxes.',
    images: [
      {
        id: 'img1',
        modality: 'optical',
        date: '2024-05-10',
        name: 'Reservoir_Sector.tif',
        url_or_base64: 'https://images.unsplash.com/photo-1508873696983-2df5293cb32f?q=80&w=1200&auto=format&fit=crop',
        previewUrl: 'https://images.unsplash.com/photo-1508873696983-2df5293cb32f?q=80&w=1200&auto=format&fit=crop',
      },
    ],
  },
  {
    id: 'preset-seg',
    title: 'Water & Land Cover Highlight',
    task: 'detection',
    category: 'Precision Mapping',
    query: 'Highlight all coastal water bodies and flooded zones in this image.',
    description: 'Generates detailed colored pixel overlays on lakes, rivers, forests, or flood zones.',
    images: [
      {
        id: 'img1',
        modality: 'optical',
        date: '2024-08-01',
        name: 'Coastal_Zone.tif',
        url_or_base64: 'https://images.unsplash.com/photo-1524661135-423995f22d0b?q=80&w=1200&auto=format&fit=crop',
        previewUrl: 'https://images.unsplash.com/photo-1524661135-423995f22d0b?q=80&w=1200&auto=format&fit=crop',
      },
    ],
  },
  {
    id: 'preset-change',
    title: 'Temporal Change Detection',
    task: 'change_detection',
    category: 'Monitoring',
    query: 'What changed between these two dates, and where did new construction or land clearing occur?',
    description: 'Compare two satellite captures of the same location over time to spot developments.',
    images: [
      {
        id: 'img1',
        modality: 'optical',
        date: '2023-01-15',
        name: 'Earlier_Date_2023.tif',
        url_or_base64: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?q=80&w=1200&auto=format&fit=crop',
        previewUrl: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?q=80&w=1200&auto=format&fit=crop',
      },
      {
        id: 'img2',
        modality: 'optical',
        date: '2024-03-02',
        name: 'Recent_Date_2024.tif',
        url_or_base64: 'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?q=80&w=1200&auto=format&fit=crop',
        previewUrl: 'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?q=80&w=1200&auto=format&fit=crop',
      },
    ],
  },
  {
    id: 'preset-fusion',
    title: 'Optical + Radar (SAR) Fusion',
    task: 'fusion',
    category: 'All-Weather',
    query: 'Use optical and radar images together to identify built-up structures and water penetration through cloud cover.',
    description: 'Combines optical imagery with penetrating radar data to see through cloud cover.',
    images: [
      {
        id: 'img1',
        modality: 'optical',
        date: '2024-07-20',
        name: 'Optical_Cloudy.tif',
        url_or_base64: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=1200&auto=format&fit=crop',
        previewUrl: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=1200&auto=format&fit=crop',
      },
      {
        id: 'img2',
        modality: 'sar',
        date: '2024-07-20',
        name: 'Radar_SAR_Band.tif',
        url_or_base64: 'https://images.unsplash.com/photo-1541185933-ef5d8ed016c2?q=80&w=1200&auto=format&fit=crop',
        previewUrl: 'https://images.unsplash.com/photo-1541185933-ef5d8ed016c2?q=80&w=1200&auto=format&fit=crop',
      },
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
                    {preset.images.length === 1 
                      ? '1 Image' 
                      : `2 Images (${preset.images.map(i => i.modality.toUpperCase()).join(' + ')})`}
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
          <span>5 ready-to-use analysis demonstrations</span>
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

