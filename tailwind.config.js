/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './ilovevoley/**/*.html',
    './ilovevoley/**/*.py',
    './ilovevoley/static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        'csj-purple': 'rgb(var(--brand-rgb, 155 127 191) / <alpha-value>)',
        'csj-yellow': '#F4D47C',
        'csj-purple-dark': 'rgb(var(--brand-dark-rgb, 123 95 160) / <alpha-value>)',
        'csj-yellow-dark': '#E5C05A',
        'brand-gradient-from': 'rgb(var(--brand-gradient-from-rgb, 1 105 111) / <alpha-value>)',
        'brand-gradient-to': 'rgb(var(--brand-gradient-to-rgb, 0 77 82) / <alpha-value>)',
        // Tokens del rediseño: derivados en base.html a partir de --brand / --brand-dark.
        surface: 'var(--surface)',
        line: 'var(--line)',
        tint: 'var(--tint)',
        'brand-text': 'var(--brand-text)',
        ink: 'var(--ink)',
        muted: 'var(--muted)',
        page: 'var(--bg)',
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', 'system-ui', 'sans-serif'],
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
