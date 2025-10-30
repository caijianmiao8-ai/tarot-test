/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  // content 由 /api/compile-preview.js 用 raw 注入，这里保持空即可
  content: [],
  // ⭐ 关键：把容易漏的“斜杠不透明度”& 任意值类名 safelist 掉
  safelist: [
    // 斜杠不透明度描边（否则容易回落为 currentColor → 看起来像黑边）
    { pattern: /border-(white|black)\/\d+/ },
    // 你 Demo 中大量使用的任意值类（渐变、阴影）
    { pattern: /bg-\[.*\]/ },
    { pattern: /shadow-\[.*\]/ },
    // 保险起见，把常见透明度类也兜一下
    { pattern: /text-(white|black)\/\d+/ },
    { pattern: /bg-(white|black)\/\d+/ },
  ],
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
      borderRadius: {
        xl: "1.25rem",
        "2xl": "1.5rem",
        "3xl": "1.75rem",
      },
    },
  },
  plugins: [],
};
