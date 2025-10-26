(function () {
  const editor = document.getElementById("code-editor");
  const frame = document.getElementById("preview-frame");
  const overlay = document.getElementById("error-overlay");
  const compileBadge = document.getElementById("compile-info");
  const statusLabel = document.getElementById("status-label");
  const buttons = document.querySelectorAll("[data-action]");
  const compilerRetryButton = document.querySelector('[data-action="reload-compiler"]');

  const STORAGE_KEY = "code-playground-source";
  const COMPILE_ENDPOINT = "/api/compile-preview";
  const REQUEST_DEBOUNCE = 320;

  // 仅作为兜底示例，不影响你的测试文件
  const DEFAULT_SOURCE = `export default function Demo(){return <div className="min-h-screen grid place-items-center text-slate-200 bg-gradient-to-br from-slate-900 via-slate-950 to-black">准备就绪</div>}`;

  let debounceTimer = null;
  let lastSource = "";
  let currentBlobUrl = null;
  let activeRequestId = 0;
  let currentController = null;

  function setStatus(message, state = "idle") {
    const span = statusLabel.querySelector("span:last-child");
    if (span) span.textContent = message;
    statusLabel.dataset.state = state;
  }

  function setCompileInfo(message, good = true) {
    compileBadge.textContent = message;
    compileBadge.style.background = good ? "rgba(56,189,248,0.18)" : "rgba(248,113,113,0.12)";
    compileBadge.style.color = good ? "#38bdf8" : "#f87171";
    if (compilerRetryButton && good) compilerRetryButton.classList.remove("is-visible");
  }

  function showError(message, label = "编译失败") {
    overlay.textContent = message;
    overlay.classList.add("visible");
    setCompileInfo(label, false);
    setStatus("出现错误", "error");
  }
  function hideError() {
    overlay.textContent = "";
    overlay.classList.remove("visible");
  }

  window.addEventListener("message", (event) => {
    if (!event || !event.data || event.source !== frame.contentWindow) return;
    if (event.data.type === "CODE_PLAYGROUND_ERROR") {
      showError(event.data.message || "运行时出现错误", "运行时错误");
    }
  });

  function sanitizeScriptContent(js) {
    return (js || "")
      .replace(/<\/script>/gi, "<\\/script>")
      .replace(/<script/gi, "<\\\\script>")
      .replace(/<\/style>/gi, "<\\/style>");
  }

  // 生成 iframe 预览 HTML
  function buildPreviewHtml(js, css) {
    const script = sanitizeScriptContent(js);
    const styles = css || "";

    return `<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />

    <!-- 字体：Inter + JetBrains Mono（和 Tailwind fallback 一致） -->
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />

    <!-- Tailwind 实际生成的 utility（我们在 server 侧关闭了 preflight） -->
    <style id="tailwind-bundle">
${styles}
    </style>

    <!-- 预览环境基线（兜底：字体 / 阴影 / 滚动 / 表单控件） -->
    <style id="sandbox-baseline">
      /* 基本铺满，允许自然滚动 */
      html, body { margin: 0; padding: 0; height: 100%; }
      #root { height: 100%; min-height: 100%; }
      *, *::before, *::after { box-sizing: border-box; }
      body {
        font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
        background: transparent;
        color: inherit;
        overflow: auto; /* 允许页面滚动：你的滚动区（.cupertino-scroll）也会生效 */
      }
      button, input, select, textarea {
        font: inherit;
        color: inherit;
        background: transparent;
      }

      /* 兜底玻璃态阴影（即使没读取到你的定制 shadow，也能保持质感） */
      .shadow-glass-xl { box-shadow: 0 40px 120px rgba(15,23,42,0.45) !important; }

      /* 滚动体验优化：你的 ScrollArea 会再加具体样式 */
      .cupertino-scroll { -webkit-overflow-scrolling: touch; overscroll-behavior: contain; }

      /* 可选：更细的滚动条（与 cupertino 类风格一致，不因浏览器默认显得粗糙） */
      .cupertino-scroll { scrollbar-width: thin; scrollbar-color: rgba(60,60,67,0.36) transparent; }
      .cupertino-scroll::-webkit-scrollbar { width: 10px; height: 10px; }
      .cupertino-scroll::-webkit-scrollbar-track { background: transparent; margin: 6px; }
      .cupertino-scroll::-webkit-scrollbar-thumb { border-radius: 999px; border: 3px solid transparent; background-clip: padding-box; }
      .cupertino-scroll.cupertino-scroll--light::-webkit-scrollbar-thumb { background-color: rgba(60,60,67,0.28); }
      .cupertino-scroll.cupertino-scroll--light:hover::-webkit-scrollbar-thumb { background-color: rgba(60,60,67,0.45); }
      .cupertino-scroll.cupertino-scroll--dark::-webkit-scrollbar-thumb { background-color: rgba(235,235,245,0.25); }
      .cupertino-scroll.cupertino-scroll--dark:hover::-webkit-scrollbar-thumb { background-color: rgba(235,235,245,0.45); }
      .cupertino-scroll::-webkit-scrollbar-corner { background: transparent; }
    </style>
  </head>
  <body>
    <div id="root"></div>

    <!-- React 运行时 -->
    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>

    <!-- lucide-react / lucide 多种 UMD 变体（尽可能命中“真图标组件”或“核心节点”） -->
    <script src="https://unpkg.com/lucide-react@latest/dist/umd/lucide-react.js"></script>
    <script src="https://unpkg.com/lucide-react@latest/umd/lucide-react.min.js"></script>
    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>

    <!-- 小调试：看看全局是否挂到图标（可删除） -->
    <script>
      (function(){
        const cands = [
          window.lucideReact, window.LucideReact, window.lucide_react, window.lucideReactIcons, window.LucideReactIcons, // 组件版
          window.lucide, window.lucide_icons, window.lucideIcons, window.LucideIcons // 核心节点
        ];
        let sample = null, from = null;
        for (const lib of cands) {
          if (lib && typeof lib === 'object' && Object.keys(lib).length) {
            from = lib === window.lucide ? 'lucide' : 'other';
            sample = Object.keys(lib).slice(0, 8);
            break;
          }
        }
        console.log('[Preview] React:', !!window.React, 'ReactDOM:', !!window.ReactDOM, 'Lucide sample:', sample, 'from:', from);
      })();
    </script>

    <!-- 编译产物（IIFE） -->
    <script>
${script}
    </script>
  </body>
</html>`;
  }

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

    const cleanup = setTimeout(() => {
      if (currentBlobUrl === url) { try { URL.revokeObjectURL(url); currentBlobUrl = null; } catch {} }
    }, 10000);

    frame.onload = () => { clearTimeout(cleanup); if (currentBlobUrl === url) { try { URL.revokeObjectURL(url); currentBlobUrl = null; } catch {} } };
    frame.onerror = () => { clearTimeout(cleanup); try { URL.revokeObjectURL(url); if (currentBlobUrl === url) currentBlobUrl = null; } catch {} };
  }

  function handleCompileSuccess(js, css) {
    hideError();
    applyPreview(js, css);
    setCompileInfo("编译成功", true);
    setStatus("实时预览", "idle");
  }

  function handleCompileError(message) {
    showError(message || "编译失败");
    if (compilerRetryButton) compilerRetryButton.classList.add("is-visible");
  }

  async function requestPreview(source, requestId) {
    if (currentController) currentController.abort();
    const controller = new AbortController();
    currentController = controller;

    setCompileInfo("编译中…", true);
    setStatus("编译中", "running");
    hideError();

    const timeoutId = setTimeout(() => {
      controller.abort();
      if (requestId === activeRequestId) handleCompileError("编译超时（30秒），请检查代码复杂度");
    }, 30000);

    try {
      const resp = await fetch(COMPILE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (requestId !== activeRequestId || currentController !== controller) return;

      if (!resp.ok) {
        let msg = "编译失败";
        try { const data = await resp.json(); if (data?.error) msg = data.error; } catch { msg = resp.statusText || msg; }
        handleCompileError(msg);
        return;
      }
      const payload = await resp.json();
      if (!payload || typeof payload.js !== "string") { handleCompileError("编译服务返回了无效的结果"); return; }
      handleCompileSuccess(payload.js, typeof payload.css === "string" ? payload.css : "");
    } catch (e) {
      clearTimeout(timeoutId);
      if (e.name === "AbortError") return;
      if (requestId !== activeRequestId || currentController !== controller) return;
      handleCompileError(e.message || "网络异常，请稍后重试");
    } finally {
      if (currentController === controller) currentController = null;
    }
  }

  function scheduleUpdate(immediate = false) {
    const source = editor.value;
    if (!immediate && source === lastSource) return;
    const trigger = () => {
      lastSource = source;
      activeRequestId += 1;
      requestPreview(source, activeRequestId);
    };
    if (immediate) { trigger(); return; }
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(trigger, REQUEST_DEBOUNCE);
  }

  function saveToLocalStorage(key, value) {
    try { localStorage.setItem(key, value); return true; }
    catch (err) {
      console.error("LocalStorage save failed:", err);
      if (err.name === "QuotaExceededError") { setStatus("存储空间已满", "error"); setTimeout(() => setStatus("实时预览", "idle"), 3000); }
      return false;
    }
  }

  function handleAction(e) {
    const action = e.currentTarget.dataset.action;
    if (action === "reset") {
      editor.value = DEFAULT_SOURCE;
      localStorage.removeItem(STORAGE_KEY);
      scheduleUpdate(true);
      return;
    }
    if (action === "copy") {
      navigator.clipboard.writeText(editor.value)
        .then(() => { setStatus("已复制到剪贴板", "success"); setTimeout(() => setStatus("实时预览", "idle"), 1600); })
        .catch(() => setStatus("复制失败", "error"));
      return;
    }
    if (action === "format") {
      if (window.js_beautify) {
        const formatted = window.js_beautify(editor.value, { indent_size: 2, max_preserve_newlines: 2, space_in_empty_paren: false });
        editor.value = formatted;
        scheduleUpdate(true);
      } else {
        setStatus("格式化工具加载中", "running");
        setTimeout(() => setStatus("实时预览", "idle"), 1500);
      }
      return;
    }
    if (action === "reload-compiler") { scheduleUpdate(true); return; }
  }

  function init() {
    const stored = localStorage.getItem(STORAGE_KEY);
    editor.value = stored || DEFAULT_SOURCE;
    editor.addEventListener("input", () => { saveToLocalStorage(STORAGE_KEY, editor.value); scheduleUpdate(); });
    buttons.forEach((btn) => btn.addEventListener("click", handleAction));
    setCompileInfo("等待编译…", true);
    setStatus("实时预览", "idle");
    scheduleUpdate(true);
  }

  init();
})();
