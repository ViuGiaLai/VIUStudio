import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { AppProvider } from './stores/useAppStore';
import './index.css';

let storedTheme: string | null = null;
try { storedTheme = localStorage.getItem('viustudio_studio_theme'); } catch { /* Storage may be disabled. */ }
if (storedTheme === 'cyber-neon' || storedTheme === 'midnight-oled' || storedTheme === 'sapphire-slate') {
  document.documentElement.dataset.studioTheme = storedTheme;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppProvider>
        <App />
      </AppProvider>
    </BrowserRouter>
  </React.StrictMode>
);
