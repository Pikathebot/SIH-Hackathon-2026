/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Core Theme Tokens
        background: 'var(--color-bg)',
        'surface-panel': 'var(--color-surface-panel)',
        'surface-container': 'var(--color-surface-container)',
        'surface-variant': 'var(--color-surface-variant)',
        'grid-hairline': 'var(--color-grid-hairline)',
        
        // Brand & Accents
        primary: 'var(--color-primary)',
        'primary-container': 'var(--color-primary-container)',
        'on-primary': 'var(--color-on-primary)',
        'on-primary-container': 'var(--color-on-primary-container)',
        
        // Specialized Indicators
        cyan: {
          detection: '#4FD6C4',
        },
        red: {
          delta: '#E85C4A',
        },
        amber: {
          signal: '#F2A93B',
        },
        emerald: {
          sensor: '#10B981',
        },

        // Text
        'text-primary': 'var(--color-text-primary)',
        'text-muted': 'var(--color-text-muted)',
      },
      fontFamily: {
        headline: ['"Space Grotesk"', 'sans-serif'],
        body: ['"IBM Plex Sans"', 'Inter', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
        telemetry: ['"IBM Plex Mono"', 'monospace'],
      },
      spacing: {
        'margin-page': '24px',
        gutter: '16px',
        unit: '4px',
        'sidebar-width': '280px',
      },
      borderRadius: {
        DEFAULT: '0.25rem', // 4px
        sm: '0.125rem',     // 2px
        md: '0.375rem',     // 6px
        lg: '0.5rem',       // 8px
      },
    },
  },
  plugins: [],
}
