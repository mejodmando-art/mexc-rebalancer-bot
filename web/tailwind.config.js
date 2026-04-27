/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        base:    '#0D1117',
        card:    '#161B2A',
        input:   '#1E2436',
        border:  '#388BFD26',
        primary:   '#E6EDF3',
        secondary: '#7D8590',
        brand:   '#388BFD',
        accent:  '#2DD4BF',
        'accent-dark': '#14B8A6',
        profit: '#3FB950',
        loss:   '#F85149',
        'light-base':  '#F0F4F8',
        'light-card':  '#FFFFFF',
        'light-input': '#EEF2F7',
        'light-border':'#D0D7DE',
      },
      fontFamily: {
        sans:  ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono:  ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        card:  '0 8px 24px rgba(0,0,0,0.4)',
        glow:  '0 0 20px rgba(0,212,170,0.25)',
        'glow-sm': '0 0 10px rgba(0,212,170,0.15)',
      },
      animation: {
        'fade-up':    'fadeUp 0.3s ease-out',
        'fade-in':    'fadeIn 0.2s ease-out',
        'slide-in':   'slideIn 0.3s ease-out',
        'pulse-dot':  'pulseDot 2s ease-in-out infinite',
        'shimmer':    'shimmer 1.5s infinite',
      },
      keyframes: {
        fadeUp:   { from: { opacity: '0', transform: 'translateY(12px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        fadeIn:   { from: { opacity: '0' }, to: { opacity: '1' } },
        slideIn:  { from: { opacity: '0', transform: 'translateX(-12px)' }, to: { opacity: '1', transform: 'translateX(0)' } },
        pulseDot: { '0%,100%': { opacity: '1', transform: 'scale(1)' }, '50%': { opacity: '0.5', transform: 'scale(0.8)' } },
        shimmer:  { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
      },
    },
  },
  plugins: [],
};
