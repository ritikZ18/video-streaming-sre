/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Inter (loaded via next/font in app/layout.tsx) with the system stack
        // as fallback so macOS still renders SF before/without Inter.
        sans: [
          "var(--font-inter)",
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        // Depth instead of flat black — see index.css for the page base + wash.
        surface: {
          DEFAULT: "#0a0a0f", // page base (not pure black)
          1: "#16161d", // elevated card surface
          2: "#1c1c26", // raised panel
        },
        glass: "rgba(255,255,255,0.05)",
        accent: {
          DEFAULT: "#7d8bff",
          400: "#818cf8",
          500: "#6366f1",
        },
      },
      textColor: {
        // Slightly brighter than the old white/40-60 so it doesn't read as a void.
        ink: "#ffffff",
        "ink-2": "rgba(255,255,255,0.66)",
        "ink-3": "rgba(255,255,255,0.40)",
      },
      letterSpacing: {
        display: "-0.03em", // hero titles
        heading: "-0.02em", // section headings
        bodytight: "-0.01em", // body / meta
      },
      borderRadius: {
        card: "0.9rem",
        modal: "1.25rem",
        poster: "0.75rem",
      },
      boxShadow: {
        "glow-soft": "0 12px 40px -12px rgba(0, 0, 0, 0.7)",
        // Apple-TV card focus: deep soft drop + top inner highlight + hairline ring.
        "card-focus":
          "0 26px 44px -18px rgba(0,0,0,0.85), 0 0 0 1px rgba(255,255,255,0.10), inset 0 1px 0 rgba(255,255,255,0.14)",
        "card-rest": "0 8px 22px -12px rgba(0,0,0,0.9)",
      },
      backgroundImage: {
        // Soft top vignette light so the top of the page isn't a void.
        ambient:
          "radial-gradient(120% 80% at 50% -10%, rgba(70,70,110,0.22), transparent 60%)",
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
