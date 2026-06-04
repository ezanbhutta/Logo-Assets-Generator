/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "system-ui", "sans-serif"],
      },
      colors: {
        // CSR-Pulse palette
        pulse: {
          50: "#f5f3ff",
          100: "#ece7fe",
          200: "#dccffd",
          300: "#c3aafb",
          400: "#a17cf8",
          500: "#7229ff", // primary
          600: "#6420e6",
          700: "#5117bd",
        },
        ink: "#160a33",
        // legacy aliases (kept so any stray class still resolves)
        brand: { navy: "#160a33", red: "#7229ff" },
      },
    },
  },
  plugins: [],
};
