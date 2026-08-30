/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ── Semantic tokens (CSS variables, theme-aware) ────────────────────
        // Use these for new components so they automatically swap on theme.
        surface: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
          raised: 'rgb(var(--color-surface-raised) / <alpha-value>)',
          overlay: 'rgb(var(--color-surface-overlay) / <alpha-value>)',
          inverse: 'rgb(var(--color-surface-inverse) / <alpha-value>)',
        },
        content: {
          DEFAULT: 'rgb(var(--color-content) / <alpha-value>)',
          muted: 'rgb(var(--color-content-muted) / <alpha-value>)',
          subtle: 'rgb(var(--color-content-subtle) / <alpha-value>)',
          inverse: 'rgb(var(--color-content-inverse) / <alpha-value>)',
        },
        edge: {
          DEFAULT: 'rgb(var(--color-edge) / <alpha-value>)',
          strong: 'rgb(var(--color-edge-strong) / <alpha-value>)',
          subtle: 'rgb(var(--color-edge-subtle) / <alpha-value>)',
        },
        brand: {
          DEFAULT: 'rgb(var(--color-brand) / <alpha-value>)',
          hover: 'rgb(var(--color-brand-hover) / <alpha-value>)',
          soft: 'rgb(var(--color-brand-soft) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'rgb(var(--color-success) / <alpha-value>)',
          soft: 'rgb(var(--color-success-soft) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'rgb(var(--color-warning) / <alpha-value>)',
          soft: 'rgb(var(--color-warning-soft) / <alpha-value>)',
        },
        danger: {
          DEFAULT: 'rgb(var(--color-danger) / <alpha-value>)',
          soft: 'rgb(var(--color-danger-soft) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'rgb(var(--color-info) / <alpha-value>)',
          soft: 'rgb(var(--color-info-soft) / <alpha-value>)',
        },
        // ── Legacy palettes (kept for back-compat; do not extend in new UI) ──
        primary: {
          50: '#f3eeff',
          100: '#e8ddff',
          200: '#d5c2ff',
          300: '#bb9eff',
          400: '#9d70ff',
          500: '#845ec2',
          600: '#7044b3',
          700: '#5d3699',
          800: '#4a2b7a',
          900: '#3a2260',
        },
        secondary: {
          50: '#e6f2ff',
          100: '#cce5ff',
          200: '#99ccff',
          300: '#66b3ff',
          400: '#4d9aff',
          500: '#2c73d2',
          600: '#2461b3',
          700: '#1d4f99',
          800: '#163d7a',
          900: '#112f60',
        },
        accent: {
          cyan: '#0081cf',
          teal: '#0089ba',
          sea: '#008e9b',
          green: '#008f7a',
        },
        dark: {
          50: 'rgb(var(--dark-50) / <alpha-value>)',
          100: 'rgb(var(--dark-100) / <alpha-value>)',
          200: 'rgb(var(--dark-200) / <alpha-value>)',
          300: 'rgb(var(--dark-300) / <alpha-value>)',
          400: 'rgb(var(--dark-400) / <alpha-value>)',
          500: 'rgb(var(--dark-500) / <alpha-value>)',
          600: 'rgb(var(--dark-600) / <alpha-value>)',
          700: 'rgb(var(--dark-700) / <alpha-value>)',
          800: 'rgb(var(--dark-800) / <alpha-value>)',
          900: 'rgb(var(--dark-900) / <alpha-value>)',
          950: 'rgb(var(--dark-950) / <alpha-value>)',
        },
        // Override default `gray.*` scale so legacy hardcoded utilities
        // (bg-gray-800, text-gray-200, ...) become theme-aware. Values
        // are inverted in light mode via the CSS variables in index.css.
        gray: {
          50: 'rgb(var(--gray-50) / <alpha-value>)',
          100: 'rgb(var(--gray-100) / <alpha-value>)',
          200: 'rgb(var(--gray-200) / <alpha-value>)',
          300: 'rgb(var(--gray-300) / <alpha-value>)',
          400: 'rgb(var(--gray-400) / <alpha-value>)',
          500: 'rgb(var(--gray-500) / <alpha-value>)',
          600: 'rgb(var(--gray-600) / <alpha-value>)',
          700: 'rgb(var(--gray-700) / <alpha-value>)',
          800: 'rgb(var(--gray-800) / <alpha-value>)',
          900: 'rgb(var(--gray-900) / <alpha-value>)',
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-mesh': 'linear-gradient(135deg, #845ec2 0%, #2c73d2 100%)',
        'gradient-accent': 'linear-gradient(135deg, #0081cf 0%, #008f7a 100%)',
      },
      boxShadow: {
        'glow': '0 0 20px rgba(132, 94, 194, 0.3)',
        'glow-lg': '0 0 40px rgba(132, 94, 194, 0.4)',
        'glow-secondary': '0 0 20px rgba(44, 115, 210, 0.3)',
      },
    },
  },
  plugins: [],
}
