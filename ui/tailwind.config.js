/*
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
*/

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        "sre-bg": "var(--sre-bg)",
        "sre-bg-alt": "var(--sre-bg-alt)",
        "sre-bg-card": "var(--sre-bg-card)",
        "sre-surface": "var(--sre-surface)",
        "sre-surface-light": "var(--sre-surface-light)",
        "sre-border": "var(--sre-border)",
        "sre-text": "var(--sre-text)",
        "sre-text-muted": "var(--sre-text-muted)",
        "sre-text-subtle": "var(--sre-text-subtle)",
        "sre-primary": "rgb(var(--sre-primary-rgb) / <alpha-value>)",
        "sre-primary-light": "rgb(var(--sre-primary-light-rgb) / <alpha-value>)",
        "sre-ink": "var(--sre-ink)",
        "sre-highlight": "var(--sre-highlight)",
        "sre-success": "#22c55e",
        "sre-success-light": "#4ade80",
        "sre-warning": "#fb923c",
        "sre-warning-light": "#fdba74",
        "sre-error": "#ef4444",
        "sre-error-light": "#f87171",
        "sre-accent": "#c084fc",
        "sre-accent-light": "#e879f9",
        "sre-neon": "#39ff14",
      },
      fontFamily: {
        mono: [
          "Ubuntu Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Courier New",
          "monospace",
        ],
        sans: [
          "Ubuntu Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Courier New",
          "monospace",
        ],
        serif: [
          "ui-serif",
          "Georgia",
          "Cambria",
          '"Times New Roman"',
          "Times",
          "serif",
        ],
      },
      boxShadow: {
        "glow-sm": "0 0 10px rgb(var(--sre-primary-rgb) / 0.3)",
        glow: "0 0 20px rgb(var(--sre-primary-rgb) / 0.4)",
        "glow-lg": "0 0 30px rgb(var(--sre-primary-rgb) / 0.5)",
        neon: "0 0 10px rgba(57, 255, 20, 0.5)",
        /* Flat ambient lift for dropdowns / overlays only (no offset “sticker” depth) */
        float: "0 4px 24px rgb(0 0 0 / 0.07)",
        "float-sm": "0 2px 14px rgb(0 0 0 / 0.06)",
      },
      transitionTimingFunction: {
        smooth: "cubic-bezier(0.33, 1, 0.68, 1)",
        "smooth-in-out": "cubic-bezier(0.65, 0, 0.35, 1)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "slide-up": "slideUp 0.35s cubic-bezier(0.33, 1, 0.68, 1)",
        "fade-in": "fadeIn 0.4s cubic-bezier(0.65, 0, 0.35, 1)",
      },
      keyframes: {
        slideUp: {
          "0%": { transform: "translateY(6px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
      },
    },
  },
  plugins: [require("tailwind-scrollbar")],
};
