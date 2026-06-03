/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Colors de marca: llegeixen variables CSS (multi-tenant branding).
        // El fallback és el color original de Nou Patufet. La sintaxi
        // `rgb(var(...) / <alpha-value>)` preserva els modificadors d'opacitat
        // (p. ex. bg-navy/90, text-navy/20).
        navy:   'rgb(var(--brand-navy-rgb, 11 37 69) / <alpha-value>)',
        terra:  'rgb(var(--brand-terra-rgb, 201 123 78) / <alpha-value>)',
        sage:   '#84B59F',
        cherry: '#6D2E46',
        crema:  '#F4F1EA',
        fons:   '#E5E0D5',
        // greys del mockup
        muted:  '#64748B',
        border: '#DDD7C8',
        card:   '#F4F1EA',
        dark:   '#1F2937',
        navylight: '#0F3258',
        navyborder: '#B8C4D6',
        userbubble: '#E3EAF5',
        green: '#10B981',
      },
      fontFamily: {
        sans: ['Calibri', 'Arial', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
