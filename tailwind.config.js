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
      },
    },
  },
  plugins: [],
}
