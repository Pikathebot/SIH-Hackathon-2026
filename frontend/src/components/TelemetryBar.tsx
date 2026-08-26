import React, { useEffect, useState } from 'react';
import { useTheme } from '../context/ThemeContext';
import { checkHealth } from '../services/api';
import { HealthResponse } from '../types/contract';
import { Sun, Moon, Sparkles, Menu, Wifi, WifiOff } from 'lucide-react';

interface TelemetryBarProps {
  onToggleSidebar?: () => void;
  onOpenPresets?: () => void;
}

export const TelemetryBar: React.FC<TelemetryBarProps> = ({
  onToggleSidebar,
  onOpenPresets,
}) => {
  const { theme, toggleTheme } = useTheme();
  const [timeStr, setTimeStr] = useState('');
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      const h = now.getUTCHours().toString().padStart(2, '0');
      const m = now.getUTCMinutes().toString().padStart(2, '0');
      const s = now.getUTCSeconds().toString().padStart(2, '0');
      setTimeStr(`${h}:${m}:${s} UTC`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const poll = async () => {
      try {
        setHealth(await checkHealth());
      } catch {
        setHealth({ status: 'offline', rsunivlm_loaded: false, fusion_loaded: false });
      }
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => clearInterval(id);
  }, []);

  const online = health?.status === 'ok';

  return (
    <header className="fixed top-0 left-0 md:left-[280px] right-0 z-40 h-[52px] flex items-center justify-between px-4 md:px-6 bg-surface-panel/95 backdrop-blur-md border-b border-grid-hairline">
      {/* Left: mobile hamburger + live UTC clock */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onToggleSidebar}
          className="md:hidden p-2 text-text-muted hover:text-text-primary hover:bg-surface-variant rounded-lg transition-colors"
          aria-label="Open menu"
        >
          <Menu className="w-4 h-4" />
        </button>

        <div className="hidden sm:flex items-center gap-2 text-xs text-text-muted font-mono">
          <span className={`w-1.5 h-1.5 rounded-full ${online ? 'bg-emerald-sensor animate-pulse' : 'bg-amber-signal'}`} />
          <span>{timeStr}</span>
        </div>
      </div>

      {/* Right: contextual controls */}
      <div className="flex items-center gap-2">
        {onOpenPresets && (
          <button
            type="button"
            onClick={onOpenPresets}
            className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-surface-container hover:bg-surface-variant border border-grid-hairline text-text-primary text-xs font-medium rounded-lg transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-signal" />
            <span>Sample Questions</span>
          </button>
        )}

        <div className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 border rounded-lg text-xs ${
          online
            ? 'bg-emerald-sensor/10 border-emerald-sensor/30 text-emerald-sensor'
            : 'bg-amber-signal/10 border-amber-signal/30 text-amber-signal'
        }`}>
          {online ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
          <span>{online ? 'AI Online' : 'AI Offline'}</span>
        </div>

        <button
          type="button"
          onClick={toggleTheme}
          className="flex items-center gap-1.5 p-2 text-text-muted hover:text-text-primary hover:bg-surface-variant border border-grid-hairline rounded-lg transition-colors"
          title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {theme === 'dark'
            ? <Sun className="w-4 h-4 text-amber-signal" />
            : <Moon className="w-4 h-4 text-primary" />}
        </button>
      </div>
    </header>
  );
};
