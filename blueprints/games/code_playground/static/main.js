// blueprints/games/code_playground/static/main.js
//
// 浏览器端的实时预览控制器：
// - 读取编辑器代码
// - 请求 /api/compile-preview 得到 {js, css}
// - 动态生成 iframe HTML，里面挂 React / ReactDOM / lucide / Tailwind
// - 把任何编译期/运行期错误显示在 overlay
// - 本地存储上一次代码
//
// 这份是全量版本，包含状态提示、复制、格式化、重置等逻辑。
// 不要再砍。

(function () {
  // 页面上已有的 DOM 元素
  const editor = document.getElementById("code-editor"); // 文本编辑区 <textarea> 或 <code> 可编辑块
  const frame = document.getElementById("preview-frame"); // <iframe> 用来承载实时预览
  const overlay = document.getElementById("error-overlay"); // 错误浮层
  const compileBadge = document.getElementById("compile-info"); // 顶部/角落 显示“编译成功/失败”
  const statusLabel = document.getElementById("status-label"); // 状态文字，比如“实时预览 / 编译中...”
  const buttons = document.querySelectorAll("[data-action]"); // 复制、格式化、重置、手动重试等按钮
  const compilerRetryButton = document.querySelector('[data-action="reload-compiler"]');

  // 常量
  const STORAGE_KEY = "code-playground-source";
  const COMPILE_ENDPOINT = "/api/compile-preview";
  const REQUEST_DEBOUNCE = 320; // ms 防抖，避免每敲一个字就 POST

  // 当用户第一次进来时，如果 localStorage 没有内容，就用一个最小 demo
  // 这个只是兜底，不会覆盖你粘贴的“RemoteDesktopUI”测试文件
  const DEFAULT_SOURCE = [
    "import React from 'react';",
    "export default function Demo(){",
    "  return (",
    "    <div className=\"min-h-screen grid place-items-center text-slate-200 bg-gradient-to-br from-slate-900 via-slate-950 to-black font-sans\">",
    "      <div className=\"text-center space-y-4\">",
    "        <div className=\"text-2xl font-semibold\">准备就绪</div>",
    "        <div className=\"text-slate-500 text-sm\">你可以在左侧编辑 React + Tailwind 代码</div>",
    "      </div>",
    "    </div>",
    "  );",
    "}",
    ""
  ].join("\n");

  // 运行时状态
  let debounceTimer = null;
  let lastSource = "";
  let currentBlobUrl = null;
  let activeRequestId = 0;
  let currentController = null;

  // ---------------------------------------------------------------------------
  // 小工具：UI 状态
  // ---------------------------------------------------------------------------

  function setStatus(message, state = "idle") {
    // 假设 statusLabel 结构是：<div id="status-label"><span>●</span><span>实时预览</span></div>
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
      ? "rgba(56,189,248,0.18)" // 青色半透明
      : "rgba(248,113,113,0.12)"; // 红色半透明
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

  // 监听来自 iframe 内部的错误上报（runtime 期间 throw/unhandledrejection）
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
  // 工具：将编译后的 js/css 打包成 iframe 的完整 HTML 字符串
  // ---------------------------------------------------------------------------

  function sanitizeScriptContent(js) {
    // 防止 </script> 提前截断
    return (js || "")
      .replace(/<\/script>/gi, "<\\/script>")
      .replace(/<script/gi, "<\\\\script>")
      .replace(/<\/style>/gi, "<\\/style>");
  }

  function buildPreviewHtml(js, css) {
    const script = sanitizeScriptContent(js);
    const styles = css || "";

    // 重点：这里我们注入 baseline，这个 baseline 非常关键：
    // 1. 模拟 Tailwind preflight 的关键变量（特别是阴影所需的 --tw-shadow 等）
    // 2. 设定字体（Inter / JetBrains Mono）
    // 3. 处理 box-sizing、边框默认值等
    // 4. 锁住 body 的 overflow:hidden，配合组件内部 ScrollArea 的 overflow-y-auto -> 还原手机/桌面 App 布局
    // 5. 给 .cupertino-scroll 提供惯性滚动、滚动条样式
    //
    // 这直接解决了：
    // - “阴影看起来是一圈黑线”：因为没初始化 --tw-shadow 等变量，Tailwind 的 shadow-* 看起来像线
    // - 字体很普通
    // - 滚动区不滚
    // - 黑边问题（阴影+边框没 reset 时，卡片像被黑色1px边勾勒，没有柔和发光）

    return [
      "<!DOCTYPE html>",
      '<html lang="zh-CN">',
      "  <head>",
      '    <meta charset="utf-8" />',
      '    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />',

      // 引入字体堆栈，匹配我们 fallback Tailwind config
      '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />',
      '    <link rel="preconnect" href="https://fonts.googleapis.com" />',
      '    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />',

      // Tailwind 生成的 utilities (注意：我们在服务端关闭了 preflight)
      '    <style id="tailwind-bundle">',
      styles,
      "    </style>",

      // baseline：手工注入等价于“最小 preflight + App layout + 滚动 + 阴影变量”
      '    <style id="sandbox-baseline">',
      "      /* ========== 布局基线 ========== */",
      "      html, body {",
      "        margin: 0;",
      "        padding: 0;",
      "        height: 100%;",
      "      }",
      "      #root {",
      "        height: 100%;",
      "        min-height: 100%;",
      "      }",

      "      /* Tailwind preflight 中非常关键的一部分：全局 box-sizing 和边框/阴影变量 */",
      "      *, ::before, ::after {",
      "        box-sizing: border-box;",
      "        /* Tailwind 默认也会把边框设定为 solid + 0px，避免奇怪的默认边框样式 */",
      "        border-width: 0;",
      "        border-style: solid;",
      "        border-color: currentColor;",

      "        /* ---- 以下是 Tailwind 用到的 CSS 变量初始化 ---- */",
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

      "      /* 字体、抗锯齿、默认背景/颜色基线 */",
      "      body {",
      "        font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;",
      "        -webkit-font-smoothing: antialiased;",
      "        text-rendering: optimizeLegibility;",
      "        background: transparent;",
      "        color: inherit;",

      // 注意：为的是模拟“App 全屏容器”布局。
      // App 的真实滚动区域通常是中间 ScrollArea，而不是 <body>。
      "        overflow: hidden;",
      "      }",

      "      button, input, select, textarea {",
      "        font: inherit;",
      "        color: inherit;",
      "        background: transparent;",
      "      }",

      "      /* 玻璃态阴影：即使 tailwind.config 没被正确读取，也依旧给 shadow-glass-xl 提供漂亮投影 */",
      "      .shadow-glass-xl {",
      "        --tw-shadow: 0 40px 120px rgba(15,23,42,0.45);",
      "        box-shadow: var(--tw-ring-offset-shadow,0 0 #0000),",
      "                    var(--tw-ring-shadow,0 0 #0000),",
      "                    var(--tw-shadow);",
      "      }",

      "      /* 就算使用 shadow-xl / shadow-2xl 等，也会有柔和的阴影，不只是1px黑边 */",
      "      .shadow-xl, .shadow-2xl, .shadow-glass-xl {",
      "        /* 我们不额外用filter去加黑框，依赖上面的 --tw-shadow 扩散 */",
      "      }",

      "      /* cupertino-scroll 是你 ScrollArea 里的实际滚动容器：我们强制让它可滚，带惯性，且高度锁满 flex-1 区域 */",
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

      // React 运行时 (UMD) -> window.React / window.ReactDOM / window.ReactDOM.createRoot
      '    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>',
      '    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>',

      // lucide 核心 UMD：
      //   window.lucide.icons = { "monitor":[["rect", {...}], ...], "gamepad-2":[["path",{...}], ...], ... }
      // compile-preview.js 里的 getIcon() 会用这些节点生成真正的 React 组件
      '    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>',

      // Debug 输出，方便确认我们拿到了哪些图标
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

      // 最终编译产物（IIFE）
      "    <script>",
      script,
      "    </script>",

      "  </body>",
      "</html>",
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // 将预览 HTML 注入 iframe
  // ---------------------------------------------------------------------------

  function applyPreview(js, css) {
    // 老的 blobURL 需要清理，避免内存泄漏
    if (currentBlobUrl) {
      try {
        URL.revokeObjectURL(currentBlobUrl);
      } catch (err) {
        // ignore
      }
      currentBlobUrl = null;
    }

    const html = buildPreviewHtml(js, css);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    currentBlobUrl = url;

    // 使用 blob URL 而不是 srcdoc，因为大型代码+样式在某些沙箱策略下 srcdoc 可能被限制
    frame.removeAttribute("srcdoc");
    frame.src = url;

    // 清理 blob URL 的两段式逻辑：
    // 1. 如果 onload 正常执行，就 revoke
    // 2. 否则 10 秒后兜底 revoke
    const cleanupTimeout = setTimeout(() => {
      if (currentBlobUrl === url) {
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (err) {
          // ignore
        }
      }
    }, 10000);

    frame.onload = () => {
      clearTimeout(cleanupTimeout);
      if (currentBlobUrl === url) {
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (err) {
          // ignore
        }
      }
    };

    frame.onerror = () => {
      clearTimeout(cleanupTimeout);
      try {
        URL.revokeObjectURL(url);
        if (currentBlobUrl === url) {
          currentBlobUrl = null;
        }
      } catch (err) {
        // ignore
      }
    };
  }

  // ---------------------------------------------------------------------------
  // 成功 / 失败 时更新 UI
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
  // 发请求给 /api/compile-preview
  // ---------------------------------------------------------------------------

  async function requestPreview(source, requestId) {
    // 取消前一次尚未完成的请求
    if (currentController) {
      currentController.abort();
    }

    const controller = new AbortController();
    currentController = controller;

    setCompileInfo("编译中…", true);
    setStatus("编译中", "running");
    hideError();

    // 30s 超时兜底
    const timeoutId = setTimeout(() => {
      controller.abort();
      if (requestId === activeRequestId) {
        handleCompileError("编译超时（30秒），请检查代码复杂度");
      }
    }, 30000);

    try {
      const response = await fetch(COMPILE_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ source }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // 如果这次请求已经不是最新的请求了，结果直接丢弃
      if (requestId !== activeRequestId || currentController !== controller) {
        return;
      }

      // 非 2xx
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

      // 正常返回 json
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

      // 被我们主动 Abort 的，就别喊错
      if (error.name === "AbortError") {
        return;
      }
      // 已经不是最新的请求了，也别动 UI
      if (requestId !== activeRequestId || currentController !== controller) {
        return;
      }

      handleCompileError(error.message || "网络异常，请稍后重试");
    } finally {
      // 释放 controller
      if (currentController === controller) {
        currentController = null;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 调度编译（带防抖）
  // ---------------------------------------------------------------------------

  function scheduleUpdate(immediate = false) {
    const source = editor.value;
    if (!immediate && source === lastSource) {
      // 没改就别编译
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
  // 工具按钮点击处理：reset / copy / format / reload-compiler
  // ---------------------------------------------------------------------------

  function handleAction(event) {
    const action = event.currentTarget.dataset.action;

    // 重置到 DEFAULT_SOURCE
    if (action === "reset") {
      editor.value = DEFAULT_SOURCE;
      localStorage.removeItem(STORAGE_KEY);
      scheduleUpdate(true);
      return;
    }

    // 复制到剪贴板
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
        // 如果你的页面还没把 js_beautify 挂过来，可以在 UI 提示一下
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
  // 初始化：加载本地存储的代码，绑定事件，触发首轮编译
  // ---------------------------------------------------------------------------

  function init() {
    const stored = localStorage.getItem(STORAGE_KEY);
    editor.value = stored || DEFAULT_SOURCE;

    // 监听编辑器变化 -> 防抖编译 + 本地存储
    editor.addEventListener("input", () => {
      saveToLocalStorage(STORAGE_KEY, editor.value);
      scheduleUpdate();
    });

    // 各种操作按钮
    buttons.forEach((btn) => btn.addEventListener("click", handleAction));

    // 初始 UI 状态
    setCompileInfo("等待编译…", true);
    setStatus("实时预览", "idle");

    // 马上跑一轮编译，展示初始画面
    scheduleUpdate(true);
  }

  init();
})();
