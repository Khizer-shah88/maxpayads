import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#DC2626',
        'primary-dark': '#B91C1C',
        'primary-light': '#EF4444',
        secondary: '#1F2937',
        accent: '#F3F4F6',
        border: '#E5E7EB',
        'text-primary': '#000000',
        'text-secondary': '#4B5563',
        'text-muted': '#9CA3AF',
        dark: '#0f0f0f',
        'dark-light': '#1a1a2e',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'],
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.6s ease-out',
        'fade-in-up-delay-1': 'fadeInUp 0.6s ease-out 0.1s both',
        'fade-in-up-delay-2': 'fadeInUp 0.6s ease-out 0.2s both',
        'fade-in-up-delay-3': 'fadeInUp 0.6s ease-out 0.3s both',
        'fade-in-up-delay-4': 'fadeInUp 0.6s ease-out 0.4s both',
        'fade-in': 'fadeIn 0.5s ease-out',
        'scale-in': 'scaleIn 0.4s ease-out',
        'slide-in-left': 'slideInLeft 0.3s ease-out',
        'shimmer': 'shimmer 2s linear infinite',
        'float': 'float 6s ease-in-out infinite',
        'float-delay': 'float 6s ease-in-out 2s infinite',
        'pulse-glow': 'pulse-glow 3s ease-in-out infinite',
        'count-up': 'count-up 0.5s ease-out',
      },
      keyframes: {
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        slideInLeft: {
          '0%': { opacity: '0', transform: 'translateX(-20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(220, 38, 38, 0.3)' },
          '50%': { boxShadow: '0 0 20px 5px rgba(220, 38, 38, 0.15)' },
        },
        'count-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)',
        'card-hover': '0 10px 25px rgba(0,0,0,0.1)',
        'sidebar': '2px 0 8px rgba(0,0,0,0.05)',
        'glow': '0 0 30px rgba(220,38,38,0.15)',
        'glow-lg': '0 0 60px rgba(220,38,38,0.2)',
      },
    },
  },
  plugins: [],
}

export default config
