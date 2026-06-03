/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: { navy: "#112630", red: "#ec1c24" },
      },
    },
  },
  plugins: [],
};
