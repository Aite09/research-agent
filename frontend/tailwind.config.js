/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Outfit', 'system-ui', 'sans-serif'],
        body:    ['Fira Sans', 'system-ui', 'sans-serif'],
        mono:    ['Fira Code', 'monospace'],
      },
      colors: {
        bg:      '#020617',
        surface: '#0a0f1e',
        card:    '#0d1426',
        border:  'rgba(255,255,255,0.07)',
        accent:  '#22C55E',
      },
      animation: {
        'orb-1':      'orbFloat1 18s ease-in-out infinite',
        'orb-2':      'orbFloat2 22s ease-in-out infinite',
        'orb-3':      'orbFloat3 26s ease-in-out infinite',
        'pulse-ring': 'pulseRing 2s cubic-bezier(0.4,0,0.6,1) infinite',
        'slide-up':   'slideUp 0.6s cubic-bezier(0.32,0.72,0,1) both',
        'fade-in':    'fadeIn 0.5s ease both',
        'shimmer':    'shimmer 2.2s linear infinite',
        'draw-line':  'drawLine 0.6s cubic-bezier(0.32,0.72,0,1) both',
        'bounce-in':  'bounceIn 0.5s cubic-bezier(0.34,1.56,0.64,1) both',
        'marquee':    'marquee 32s linear infinite',
      },
      keyframes: {
        orbFloat1: {
          '0%,100%': { transform: 'translate(0,0) scale(1)' },
          '33%':     { transform: 'translate(60px,-40px) scale(1.08)' },
          '66%':     { transform: 'translate(-30px,50px) scale(0.95)' },
        },
        orbFloat2: {
          '0%,100%': { transform: 'translate(0,0) scale(1)' },
          '40%':     { transform: 'translate(-70px,30px) scale(1.1)' },
          '70%':     { transform: 'translate(40px,-60px) scale(0.92)' },
        },
        orbFloat3: {
          '0%,100%': { transform: 'translate(0,0) scale(1)' },
          '50%':     { transform: 'translate(50px,40px) scale(1.05)' },
        },
        pulseRing: {
          '0%,100%': { opacity: '1' },
          '50%':     { opacity: '0.4' },
        },
        slideUp: {
          from: { transform: 'translateY(24px)', opacity: '0', filter: 'blur(4px)' },
          to:   { transform: 'translateY(0)',    opacity: '1', filter: 'blur(0)' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        drawLine: {
          from: { transform: 'scaleY(0)', transformOrigin: 'top' },
          to:   { transform: 'scaleY(1)', transformOrigin: 'top' },
        },
        bounceIn: {
          from: { transform: 'scale(0.5)', opacity: '0' },
          to:   { transform: 'scale(1)',   opacity: '1' },
        },
        marquee: {
          '0%':   { transform: 'translateX(0%)' },
          '100%': { transform: 'translateX(-50%)' },
        },
      },
      transitionTimingFunction: {
        spring: 'cubic-bezier(0.32,0.72,0,1)',
        bounce: 'cubic-bezier(0.34,1.56,0.64,1)',
      },
      backgroundImage: {
        'noise': "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='1'/%3E%3C/svg%3E\")",
      },
    },
  },
  plugins: [],
}
