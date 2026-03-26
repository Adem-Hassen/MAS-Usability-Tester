/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      fontFamily: {
        sans:  ['var(--font-sans)', 'sans-serif'],
        mono:  ['var(--font-mono)', 'monospace'],
        display: ['var(--font-display)', 'sans-serif'],
      },
      colors: {
        ink:    { DEFAULT: '#1a1a18', 50: '#f8f7f4', 100: '#f1efe9', 200: '#e8e2d8', 300: '#c8c0b0', 400: '#9a9282', 500: '#7a7770', 600: '#5f5e5a', 700: '#444441', 800: '#2c2c2a', 900: '#1a1a18' },
        amber:  { DEFAULT: '#c8a96e', light: '#e8c98e', dark: '#a07840' },
        teal:   { DEFAULT: '#2d4a3e', light: '#3d6a54', dark: '#1a2e26' },
        danger: { DEFAULT: '#c0392b', light: '#e74c3c' },
        ok:     { DEFAULT: '#2e7d52', light: '#3d9a68' },
      },
      animation: {
        'slide-up':   'slideUp 0.4s cubic-bezier(0.16,1,0.3,1)',
        'fade-in':    'fadeIn 0.3s ease',
        'pulse-dot':  'pulseDot 1.4s ease-in-out infinite',
        'scan':       'scan 2s linear infinite',
      },
      keyframes: {
        slideUp:   { from: { transform: 'translateY(12px)', opacity: 0 }, to: { transform: 'translateY(0)', opacity: 1 } },
        fadeIn:    { from: { opacity: 0 }, to: { opacity: 1 } },
        pulseDot:  { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.3 } },
        scan:      { '0%': { transform: 'translateY(-100%)' }, '100%': { transform: 'translateY(400%)' } },
      },
    },
  },
  plugins: [],
};
