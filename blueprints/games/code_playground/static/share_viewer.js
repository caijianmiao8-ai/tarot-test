// blueprints/games/code_playground/static/share_viewer.js
(function () {
  const frame = document.getElementById("preview-frame");
  const overlay = document.getElementById("error-overlay");
  const compileBadge = document.getElementById("compile-info");
  const statusLabel = document.getElementById("status-label");

  const COMPILE_ENDPOINT = "/api/compile-preview";

  // ----------------- UI helpers -----------------
  function setStatus(message, state = "idle") {
    const span = statusLabel
      ? statusLabel.querySelector("span:last-child")
      : null;
    if (span) span.textContent = message;
    if (statusLabel) statusLabel.dataset.state = state;
  }

  function setCompileInfo(message, good = true) {
    if (!compileBadge) return;
    compileBadge.textContent = message;
    compileBadge.style.background = good
      ? "rgba(56,189,248,0.18)"
      : "rgba(248,113,113,0.12)";
    compileBadge.style.color = good ? "#38bdf8" : "#f87171";
  }

  function showError(message, label) {
    if (overlay) {
      overlay.textContent = message;
      overlay.classList.add("visible");
    }
    setCompileInfo(label || "错误", false);
    setStatus("出现错误", "error");
  }

  function hideError() {
    if (overlay) {
      overlay.textContent = "";
      overlay.classList.remove("visible");
    }
  }

  // runtime error reporting from iframe
  window.addEventListener("message", (event) => {
    if (!event || !event.data || event.source !== frame.contentWindow) return;
    if (event.data.type === "CODE_PLAYGROUND_ERROR") {
      showError(
        event.data.message || "运行时出现错误",
        "运行时错误"
      );
    }
  });

  // ----------------- iframe builder -----------------
  function sanitizeScriptContent(js) {
    return (js || "")
      .replace(/<\/script>/gi, "<\\/script>")
      .replace(/<script/gi, "<\\\\script>")
      .replace(/<\/style>/gi, "<\\/style>");
  }

  // 直接拷贝 main.js 里的 buildPreviewHtml (保持一致性)
  function buildPreviewHtml(js, css) {
    const script = sanitizeScriptContent(js);
    const styles = css || "";

    return [
      "<!DOCTYPE html>",
      '<html lang="zh-CN">',
      "  <head>",
      '    <meta charset="utf-8" />',
      '    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />',
      '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />',
      '    <link rel="preconnect" href="https://fonts.googleapis.com" />',
      '    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />',
      '    <style id="tailwind-bundle">',
      styles,
      "    </style>",
      '    <style id="sandbox-baseline">',
      // 这里可以直接复用 main.js 里的 baseline 样式块（为了简化篇幅，这里略）。
      // 实际实现时请直接整段粘过去，保持和 main.js 一致，否则阴影/滚动可能不对。
      "    </style>",
      "  </head>",
      "  <body>",
      '    <div id="root"></div>',
      '    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>',
      '    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>',
      '    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>',
      "    <script>",
      "      (function () {",
      "        var iconSource = null;",
      "        if (window.lucide && window.lucide.icons) {",
      "          iconSource = 'lucide.core';",
      "        }",
      "        console.log('[Preview Sandbox:share]', !!window.React, !!window.ReactDOM, iconSource);",
      "      })();",
      "    </script>",
      "    <script>",
      script,
      "    </script>",
      "  </body>",
      "</html>",
    ].join("\n");
  }

  let currentBlobUrl = null;

  function applyPreview(js, css) {
    if (currentBlobUrl) {
      try { URL.revokeObjectURL(currentBlobUrl); } catch {}
      currentBlobUrl = null;
    }

    const html = buildPreviewHtml(js, css);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    currentBlobUrl = url;

    frame.removeAttribute("srcdoc");
    frame.src = url;

    const cleanupTimeout = setTimeout(() => {
      if (currentBlobUrl === url) {
        try { URL.revokeObjectURL(url); currentBlobUrl = null; } catch {}
      }
    }, 10000);

    frame.onload = () => {
      clearTimeout(cleanupTimeout);
      if (currentBlobUrl === url) {
        try { URL.revokeObjectURL(url); currentBlobUrl = null; } catch {}
      }
    };
    frame.onerror = () => {
      clearTimeout(cleanupTimeout);
      try { URL.revokeObjectURL(url); if (currentBlobUrl === url) currentBlobUrl = null; } catch {}
    };
  }

  function handleCompileSuccess(js, css) {
    hideError();
    applyPreview(js, css);
    setCompileInfo("编译成功", true);
    setStatus("演示准备就绪", "idle");
  }

  function handleCompileError(message) {
    showError(message || "编译失败", "编译失败");
  }

  async function loadAndRender() {
    const source = window.__SHARED_CODE__ || "";

    if (!source.trim()) {
      handleCompileError("没有可展示的代码");
      return;
    }

    setCompileInfo("编译中…", true);
    setStatus("编译中…", "running");
    hideError();

    try {
      const resp = await fetch(COMPILE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
      });

      if (!resp.ok) {
        let msg = "编译失败";
        try {
          const data = await resp.json();
          if (data && data.error) msg = data.error;
        } catch {}
        handleCompileError(msg);
        return;
      }

      const data = await resp.json();
      if (!data || typeof data.js !== "string") {
        handleCompileError("编译服务返回了无效结果");
        return;
      }

      handleCompileSuccess(
        data.js,
        typeof data.css === "string" ? data.css : ""
      );
    } catch (err) {
      handleCompileError(err.message || "网络异常");
    }
  }

  loadAndRender();
})();
