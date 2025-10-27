// blueprints/games/code_playground/static/main.js
//
// 浏览器端的实时预览控制器：
// - 读取编辑器代码
// - 请求 /api/compile-preview 得到 {js, css}
// - 动态生成 iframe HTML，里面挂 React / ReactDOM / lucide / Tailwind
// - 把任何编译期/运行期错误显示在 overlay
// - 本地存储上一次代码
//
// 这份是全量版本，包含状态提示、复制、格式化、重置、分享等逻辑。

(function () {
  // ---------------------------------------------------------------------------
  // DOM 引用
  // ---------------------------------------------------------------------------
  const editor = document.getElementById("code-editor");        // <textarea>
  const frame = document.getElementById("preview-frame");       // <iframe>
  const overlay = document.getElementById("error-overlay");     // 错误浮层
  const compileBadge = document.getElementById("compile-info"); // 编译状态徽标
  const statusLabel = document.getElementById("status-label");  // 顶部状态条
  const buttons = document.querySelectorAll("[data-action]");   // 各种操作按钮
  const compilerRetryButton = document.querySelector(
    '[data-action="reload-compiler"]'
  );

  // ---------------------------------------------------------------------------
  // 常量
  // ---------------------------------------------------------------------------
  const STORAGE_KEY = "code-playground-source";
  const COMPILE_ENDPOINT = "/api/compile-preview";
  const SNAPSHOT_ENDPOINT = "/g/code_playground/snapshot"; // <- 分享接口 (后端 plugin.py @bp.post("/snapshot"))
  const REQUEST_DEBOUNCE = 320; // ms 防抖

  // 默认示例代码（仅在本地没有存档时用）
  const DEFAULT_SOURCE = [
    "import React from 'react';",
    "export default function Demo(){",
    "  return (",
    '    <div className="min-h-screen grid place-items-center text-slate-200 bg-gradient-to-br from-slate-900 via-slate-950 to-black font-sans">',
    '      <div className="text-center space-y-4">',
    '        <div className="text-2xl font-semibold">准备就绪</div>',
    '        <div className="text-slate-500 text-sm">你可以在左侧编辑 React + Tailwind 代码</div>',
    "      </div>",
    "    </div>",
    "  );",
    "}",
    "",
  ].join("\n");

  // ---------------------------------------------------------------------------
  // 运行时状态
  // ---------------------------------------------------------------------------
  let debounceTimer = null;
  let lastSource = "";
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

    if (compilerRetryButton && good) {
      compilerRetryButton.classList.remove("is-visible");
    }
  }

  function showError(message, label = "编译失败") {
    if (overlay) {
      overlay.textContent = message;
      overlay.classList.add("visible");
    }
    setCompileInfo(label, false);
    setStatus("出现错误", "error");
  }

  function hideError() {
    if (overlay) {
      overlay.textContent = "";
      overlay.classList.remove("visible");
    }
  }

  // iframe 运行时错误上报（window.parent.postMessage(...)）
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
  // 构建 iframe HTML
  // ---------------------------------------------------------------------------
  function sanitizeScriptContent(js) {
    // 防止用户代码里出现 </script> 直接把 <script> 截断
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

      // 字体
      '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />',
      '    <link rel="preconnect" href="https://fonts.googleapis.com" />',
      '    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />',

      // Tailwind utilities（我们在 server 端关了 preflight）
      '    <style id="tailwind-bundle">',
      styles,
      "    </style>",

      // baseline：手动补齐 preflight 的关键变量、阴影变量、滚动行为、字体等
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
      "        --tw-pan-x: ;",
      "        --tw-pan-y: ;",
      "        --tw-pinch-zoom: ;",
      "        --tw-scroll-snap-strictness: proximity;",
      "        --tw-ordinal: ;",
      "        --tw-slashed-zero: ;",
      "        --tw-numeric-figure: ;",
      "        --tw-numeric-spacing: ;",
      "        --tw-numeric-fraction: ;",
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
      "        overflow: hidden;", // body 本身不滚动, 由自定义容器滚动
      "      }",
      "      button, input, select, textarea {",
      "        font: inherit;",
      "        color: inherit;",
      "        background: transparent;",
      "      }",
      "      .shadow-glass-xl {",
      "        --tw-shadow: 0 40px 120px rgba(15,23,42,0.45);",
      "        box-shadow: var(--tw-ring-offset-shadow,0 0 #0000),",
      "                    var(--tw-ring-shadow,0 0 #0000),",
      "                    var(--tw-shadow);",
      "      }",
      "      .shadow-xl, .shadow-2xl, .shadow-glass-xl {",
      "        /* 依赖上面的 --tw-shadow, 避免出现“黑线边框”式假阴影 */",
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

      // React运行时 UMD，这会挂到 window.React / window.ReactDOM / window.ReactDOM.createRoot
      '    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>',
      '    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>',

      // lucide 核心 UMD（提供 window.lucide.icons）
      '    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>',

      "    <script>",
      "      (function () {",
      "        var iconSource = null;",
      "        var sample = null;",
      "        if (window.lucide && window.lucide.icons && typeof window.lucide.icons === 'object') {",
      "          iconSource = 'lucide.core';",
      "          var keys = Object.keys(window.lucide.icons);",
      "          sample = keys.slice(0, 12);",
      "        }",
      "        console.log('[Preview Sandbox] React ok?', !!window.React, 'ReactDOM ok?', !!window.ReactDOM, 'Icon source:', iconSource, 'Sample icons:', sample);",
      "      })();",
      "    </script>",

      // esbuild 产出的 IIFE（已经把你的组件 mount 到 #root）
      "    <script>",
      script,
      "    </script>",

      "  </body>",
      "</html>",
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // 把编译结果塞进 iframe
  // ---------------------------------------------------------------------------
  function applyPreview(js, css) {
    // 清理旧 blob URL
    if (currentBlobUrl) {
      try {
        URL.revokeObjectURL(currentBlobUrl);
      } catch (err) {}
      currentBlobUrl = null;
    }

    const html = buildPreviewHtml(js, css);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    currentBlobUrl = url;

    frame.removeAttribute("srcdoc");
    frame.src = url;

    // 安全清理 blob URL
    const cleanupTimeout = setTimeout(() => {
      if (currentBlobUrl === url) {
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (err) {}
      }
    }, 10000);

    frame.onload = () => {
      clearTimeout(cleanupTimeout);
      if (currentBlobUrl === url) {
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (err) {}
      }
    };

    frame.onerror = () => {
      clearTimeout(cleanupTimeout);
      try {
        URL.revokeObjectURL(url);
        if (currentBlobUrl === url) {
          currentBlobUrl = null;
        }
      } catch (err) {}
    };
  }

  // ---------------------------------------------------------------------------
  // 成功/失败时 UI
  // ---------------------------------------------------------------------------
  function handleCompileSuccess(js, css) {
    hideError();
    applyPreview(js, css);
    setCompileInfo("编译成功", true);
    setStatus("实时预览", "idle");
  }

  function handleCompileError(message) {
    showError(message || "编译失败");
    if (compilerRetryButton) {
      compilerRetryButton.classList.add("is-visible");
    }
  }

  // ---------------------------------------------------------------------------
  // 请求后端编译
  // ---------------------------------------------------------------------------
  async function requestPreview(source, requestId) {
    // 如果上一次还在跑，就停掉
    if (currentController) {
      currentController.abort();
    }

    const controller = new AbortController();
    currentController = controller;

    setCompileInfo("编译中…", true);
    setStatus("编译中", "running");
    hideError();

    const timeoutId = setTimeout(() => {
      controller.abort();
      if (requestId === activeRequestId) {
        handleCompileError("编译超时（30秒），请检查代码复杂度");
      }
    }, 30000);

    try {
      const response = await fetch(COMPILE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // 如果这个请求已经不是“最新的那次”了，直接丢弃结果
      if (requestId !== activeRequestId || currentController !== controller) {
        return;
      }

      if (!response.ok) {
        let errorMessage = "编译失败";
        try {
          const data = await response.json();
          if (data && data.error) {
            errorMessage = data.error;
          }
        } catch (err) {
          errorMessage = response.statusText || errorMessage;
        }
        handleCompileError(errorMessage);
        return;
      }

      const payload = await response.json();
      if (!payload || typeof payload.js !== "string") {
        handleCompileError("编译服务返回了无效的结果");
        return;
      }

      handleCompileSuccess(
        payload.js,
        typeof payload.css === "string" ? payload.css : ""
      );
    } catch (error) {
      clearTimeout(timeoutId);

      if (error.name === "AbortError") {
        return; // 我们自己手动取消的请求
      }
      if (requestId !== activeRequestId || currentController !== controller) {
        return; // 不是最新请求
      }

      handleCompileError(error.message || "网络异常，请稍后重试");
    } finally {
      if (currentController === controller) {
        currentController = null;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 调度编译（防抖）
  // ---------------------------------------------------------------------------
  function scheduleUpdate(immediate = false) {
    const source = editor.value;
    if (!immediate && source === lastSource) {
      // 没变化就不打扰编译器
      return;
    }

    const trigger = () => {
      lastSource = source;
      activeRequestId += 1;
      requestPreview(source, activeRequestId);
    };

    if (immediate) {
      trigger();
      return;
    }

    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }

    debounceTimer = setTimeout(() => {
      trigger();
    }, REQUEST_DEBOUNCE);
  }

  // ---------------------------------------------------------------------------
  // 本地存储
  // ---------------------------------------------------------------------------
  function saveToLocalStorage(key, value) {
    try {
      localStorage.setItem(key, value);
      return true;
    } catch (err) {
      console.error("LocalStorage save failed:", err);
      if (err.name === "QuotaExceededError") {
        setStatus("存储空间已满", "error");
        setTimeout(() => setStatus("实时预览", "idle"), 3000);
      }
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // 分享链接逻辑
  // ---------------------------------------------------------------------------
  async function createShareLink() {
    const source = editor.value;
    setStatus("生成分享链接…", "running");

    try {
      const resp = await fetch(SNAPSHOT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
      });

      // 如果后端没注册 /snapshot，很多框架会返回一段 HTML，这里会是 resp.ok=false 或解析失败
      if (!resp.ok) {
        let msg = "分享失败";
        try {
          const maybeData = await resp.json();
          if (maybeData && maybeData.error) {
            msg = maybeData.error;
          }
        } catch (_) {
          // resp 不是 JSON（可能是整段 HTML） -> 保持默认 msg
        }
        throw new Error(msg);
      }

      // 正常返回 {id, url}
      const data = await resp.json();
      const shareUrl = data && data.url ? data.url : null;
      if (!shareUrl) {
        throw new Error("后端未返回分享URL");
      }

      // 复制到剪贴板
      try {
        await navigator.clipboard.writeText(shareUrl);
        alert("分享链接已生成并复制：\n" + shareUrl);
        setStatus("分享链接已复制", "success");
      } catch (copyErr) {
        alert("分享链接已生成：\n" + shareUrl + "\n(复制失败请手动复制)");
        setStatus("分享链接已生成", "success");
      }

      setTimeout(() => setStatus("实时预览", "idle"), 2000);
    } catch (err) {
      console.error(err);
      alert("分享失败：" + (err.message || err));
      setStatus("分享失败", "error");
      setTimeout(() => setStatus("实时预览", "idle"), 2000);
    }
  }

  // ---------------------------------------------------------------------------
  // 按钮点击分发
  // ---------------------------------------------------------------------------
  function handleAction(event) {
    const action = event.currentTarget.dataset.action;

    // 分享演示：把当前代码POST到后端，拿回只读展示链接
    if (action === "share") {
      createShareLink();
      return;
    }

    // 重置示例
    if (action === "reset") {
      editor.value = DEFAULT_SOURCE;
      localStorage.removeItem(STORAGE_KEY);
      scheduleUpdate(true);
      return;
    }

    // 复制代码
    if (action === "copy") {
      navigator.clipboard
        .writeText(editor.value)
        .then(() => {
          setStatus("已复制到剪贴板", "success");
          setTimeout(() => setStatus("实时预览", "idle"), 1600);
        })
        .catch(() => {
          setStatus("复制失败", "error");
        });
      return;
    }

    // 代码格式化
    if (action === "format") {
      if (window.js_beautify) {
        const formatted = window.js_beautify(editor.value, {
          indent_size: 2,
          max_preserve_newlines: 2,
          space_in_empty_paren: false,
        });
        editor.value = formatted;
        scheduleUpdate(true);
      } else {
        setStatus("格式化工具加载中", "running");
        setTimeout(() => setStatus("实时预览", "idle"), 1500);
      }
      return;
    }

    // 手动强制重新编译
    if (action === "reload-compiler") {
      scheduleUpdate(true);
      return;
    }
  }

  // ---------------------------------------------------------------------------
  // 初始化
  // ---------------------------------------------------------------------------
  function init() {
    const stored = localStorage.getItem(STORAGE_KEY);
    editor.value = stored || DEFAULT_SOURCE;

    // 输入 -> 防抖编译 + 存本地
    editor.addEventListener("input", () => {
      saveToLocalStorage(STORAGE_KEY, editor.value);
      scheduleUpdate();
    });

    // 操作按钮
    buttons.forEach((btn) => btn.addEventListener("click", handleAction));

    // 初始状态
    setCompileInfo("等待编译…", true);
    setStatus("实时预览", "idle");

    // 首次渲染一发
    scheduleUpdate(true);
  }

  init();
})();
