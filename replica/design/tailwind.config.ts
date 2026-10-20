// tailwind.config.ts (theme.extend); values come from tokens.css, never raw hex in components
import type { Config } from 'tailwindcss'
export default {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg': 'var(--color-bg)',
        'surface': 'var(--color-surface)',
        'surface-raised': 'var(--color-surface-raised)',
        'border': 'var(--color-border)',
        'border-input': 'var(--color-border-input)',
        'text': 'var(--color-text)',
        'text-muted': 'var(--color-text-muted)',
        'accent': 'var(--color-accent)',
        'accent-hover': 'var(--color-accent-hover)',
        'on-accent': 'var(--color-on-accent)',
        'accent-subtle': 'var(--color-accent-subtle)',
        'danger': 'var(--color-danger)',
        'danger-subtle': 'var(--color-danger-subtle)',
        'success': 'var(--color-success)',
        'success-subtle': 'var(--color-success-subtle)',
        'warning': 'var(--color-warning)',
        'warning-subtle': 'var(--color-warning-subtle)',
        'nav-bg': 'var(--color-nav-bg)',
        'nav-text': 'var(--color-nav-text)',
        'nav-active': 'var(--color-nav-active)'
      },
      fontFamily: { sans: 'var(--font-sans)', mono: 'var(--font-mono)' },
      borderRadius: { sm: 'var(--radius-sm)', md: 'var(--radius-md)', lg: 'var(--radius-lg)' },
      boxShadow: { card: 'var(--shadow-card)', pop: 'var(--shadow-pop)' },
      maxWidth: { content: 'var(--layout-content-max)', marketing: 'var(--layout-marketing-max)', prose: 'var(--layout-prose-max)' },
    },
  },
} satisfies Config
