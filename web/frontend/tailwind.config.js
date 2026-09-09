const themed = (name) => ({ opacityValue = 1 }) =>
  `color-mix(in srgb, var(--studio-${name}) calc(${opacityValue} * 100%), transparent)`;
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: themed('background'),
        surface: {
          DEFAULT: themed('surface'),
          raised: themed('surface-raised'),
          card: themed('surface-card'),
        },
        border: {
          DEFAULT: themed('border'),
          light: themed('border-light'),
          glow: themed('border-glow'),
        },
        text: {
          primary: '#f8fafc',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
        brand: {
          DEFAULT: themed('brand'),
          hover: themed('brand-hover'),
          light: themed('brand-light'),
        },
        accent: {
          focus: themed('accent'),
        },
        status: {
          success: '#34d399',
          warning: '#fbbf24',
          error: '#f87171',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      borderRadius: {
        input: '10px',
        card: '16px',
      },
    },
  },
  plugins: [],
};
