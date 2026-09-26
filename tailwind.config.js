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
        'csj-purple': 'var(--brand, #9B7FBF)',
        'csj-yellow': '#F4D47C',
        'csj-purple-dark': 'var(--brand-dark, #7B5FA0)',
        'csj-yellow-dark': '#E5C05A',
      },
    },
  },
  plugins: [],
}
