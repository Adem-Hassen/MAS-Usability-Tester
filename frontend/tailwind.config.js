/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        nexus: {
          bg: 'var(--nexus-bg)',
          primary: 'var(--nexus-primary)',
          'primary-on': 'var(--nexus-on-primary)',
          'primary-container': 'var(--nexus-primary-container)',
          secondary: 'var(--nexus-secondary)',
          tertiary: 'var(--nexus-tertiary)',
          error: 'var(--nexus-error)',
          surface: 'var(--nexus-surface)',
          'surface-variant': 'var(--nexus-surface-variant)',
          outline: 'var(--nexus-outline)',
          'outline-variant': 'var(--nexus-outline-variant)',
        },
      },
      fontFamily: {
        syne: ['var(--font-syne)', 'sans-serif'],
        sans: ['var(--font-dm-sans)', 'sans-serif'],
        mono: ['var(--font-jetbrains-mono)', 'monospace'],
      },
      spacing: {
        unit: '4px',
        sidebar: '260px',
        container: '24px',
        gutter: '16px',
      },
      borderRadius: {
        none: '0',
        sharp: '0',
        pill: '9999px',
      },
      animation: {
        'pulse-fast': 'pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'radial-pulse': 'radial-pulse 2s infinite',
      },
      keyframes: {
        'radial-pulse': {
          '0%': { boxShadow: '0 0 0 0 rgba(196, 192, 255, 0.4)' },
          '70%': { boxShadow: '0 0 0 10px rgba(196, 192, 255, 0)' },
          '100%': { boxShadow: '0 0 0 0 rgba(196, 192, 255, 0)' },
        },
      },
    },
  },
  plugins: [],
  darkMode: 'class',
};
