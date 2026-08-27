import tailwindcssAnimate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Geist Variable', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Space Grotesk Variable', 'Geist Variable', 'sans-serif'],
        mono: ['Geist Mono Variable', 'ui-monospace', 'monospace'],
      },
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        status: {
          done: 'hsl(var(--status-done))',
          running: 'hsl(var(--status-running))',
          failed: 'hsl(var(--status-failed))',
          idle: 'hsl(var(--status-idle))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 0.25rem)',
        sm: 'calc(var(--radius) - 0.4rem)',
      },
      boxShadow: {
        soft: '0 1px 2px 0 hsl(240 10% 4% / 0.04), 0 4px 16px -4px hsl(240 10% 4% / 0.08)',
        lift: '0 2px 4px 0 hsl(240 10% 4% / 0.05), 0 12px 32px -8px hsl(240 10% 4% / 0.16)',
        glow: '0 0 0 1px hsl(var(--primary) / 0.25), 0 8px 30px -8px hsl(var(--primary) / 0.35)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        'wave-bar': {
          '0%, 100%': { transform: 'scaleY(0.35)' },
          '50%': { transform: 'scaleY(1)' },
        },
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-ring': {
          '0%': { boxShadow: '0 0 0 0 hsl(var(--status-running) / 0.5)' },
          '70%': { boxShadow: '0 0 0 8px hsl(var(--status-running) / 0)' },
          '100%': { boxShadow: '0 0 0 0 hsl(var(--status-running) / 0)' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        shimmer: 'shimmer 1.6s infinite',
        'fade-up': 'fade-up 0.4s cubic-bezier(0.22, 1, 0.36, 1) both',
        'pulse-ring': 'pulse-ring 1.6s cubic-bezier(0.66, 0, 0, 1) infinite',
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
