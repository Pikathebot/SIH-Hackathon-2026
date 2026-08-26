import React, { createContext, useContext, useEffect, useState } from 'react';

export type ConsoleTheme = 'dark' | 'light';

interface ThemeContextType {
  theme: ConsoleTheme;
  themeName: string;
  themeSubtitle: string;
  toggleTheme: () => void;
  setTheme: (theme: ConsoleTheme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<ConsoleTheme>(() => {
    const saved = localStorage.getItem('satquery-console-theme');
    if (saved === 'dark' || saved === 'light') {
      return saved;
    }
    return 'dark';
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
      root.classList.remove('light');
    } else {
      root.classList.add('light');
      root.classList.remove('dark');
    }
    localStorage.setItem('satquery-console-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setThemeState((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const setTheme = (newTheme: ConsoleTheme) => {
    setThemeState(newTheme);
  };

  // User-friendly mode names (no internal dev terms)
  const themeName = theme === 'dark' ? 'Dark Mode' : 'Light Mode';
  const themeSubtitle = theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode';

  return (
    <ThemeContext.Provider
      value={{
        theme,
        themeName,
        themeSubtitle,
        toggleTheme,
        setTheme,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = (): ThemeContextType => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
