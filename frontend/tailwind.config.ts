import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        nexus: {
          bg: "#13121B",
          primary: {
            DEFAULT: "#C4C0FF",
            on: "#2000A4",
            container: "#8781FF",
            "on-container": "#1B0091",
          },
          secondary: {
            DEFAULT: "#54DBC2",
            on: "#003824",
            container: "#00AF97",
            "on-container": "#003A31",
          },
          tertiary: {
            DEFAULT: "#FFB3AF",
            on: "#68000D",
            container: "#FA5859",
            "on-container": "#5C000A",
          },
          error: {
            DEFAULT: "#FFB4AB",
            on: "#690005",
            container: "#93000A",
            "on-container": "#FFDAD6",
          },
          surface: {
            DEFAULT: "#13121B",
            variant: "#35343E",
          },
          outline: {
            DEFAULT: "#918FA1",
            variant: "#464555",
          },
        },
      },
      fontFamily: {
        syne: ["var(--font-syne)", "sans-serif"],
        sans: ["var(--font-dm-sans)", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      },
      spacing: {
        unit: "4px",
        sidebar: "260px",
        container: "24px",
        gutter: "16px",
      },
      borderRadius: {
        none: "0",
        sharp: "0",
        pill: "9999px",
      },
      animation: {
        "pulse-fast": "pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "radial-pulse": "radial-pulse 2s infinite",
      },
      keyframes: {
        "radial-pulse": {
          "0%": { boxShadow: "0 0 0 0 rgba(196, 192, 255, 0.4)" },
          "70%": { boxShadow: "0 0 0 10px rgba(196, 192, 255, 0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(196, 192, 255, 0)" },
        },
      },
    },
  },
  plugins: [],
  darkMode: "class",
};
export default config;
