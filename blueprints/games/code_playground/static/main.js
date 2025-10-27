// blueprints/games/code_playground/static/main.js
//
// 浏览器端控制器：
// - 左侧编辑器监听输入，自动调 /api/compile-preview 拿 {js, css}，更新右侧 iframe
// - 显示编译状态 / 运行期报错
// - 保存当前代码到 localStorage
// - 生成“分享演示”链接 (POST /g/code_playground/snapshot)
// - 左右分栏支持拖拽 + 记忆宽度
//
// 这一版整合了所有我们讨论过的修复点。

(function () {
  // ---------------------------------------------------------------------------
  // DOM 引用
  // ---------------------------------------------------------------------------
  const editor = document.getElementById("code-editor"); // <textarea>
  const frame = document.getElementById("preview-frame"); // <iframe>
  const overlay = document.getElementById("error-overlay"); // 错误浮层
  const compileBadge = document.getElementById("compile-info"); // “编译成功/失败…”
  const statusLabel = document.getElementById("status-label"); // 顶部状态条
  const buttons = document.querySelectorAll("[data-action]"); // 各种操作按钮
  const compilerRetryButton = document.querySelector(
    '[data-action="reload-compiler"]'
  );

  // ---------------------------------------------------------------------------
  // 常量
  // ---------------------------------------------------------------------------
  const STORAGE_KEY = "code-playground-source";
  const COMPILE_ENDPOINT = "/api/compile-preview";
  const SNAPSHOT_ENDPOINT = "/g/code_playground/snapshot";
  const REQUEST_DEBOUNCE = 320; // ms 防抖，避免每敲一个字就POST一次

  // 默认示例（localStorage 没有时用）
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
  // 运行状态
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
    // 假设 status-label 内部结构:
    // <div id="status-label"><span class="status-dot"></span><span>文本</span></div>
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

  // iframe runtime 错误监听（iframe 里代码会用 postMessage 回报错）
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
  // 构建 iframe HTML 片段
  // ---------------------------------------------------------------------------
  function sanitizeScriptContent(js) {
    // 防止 </script> 直接中断 <script> 标签
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
      "        overflow: hidden;", // body不滚动，内部自定义区域滚动
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

      // React runtime UMD，会注入 window.React / window.ReactDOM
      '    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>',
      '    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>',

      // lucide runtime UMD (window.lucide.icons)
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
      "        console.log('[Preview Sandbox] React ok?', !!window.React, 'ReactDOM ok?', !!window.ReactDOM, 'Icons?', iconSource, 'Sample icons:', sample);",
      "      })();",
      "    </script>",

      // esbuild 产物 IIFE：会在 #root 里 mount 组件
      "    <script>",
      script,
      "    </script>",

      "  </body>",
      "</html>",
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // 把 iframe 内容更新为最新编译结果
  // ---------------------------------------------------------------------------
  function applyPreview(js, css) {
    // 清理旧 blob
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

    // 10秒兜底 revoke，或者 onload 后 revoke
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

  function handleCompileSuccess(js, css) {
    hideError();
    applyPreview(js, css);
    setCompileInfo("编译成功", true);
    setStatus("实时预览", "idle");
  }

  function handleCompileError(message) {
    showError(message || "编译失败", "编译失败");
  }

  // ---------------------------------------------------------------------------
  // 调用后端 /api/compile-preview
  // ---------------------------------------------------------------------------
  async function requestPreview(source, requestId) {
    // 取消前一次未完成的编译请求
    if (currentController) {
      currentController.abort();
    }
    const controller = new AbortController();
    currentController = controller;

    setCompileInfo("编译中…", true);
    setStatus("编译中", "running");
    hideError();

    // 超时兜底
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

      // 如果这次请求已经不是最新的，就丢弃结果
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

      // Abort 不算错误提醒
      if (error.name === "AbortError") {
        return;
      }
      if (requestId !== activeRequestId || currentController !== controller) {
        return;
      }

      handleCompileError(error.message || "网络异常，请稍后重试");
    } finally {
      if (currentController === controller) {
        currentController = null;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 调度编译，带防抖
  // ---------------------------------------------------------------------------
  function scheduleUpdate(immediate = false) {
    const source = editor.value;
    if (!immediate && source === lastSource) {
      // 内容没变就不触发
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
  // 分享链接逻辑：上传当前代码，后端返回只读预览的 URL
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

      if (!resp.ok) {
        let msg = "分享失败";
        try {
          const maybeData = await resp.json();
          if (maybeData && maybeData.error) {
            msg = maybeData.error;
          }
        } catch (_) {
          // resp 不是 JSON（可能是 HTML兜底页面） -> 保持默认 msg
        }
        throw new Error(msg);
      }

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
        alert(
          "分享链接已生成：\n" +
            shareUrl +
            "\n(复制失败请手动复制)"
        );
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
  // 分隔条拖拽逻辑：左栏宽度可调并写入 localStorage
  // ---------------------------------------------------------------------------
  function setupResizableSplit() {
    const leftPane = document.getElementById("pane-left");
    const handle = document.getElementById("split-handle");

    if (!leftPane || !handle) {
      // 分享页等没有左栏时，直接跳过
      return;
    }

    const SAVED_KEY = "code-playground-left-width";
    const saved = localStorage.getItem(SAVED_KEY);
    if (saved) {
      const px = parseFloat(saved);
      if (!Number.isNaN(px) && px > 0) {
        leftPane.style.flexBasis = px + "px";
      }
    }

    let dragging = false;
    let startX = 0;
    let startWidth = 0;

    function pointerDown(e) {
      dragging = true;
      startX = e.clientX;
      startWidth = leftPane.getBoundingClientRect().width;

      document.body.classList.add("resizing");
      handle.classList.add("dragging");

      window.addEventListener("pointermove", pointerMove);
      window.addEventListener("pointerup", pointerUp);
    }

    function pointerMove(e) {
      if (!dragging) return;

      const dx = e.clientX - startX;
      let newWidth = startWidth + dx;

      const MIN = 260;
      const MAX = window.innerWidth * 0.8;
      if (newWidth < MIN) newWidth = MIN;
      if (newWidth > MAX) newWidth = MAX;

      leftPane.style.flexBasis = newWidth + "px";
      localStorage.setItem(SAVED_KEY, String(newWidth));
    }

    function pointerUp() {
      if (!dragging) return;
      dragging = false;

      document.body.classList.remove("resizing");
      handle.classList.remove("dragging");

      window.removeEventListener("pointermove", pointerMove);
      window.removeEventListener("pointerup", pointerUp);
    }

    handle.addEventListener("pointerdown", pointerDown, { passive: true });
  }

  // ---------------------------------------------------------------------------
  // action 按钮处理：reset / copy / format / share / reload-compiler
  // ---------------------------------------------------------------------------
  function handleAction(event) {
    const action = event.currentTarget.dataset.action;

    if (action === "share") {
      createShareLink();
      return;
    }

    if (action === "reset") {
      editor.value = DEFAULT_SOURCE;
      localStorage.removeItem(STORAGE_KEY);
      scheduleUpdate(true);
      return;
    }

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

    if (action === "reload-compiler") {
      scheduleUpdate(true);
      return;
    }
  }

  // ---------------------------------------------------------------------------
  // 初始化
  // ---------------------------------------------------------------------------
  function init() {
    // 1. 启用分栏拖拽（如果当前页面有左右面板）
    setupResizableSplit();

    // 2. 还原上次编辑的代码
    const stored = localStorage.getItem(STORAGE_KEY);
    editor.value = stored || DEFAULT_SOURCE;

    // 3. 输入监听：本地保存 + 防抖触发编译
    editor.addEventListener("input", () => {
      saveToLocalStorage(STORAGE_KEY, editor.value);
      scheduleUpdate();
    });

    // 4. 操作按钮监听
    buttons.forEach((btn) => btn.addEventListener("click", handleAction));

    // 5. 初始 UI 状态
    setCompileInfo("等待编译…", true);
    setStatus("实时预览", "idle");

    // 6. 一进来先编译一轮，右侧 iframe 立刻有内容
    scheduleUpdate(true);
  }

  init();
})();
