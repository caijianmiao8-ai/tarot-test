// blueprints/games/code_playground/static/share_view.js
//
// 这是分享页(只读页)专用的控制器。
// 它做的事：
// 1. 读取后端注入的 window.__SNAPSHOT_SOURCE__ （也就是那一刻保存下来的源码）
// 2. POST 给 /api/compile-preview，拿到 {js, css}
// 3. 把结果拼成 sandbox HTML，丢进 <iframe>
// 4. 根据成功/失败更新 “等待中 / 编译中 / 预览就绪 / 错误” 的状态标签
//
// 这个文件不会修改本地存储、不会提供编辑功能。
// 也不会暴露源码给访客（除了在 JS 里还拿得到 window.__SNAPSHOT_SOURCE__，如果你以后真的要完全藏源码，下一步是提前编译并存 js/css，再下发）.
//

(function () {
  // ---------------------------------------------------------------------------
  // DOM 元素
  // ---------------------------------------------------------------------------
  const frame = document.getElementById("preview-frame");        // iframe
  const overlay = document.getElementById("error-overlay");      // 错误浮层
  const compileBadge = document.getElementById("compile-info");  // “等待中/编译中/成功/失败”
  const statusLabel = document.getElementById("status-label");   // 右上角状态条
  const compilerRetryButton = document.querySelector('[data-action="reload-compiler"]');

  // ---------------------------------------------------------------------------
  // 常量
  // ---------------------------------------------------------------------------
  const SOURCE = window.__SNAPSHOT_SOURCE__ || "";
  const COMPILE_ENDPOINT = "/api/compile-preview";

  // 运行时状态
  let currentBlobUrl = null;
  let activeRequestId = 0;
  let currentController = null;

  // ---------------------------------------------------------------------------
  // UI 状态工具
  // ---------------------------------------------------------------------------
  function setStatus(message, state = "idle") {
    // 假设结构: <div id="status-label"><span class="status-dot"></span><span>文本</span></div>
    const span = statusLabel
      ? statusLabel.querySelector("span:last-child")
      : null;
    if (span) {
      span.textContent = message;
    }
    if (statusLabel) {
      statusLabel.dataset.state = state;
    }
  }

  function setCompileInfo(message, good = true) {
    if (!compileBadge) return;
    compileBadge.textContent = message;
    compileBadge.style.background = good
      ? "rgba(56,189,248,0.18)"
      : "rgba(248,113,113,0.12)";
    compileBadge.style.color = good ? "#38bdf8" : "#f87171";

    // 成功时把“重试”按钮收起来；失败时我们会单独展开
    if (compilerRetryButton && good) {
      compilerRetryButton.classList.remove("is-visible");
    }
  }

  function showError(message, labelText = "编译失败") {
    if (overlay) {
      overlay.textContent = message;
      overlay.classList.add("visible");
    }
    setCompileInfo(labelText, false);
    setStatus("出现错误", "error");

    if (compilerRetryButton) {
        compilerRetryButton.classList.add("is-visible");
    }
  }

  function hideError() {
    if (overlay) {
      overlay.textContent = "";
      overlay.classList.remove("visible");
    }
  }

  // 监听 iframe 内部 runtime error（代码跑起来后如果 throw，会发 postMessage 出来）
  window.addEventListener("message", (event) => {
    if (!event || !event.data || event.source !== frame.contentWindow) return;
    if (event.data.type === "CODE_PLAYGROUND_ERROR") {
      showError(
        event.data.message || "运行时出现错误",
        "运行时错误"
      );
    }
  });

  // ---------------------------------------------------------------------------
  // 把编译产物拼成 iframe HTML
  // （保持和 main.js 的 buildPreviewHtml 基本一致，这样渲染出来的效果一致）
  // ---------------------------------------------------------------------------
  function sanitizeScriptContent(js) {
    return (js || "")
      .replace(/<\/script>/gi, "<\\/script>")
      .replace(/<script/gi, "<\\\\script>")
      .replace(/<\/style>/gi, "<\\/style>");
  }

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
      "      html, body {",
      "        margin: 0;",
      "        padding: 0;",
      "        height: 100%;",
      "      }",
      "      #root {",
      "        height: 100%;",
      "        min-height: 100%;",
      "      }",
      "      *, ::before, ::after {",
      "        box-sizing: border-box;",
      "        border-width: 0;",
      "        border-style: solid;",
      "        border-color: currentColor;",
      "        --tw-border-spacing-x: 0;",
      "        --tw-border-spacing-y: 0;",
      "        --tw-translate-x: 0;",
      "        --tw-translate-y: 0;",
      "        --tw-rotate: 0;",
      "        --tw-skew-x: 0;",
      "        --tw-skew-y: 0;",
      "        --tw-scale-x: 1;",
      "        --tw-scale-y: 1;",
      "        --tw-ring-inset: ;",
      "        --tw-ring-offset-width: 0px;",
      "        --tw-ring-offset-color: #fff;",
      "        --tw-ring-color: rgb(59 130 246 / 0.5);",
      "        --tw-ring-offset-shadow: 0 0 #0000;",
      "        --tw-ring-shadow: 0 0 #0000;",
      "        --tw-shadow: 0 0 #0000;",
      "        --tw-shadow-colored: 0 0 #0000;",
      "        --tw-blur: ;",
      "        --tw-brightness: ;",
      "        --tw-contrast: ;",
      "        --tw-grayscale: ;",
      "        --tw-hue-rotate: ;",
      "        --tw-invert: ;",
      "        --tw-saturate: ;",
      "        --tw-sepia: ;",
      "        --tw-drop-shadow: ;",
      "        --tw-backdrop-blur: ;",
      "        --tw-backdrop-brightness: ;",
      "        --tw-backdrop-contrast: ;",
      "        --tw-backdrop-grayscale: ;",
      "        --tw-backdrop-hue-rotate: ;",
      "        --tw-backdrop-invert: ;",
      "        --tw-backdrop-opacity: ;",
      "        --tw-backdrop-saturate: ;",
      "        --tw-backdrop-sepia: ;",
      "      }",
      "      body {",
      "        font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;",
      "        -webkit-font-smoothing: antialiased;",
      "        text-rendering: optimizeLegibility;",
      "        background: transparent;",
      "        color: inherit;",
      "        overflow: hidden;",
      "      }",
      "      button, input, select, textarea {",
      "        font: inherit;",
      "        color: inherit;",
      "        background: transparent;",
      "      }",
      "      .shadow-glass-xl {",
      "        --tw-shadow: 0 40px 120px rgba(15,23,42,0.45);",
      "        box-shadow: var(--tw-ring-offset-shadow,0 0 #0000),var(--tw-ring-shadow,0 0 #0000),var(--tw-shadow);",
      "      }",
      "      .cupertino-scroll {",
      "        height: 100%;",
      "        max-height: 100%;",
      "        overflow-y: auto !important;",
      "        -webkit-overflow-scrolling: touch;",
      "        overscroll-behavior: contain;",
      "        scrollbar-width: thin;",
      "        scrollbar-color: rgba(60,60,67,0.36) transparent;",
      "      }",
      "      .cupertino-scroll::-webkit-scrollbar {",
      "        width: 10px;",
      "        height: 10px;",
      "      }",
      "      .cupertino-scroll::-webkit-scrollbar-track {",
      "        background: transparent;",
      "        margin: 6px;",
      "      }",
      "      .cupertino-scroll::-webkit-scrollbar-thumb {",
      "        border-radius: 999px;",
      "        border: 3px solid transparent;",
      "        background-clip: padding-box;",
      "      }",
      "      .cupertino-scroll.cupertino-scroll--light::-webkit-scrollbar-thumb {",
      "        background-color: rgba(60,60,67,0.28);",
      "      }",
      "      .cupertino-scroll.cupertino-scroll--light:hover::-webkit-scrollbar-thumb {",
      "        background-color: rgba(60,60,67,0.45);",
      "      }",
      "      .cupertino-scroll.cupertino-scroll--dark::-webkit-scrollbar-thumb {",
      "        background-color: rgba(235,235,245,0.25);",
      "      }",
      "      .cupertino-scroll.cupertino-scroll--dark:hover::-webkit-scrollbar-thumb {",
      "        background-color: rgba(235,235,245,0.45);",
      "      }",
      "      .cupertino-scroll::-webkit-scrollbar-corner {",
      "        background: transparent;",
      "      }",
      "    </style>",

      "  </head>",
      "  <body>",
      '    <div id="root"></div>',

      // React Runtime
      '    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>',
      '    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>',

      // lucide Runtime
      '    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>',

      "    <script>",
      "      (function () {",
      "        var iconSource = null;",
      "        if (window.lucide && window.lucide.icons) {",
      "          iconSource = 'lucide.core';",
      "        }",
      "        console.log('[Preview Snapshot] Ready. React?', !!window.React, 'ReactDOM?', !!window.ReactDOM, 'Icons?', iconSource);",
      "      })();",
      "    </script>",

      // 用户代码编译结果（IIFE，会把组件 mount 到 #root）
      "    <script>",
      script,
      "    </script>",

      "  </body>",
      "</html>",
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // 把 HTML 塞进 iframe
  // ---------------------------------------------------------------------------
  function applyPreview(js, css) {
    // 清掉旧 blob，避免内存泄漏
    if (currentBlobUrl) {
      try {
        URL.revokeObjectURL(currentBlobUrl);
      } catch (_) {}
      currentBlobUrl = null;
    }

    const html = buildPreviewHtml(js, css);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    currentBlobUrl = url;

    frame.removeAttribute("srcdoc");
    frame.src = url;

    // revoke 策略：onload 或者兜底10秒
    const cleanupTimeout = setTimeout(() => {
      if (currentBlobUrl === url) {
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (_) {}
      }
    }, 10000);

    frame.onload = () => {
      clearTimeout(cleanupTimeout);
      if (currentBlobUrl === url) {
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (_) {}
      }
    };

    frame.onerror = () => {
      clearTimeout(cleanupTimeout);
      try {
        URL.revokeObjectURL(url);
        if (currentBlobUrl === url) {
          currentBlobUrl = null;
        }
      } catch (_) {}
    };
  }

  function handleCompileSuccess(js, css) {
    hideError();
    applyPreview(js, css);
    setCompileInfo("编译成功", true);
    setStatus("预览就绪", "idle");
  }

  function handleCompileError(message) {
    showError(message || "编译失败", "编译失败");
  }

  // ---------------------------------------------------------------------------
  // 调 /api/compile-preview
  // ---------------------------------------------------------------------------
  async function compileAndRender(source, requestId) {
    // 如果上一次还在跑，先撤掉
    if (currentController) {
      currentController.abort();
    }
    const controller = new AbortController();
    currentController = controller;

    // UI: 进入编译中
    setCompileInfo("编译中…", true);
    setStatus("编译中…", "running");
    hideError();

    // 超时兜底
    const timeoutId = setTimeout(() => {
      controller.abort();
      if (requestId === activeRequestId) {
        handleCompileError("编译超时（30秒）");
      }
    }, 30000);

    try {
      const resp = await fetch(COMPILE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // 如果已经不是当前这次请求，结果丢弃
      if (requestId !== activeRequestId || currentController !== controller) {
        return;
      }

      if (!resp.ok) {
        let msg = "编译失败";
        try {
          const data = await resp.json();
          if (data && data.error) msg = data.error;
        } catch (_) {
          msg = resp.statusText || msg;
        }
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
      clearTimeout(timeoutId);

      if (err.name === "AbortError") {
        // 主动abort就别提示
        return;
      }
      if (requestId !== activeRequestId || currentController !== controller) {
        return;
      }

      handleCompileError(err.message || "网络异常");
    } finally {
      if (currentController === controller) {
        currentController = null;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 入口：跑一轮编译
  // ---------------------------------------------------------------------------
  function runOnce() {
    if (!SOURCE.trim()) {
      handleCompileError("没有可展示的代码");
      return;
    }

    activeRequestId += 1;
    compileAndRender(SOURCE, activeRequestId);
  }

  function init() {
    // 初始 UI
    setCompileInfo("等待编译…", true);
    setStatus("准备就绪", "idle");

    if (compilerRetryButton) {
      compilerRetryButton.addEventListener("click", runOnce);
    }

    runOnce();
  }

  init();
})();
