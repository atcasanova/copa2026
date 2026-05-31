import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#10b981', // Emerald Green (World Cup Grass / Vibrant sport vibe)
      light: '#34d399',
      dark: '#059669',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#fbbf24', // Warm Gold (Copa/Champion theme)
      light: '#fcd34d',
      dark: '#d97706',
      contrastText: '#0f172a',
    },
    background: {
      default: '#0b0f19', // Sleek deep space dark background
      paper: '#111827', // Slate gray cards/surfaces
    },
    text: {
      primary: '#f8fafc', // Clean off-white
      secondary: '#94a3b8', // Muted slate gray
    },
    divider: '#1f2937',
    info: {
      main: '#3b82f6',
    },
    warning: {
      main: '#f59e0b',
    },
    error: {
      main: '#ef4444',
    },
    success: {
      main: '#10b981',
    },
  },
  typography: {
    fontFamily: '"Inter", "Outfit", "Helvetica", "Arial", sans-serif',
    h1: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 800,
    },
    h2: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 700,
    },
    h3: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 700,
    },
    h4: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 600,
    },
    h5: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 600,
    },
    h6: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 600,
    },
    subtitle1: {
      fontFamily: '"Inter", sans-serif',
      fontWeight: 500,
    },
    body1: {
      fontFamily: '"Inter", sans-serif',
      lineHeight: 1.6,
    },
    button: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 600,
      textTransform: 'none', // Remove rigid uppercase buttons
    },
  },
  shape: {
    borderRadius: 12, // Smooth Material-3 styled corners
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 24, // Pill buttons
          padding: '8px 20px',
          transition: 'all 0.2s ease-in-out',
          '&:hover': {
            transform: 'translateY(-1px)',
            boxShadow: '0 4px 12px rgba(16, 185, 129, 0.25)',
          },
        },
        containedSecondary: {
          '&:hover': {
            boxShadow: '0 4px 12px rgba(251, 191, 36, 0.3)',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none', // Remove default paper overlay gradients
          boxShadow: '0 4px 20px 0 rgba(0, 0, 0, 0.3)',
          border: '1px solid #1f2937',
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottom: '1px solid #1f2937',
          padding: '12px 16px',
        },
        head: {
          backgroundColor: '#111827',
          fontWeight: 600,
        },
      },
    },
  },
});

export default theme;
