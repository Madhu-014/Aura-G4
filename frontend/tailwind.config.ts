import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        tactical: {
          bg: "#050509",
          panel: "#0a0a0f",
          neon: "#00FF41",
          ocean: "#0070f3",
          warning: "#ff8a00",
          danger: "#ff2d2d",
        },
      },
      boxShadow: {
        glass: "0 0 0 1px rgba(255,255,255,0.05), 0 16px 40px rgba(0, 0, 0, 0.35)",
      },
      backgroundImage: {
        grid: "linear-gradient(rgba(0, 255, 65, 0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 112, 243, 0.04) 1px, transparent 1px)",
      },
      animation: {
        heartbeat: "heartbeat 1.6s ease-in-out infinite",
        scanline: "scanline 2.8s linear infinite",
      },
      keyframes: {
        heartbeat: {
          "0%, 100%": { transform: "scale(1)", opacity: "0.85" },
          "50%": { transform: "scale(1.35)", opacity: "1" },
        },
        scanline: {
          "0%": { transform: "translateY(-105%)" },
          "100%": { transform: "translateY(105%)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
