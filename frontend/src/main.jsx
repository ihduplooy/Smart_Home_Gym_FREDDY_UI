import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Provider } from 'react-redux'
import { PersistGate } from 'redux-persist/integration/react'
import { ChakraProvider, extendTheme, LightMode } from '@chakra-ui/react'
import { store, persistor } from './store'
import './index.css'
import App from './App.jsx'

const theme = extendTheme({
  config: {
    initialColorMode: 'light',
    useSystemColorMode: false,
  },
  fonts: {
    heading: `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`,
    body: `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`,
    mono: `'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace`,
  },
  radii: {
    md: '4px',
    lg: '6px',
  },
  styles: {
    global: {
      body: {
        bg: '#FFFFFF',
        color: '#18181B',
      },
    },
  },
  colors: {
    gray: {
      650: '#3a4453',
      750: '#222831',
      850: '#16191f',
    },
    odrive: {
      50: '#e6fffa',
      100: '#b3f5ec',
      200: '#81e6d9',
      300: '#4fd1c7',
      400: '#38b2ac',
      500: '#0d7377',
      600: '#0a5d61',
      700: '#08474a',
      800: '#053134',
      900: '#021b1d',
    },
    // UI redesign sub-phase 1 (Setup tab prototype only, see docs/decisions.md) --
    // additive, not consumed anywhere outside the Setup tab's own components.
    accent: {
      50: '#eff6ff',
      100: '#dbeafe',
      200: '#bfdbfe',
      300: '#93c5fd',
      400: '#60a5fa',
      500: '#3b82f6',
      600: '#2563eb',
      700: '#1d4ed8',
      800: '#1e40af',
      900: '#1e3a8a',
    },
    tag: {
      50: '#fffbeb',
      100: '#fef3c7',
      200: '#fde68a',
      300: '#fcd34d',
      400: '#fbbf24',
      500: '#f59e0b',
      600: '#d97706',
      700: '#b45309',
      800: '#92400e',
      900: '#78350f',
    },
    paper: {
      bg: '#FFFFFF',
      textPrimary: '#18181B',
      textSecondary: '#71717A',
      border: '#E4E4E7',
    },
  },
  components: {
    // Chakra's default disabled-state treatment is `opacity: 0.4` on every
    // interactive component (Button/Input/Select/Checkbox/Switch/...) --
    // that reads fine blended into a dark background, but on this app's
    // white background it washes disabled controls out to near-invisible
    // (flagged directly from a screenshot during the light-theme roll-out).
    // Raised to 0.6 wherever Chakra bakes the same `_disabled: { opacity:
    // 0.4 }` block into its own component theme, so a disabled control is
    // still clearly legible rather than just technically present.
    Button: {
      baseStyle: {
        fontWeight: 600,
        letterSpacing: '0.01em',
        borderRadius: 'full',
        _disabled: { opacity: 0.6 },
      },
      // Chakra's default outline variant borders a "gray" button in
      // `gray.200` -- barely visible on white, which undermines this app's
      // whole "structure comes from the border" look (also flagged directly
      // from a screenshot). Re-implemented (not just tweaked) since Chakra's
      // own outline variant is a style function extendTheme can only
      // replace wholesale, not deep-merge into.
      variants: {
        outline: (props) => {
          const { colorScheme: c } = props
          if (c === 'gray') {
            return {
              border: '1.5px solid',
              borderColor: 'gray.300',
              color: 'paper.textPrimary',
              _hover: { bg: 'gray.50' },
              _active: { bg: 'gray.100' },
            }
          }
          return {
            border: '1.5px solid',
            borderColor: `${c}.600`,
            color: `${c}.600`,
            _hover: { bg: `${c}.50` },
            _active: { bg: `${c}.100` },
          }
        },
      },
      defaultProps: { colorScheme: 'accent' },
    },
    Input: {
      baseStyle: { field: { _disabled: { opacity: 0.6 } } },
    },
    NumberInput: {
      baseStyle: { field: { _disabled: { opacity: 0.6 } } },
    },
    Select: {
      baseStyle: { field: { _disabled: { opacity: 0.6 } } },
    },
    Checkbox: {
      baseStyle: { control: { _disabled: { opacity: 0.6 } } },
    },
    Switch: {
      baseStyle: { track: { _disabled: { opacity: 0.6 } } },
    },
    Badge: {
      baseStyle: { borderRadius: 'full' },
    },
    Heading: {
      baseStyle: { letterSpacing: '-0.01em' },
    },
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Provider store={store}>
      <PersistGate loading={null} persistor={persistor}>
        <ChakraProvider theme={theme}>
          {/* This app dropped dark mode entirely in the light-theme UI
              redesign -- `initialColorMode: 'light'` above only picks the
              INITIAL mode, but Chakra's ColorModeProvider still prefers
              whatever's cached in this browser's localStorage
              (`chakra-ui-color-mode`) from any earlier dark-mode session,
              which silently pulls every un-overridden Chakra default
              (button/badge/alert variants, etc.) back onto their dark-mode
              branch -- e.g. an outline button's text reading `orange.200`
              (pale) instead of `orange.600` (solid), which is exactly what
              got flagged as "low contrast" from a real screenshot. Locking
              the whole app in <LightMode> makes every `mode(light, dark)`
              call resolve to light unconditionally, regardless of what's
              cached from before. */}
          <LightMode>
            <App />
          </LightMode>
        </ChakraProvider>
      </PersistGate>
    </Provider>
  </StrictMode>,
)