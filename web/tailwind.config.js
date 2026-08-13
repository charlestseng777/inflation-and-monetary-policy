import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Content globs resolve against process.cwd(), not this file. Anchoring them
// here means the utility classes survive however the build is invoked — a
// cwd-relative glob silently yields an empty content set, which strips every
// utility class in the JSX while leaving @apply rules intact (so the page still
// renders, just with no layout).
const here = dirname(fileURLToPath(import.meta.url))

/** @type {import('tailwindcss').Config} */
export default {
  content: [join(here, 'index.html'), join(here, 'src/**/*.{js,jsx}')],
  theme: {
    extend: {
      colors: {
        canvas: '#0F1116',
        panel: '#161A23',
        raised: '#1C212C',
        hairline: '#252B38',
        ink: '#E8ECF4',
        muted: '#8A93A6',
        faint: '#5A6273',
      },
      fontFamily: {
        sans: ['"Inter var"', 'Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      keyframes: {
        'slide-in': {
          from: { transform: 'translateX(100%)', opacity: '0' },
          to: { transform: 'translateX(0)', opacity: '1' },
        },
        'fade-up': {
          from: { transform: 'translateY(6px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
      },
      animation: {
        'slide-in': 'slide-in 260ms cubic-bezier(0.22, 1, 0.36, 1)',
        'fade-up': 'fade-up 220ms ease-out',
      },
    },
  },
  plugins: [],
}
