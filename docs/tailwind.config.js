/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./docs/**/*.html",
    "./docs/**/*.js",
    "./docs/**/*.md"
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'Monaco', 'monospace'],
      },
      colors: {
        canvas: '#06080d',
        surface: '#0b0f17',
        surfaceElevated: '#111724',
        surfaceCard: '#151d2e',
        borderSubtle: '#1e293b',
        borderAccent: 'rgba(99, 102, 241, 0.3)',
        primaryAccent: '#6366f1',
        secondaryAccent: '#10b981',
        cyanAccent: '#06b6d4',
        amberAccent: '#f59e0b',
      },
      boxShadow: {
        'glow-primary': '0 0 40px -10px rgba(99, 102, 241, 0.35)',
        'glow-emerald': '0 0 40px -10px rgba(16, 185, 129, 0.35)',
        'glow-cyan': '0 0 40px -10px rgba(6, 182, 212, 0.35)',
      }
    }
  },
  plugins: [],
}
