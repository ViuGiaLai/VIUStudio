/**
 * Design tokens strictly following VIUStudio Web specification Section 5.2
 */
export const DESIGN_TOKENS = {
  colors: {
    pageBackground: '#0B1020',
    surface: '#121A2B',
    raisedSurface: '#192338',
    border: '#2B3850',
    primaryText: '#F1F5F9',
    secondaryText: '#A8B6CC',
    brandAccent: '#14B8A6',
    selectionFocus: '#818CF8',
    status: {
      success: '#34D399',
      warning: '#FBBF24',
      error: '#F87171',
    },
  },
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '24px',
    xxl: '32px',
  },
  radius: {
    input: '8px',
    card: '12px',
    dialog: '12px',
  },
  typography: {
    fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
    body: '14px',
    bodyLg: '16px',
    pageTitle: '26px',
  },
} as const;
