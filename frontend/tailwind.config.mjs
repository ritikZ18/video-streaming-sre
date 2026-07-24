/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
      borderRadius: {
        card: "0.9rem",
        modal: "1.25rem",
      },
      boxShadow: {
        "glow-soft": "0 12px 40px -12px rgba(0, 0, 0, 0.7)",
      },
      keyframes: {
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        slideUp: "slideUp 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94)",
      },
    },
  },
  plugins: [],
};
