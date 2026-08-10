/** @type {import('tailwindcss').Config} */

// Theme ported from the Horizon UI Tailwind template. Its palette is dropped
// into `extend` rather than replacing `theme.colors` (which is what Horizon
// itself does) so Tailwind's built-in scales stay available — the app already
// leans on slate/emerald/amber for status text, and wiping them would break
// those silently rather than loudly.
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  // Dark mode is a class on <html>, driven by lib/theme.tsx (not the OS
  // setting alone) so the header toggle can override it in both directions.
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Horizon's accent. Replaces the old blue `brand` scale, so every
        // existing brand-* class across the app picks up the new theme.
        brand: {
          50: "#E9E3FF",
          100: "#C0B8FE",
          200: "#A195FD",
          300: "#8171FC",
          400: "#7551FF",
          500: "#422AFB",
          600: "#3311DB",
          700: "#2111A5",
          800: "#190793",
          900: "#11047A",
        },
        brandLinear: "#868CFF",
        // Dark-mode surfaces, and the primary ink in light mode.
        navy: {
          50: "#d0dcfb",
          100: "#aac0fe",
          200: "#a3b9f8",
          300: "#728fea",
          400: "#3652ba",
          500: "#1b3bbb",
          600: "#24388a",
          700: "#1B254B",
          800: "#111c44",
          900: "#0b1437",
        },
        // Horizon's muted greys — cooler and bluer than Tailwind's slate.
        // Extended, not replaced, so only these steps change.
        gray: {
          50: "#F5F6FA",
          100: "#EEF0F6",
          200: "#DADEEC",
          300: "#C9D0E3",
          400: "#B0BBD5",
          500: "#B5BED9",
          600: "#A3AED0",
          700: "#707eae",
          800: "#2D396B",
          900: "#1B2559",
        },
        lightPrimary: "#F4F7FE",
        background: {
          100: "#F4F7FE",
          900: "#070f2e",
        },
        horizonGreen: {
          50: "#E1FFF4",
          100: "#BDFFE7",
          400: "#01F99E",
          500: "#01B574",
          600: "#01935D",
        },
        horizonOrange: {
          50: "#FFF7EB",
          100: "#FFF1DB",
          400: "#FFC46B",
          500: "#FFB547",
          600: "#FF9B05",
        },
        horizonRed: {
          50: "#FCE8E8",
          100: "#FAD1D1",
          400: "#EA4848",
          500: "#E31A1A",
          600: "#B71515",
        },
        horizonTeal: {
          400: "#59D4C9",
          500: "#33C3B7",
          600: "#299E94",
        },
        // Card shadow tints, referenced as shadow-shadow-500 / -100 exactly
        // as Horizon's own Card component does.
        shadow: {
          100: "var(--shadow-100)",
          500: "rgba(112, 144, 176, 0.08)",
        },
      },
      fontFamily: {
        // DM Sans for body copy, Poppins for headings — Horizon's pairing.
        sans: ["DM Sans", "system-ui", "sans-serif"],
        dm: ["DM Sans", "system-ui", "sans-serif"],
        display: ["Poppins", "DM Sans", "system-ui", "sans-serif"],
        poppins: ["Poppins", "sans-serif"],
      },
      boxShadow: {
        "3xl": "14px 17px 40px 4px",
        card: "0px 18px 40px rgba(112, 144, 176, 0.12)",
        glow: "0 8px 24px -8px rgba(66, 42, 251, 0.45)",
        inset: "inset 0px 18px 22px",
        darkinset: "0px 4px 4px inset",
      },
      animation: {
        "fade-in": "fadeIn 0.5s ease-out forwards",
        "slide-up": "slideUp 0.5s ease-out forwards",
        float: "float 7s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-16px)" },
        },
      },
    },
  },
  plugins: [],
};
