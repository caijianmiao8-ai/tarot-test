/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "BlinkMacSystemFont", "'Segoe UI'", "sans-serif"],
        mono: ["'JetBrains Mono'", "'Fira Code'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      backgroundImage: {
        "glass-gradient": "linear-gradient(135deg, rgba(14,165,233,0.1), transparent 55%, rgba(168,85,247,0.1))",
      },
      boxShadow: {
        glow: "0 30px 60px -12px rgba(15,23,42,0.55)",
      },
    },
  },
  plugins: [],
};
