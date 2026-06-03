/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          emphasis: 'var(--lsf-primary-emphasis, #1e40af)',
          DEFAULT: 'var(--lsf-primary, #2563eb)',
        },
        neutral: {
          'emphasis-subtle': 'var(--lsf-neutral-emphasis-subtle, #f3f4f6)',
        },
        success: { DEFAULT: 'var(--lsf-success, #16a34a)' },
        warning: { DEFAULT: 'var(--lsf-warning, #f59e0b)' },
        danger: { DEFAULT: 'var(--lsf-danger, #dc2626)' },
      },
    },
  },
  plugins: [],
};
