import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // WELLgreen brand — official palette from cff2db1d-__________OL.ai
        //
        // brand.500 = #87A53C  (PANTONE 390C, Green)
        // brown.700 = #4B1E00  (PANTONE 476C, Dark Brown)
        // gold       = #A5874B (PANTONE 874C)
        // silver     = #A5A5A5 (PANTONE 877C)
        // warm-gray  = #968787 (PANTONE Warm Gray 6C)
        brand: {
          50: "#f7faf0",
          100: "#ecf3da",
          200: "#d6e6b6",
          300: "#b9d287",
          400: "#9fc05a",
          500: "#87a53c",
          600: "#6e8a2e",
          700: "#556a24",
          800: "#424f1d",
          900: "#2d3614",
          950: "#1a200a",
        },
        brown: {
          50: "#faf5f0",
          100: "#f0e2d3",
          200: "#dfc0a0",
          300: "#cb966a",
          400: "#b06e3f",
          500: "#8a4d22",
          600: "#6d3812",
          700: "#4b1e00",
          800: "#361500",
          900: "#220d00",
        },
        gold: {
          DEFAULT: "#a5874b",
          50: "#faf7f0",
          100: "#f0e6d0",
          200: "#dfc89a",
          300: "#caa769",
          400: "#b08947",
          500: "#a5874b",
          600: "#856a37",
          700: "#634e29",
          800: "#42341c",
          900: "#221b0e",
        },
        silver: "#a5a5a5",
        "warm-gray": "#968787",
      },
      fontFamily: {
        brand: ["'Plus Jakarta Sans'", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
