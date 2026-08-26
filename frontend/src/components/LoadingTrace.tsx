import React, { useEffect, useState } from 'react';
import { Check, Loader2, Sparkles } from 'lucide-react';

interface LoadingTraceProps {
  currentStep?: string;
  taskHint?: string;
}

const STEPS = [
  'Inspecting satellite imagery and coordinates',
  'Understanding question and selecting analysis model',
  'Running AI visual intelligence analysis',
  'Generating highlights and bounding overlays',
  'Finalizing findings and summary report',
];

export const LoadingTrace: React.FC<LoadingTraceProps> = () => {
  const [activeStep, setActiveStep] = useState(0);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setSeconds((prev) => prev + 1);
    }, 1000);

    const stepInterval = setInterval(() => {
      setActiveStep((prev) => (prev < STEPS.length - 1 ? prev + 1 : prev));
    }, 4000);

    return () => {
      clearInterval(timer);
      clearInterval(stepInterval);
    };
  }, []);

  return (
    <div className="w-full bg-surface-panel border border-grid-hairline p-5 rounded-2xl shadow-sm text-sm text-text-primary">
      <div className="flex items-center justify-between pb-3 mb-4 border-b border-grid-hairline">
        <div className="flex items-center gap-2 text-primary font-semibold tracking-wide text-xs">
          <Sparkles className="w-4 h-4 text-amber-signal animate-spin-slow" />
          <span>Analyzing Satellite Data</span>
        </div>
        <div className="text-text-muted text-xs font-mono">
          Elapsed: <span className="text-cyan-detection font-bold">{seconds}s</span>
        </div>
      </div>

      <div className="flex flex-col gap-3 pl-3 border-l-2 border-primary/30">
        {STEPS.map((step, idx) => {
          const isDone = idx < activeStep;
          const isCurrent = idx === activeStep;

          return (
            <div
              key={idx}
              className={`flex items-center gap-3 transition-all duration-300 ${
                isDone
                  ? 'text-emerald-sensor'
                  : isCurrent
                  ? 'text-amber-signal font-medium'
                  : 'text-text-muted/50'
              }`}
            >
              {isDone ? (
                <Check className="w-4 h-4 flex-shrink-0" />
              ) : isCurrent ? (
                <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />
              ) : (
                <span className="w-4 h-4 inline-block border border-current rounded-full flex-shrink-0 opacity-40 scale-50" />
              )}
              <span className="text-xs truncate">{step}</span>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-3 text-xs text-text-muted flex justify-between items-center border-t border-grid-hairline/40">
        <span>High-resolution processing</span>
        <span className="animate-pulse text-cyan-detection font-medium">Synthesizing answer and visual results...</span>
      </div>
    </div>
  );
};
