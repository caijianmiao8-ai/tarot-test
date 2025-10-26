// api/compile-preview.js
//
// ✅ 目标：在 Vercel Serverless 上稳定编译 + 预览 React 代码，且：
// 1) 彻底解决 "Element type is invalid"（lucide-react 命名导出静态化）
// 2) 图标优先展示真图标（lucide-react UMD），拿不到就从 lucide 核心节点生成 React 组件
// 3) Tailwind 关闭 preflight（规避 ENOENT），阴影/滚动/字体由前端 baseline 兜底
// 4) 严格沙箱（禁 Node 内置、禁任意第三方 import）
// ----------------------------------------------------------------------

const { build } = require("esbuild");
const path = require("path");
const { builtinModules } = require("module");
const postcss = require("postcss");
const tailwindcss = require("tailwindcss");
const loadConfig = require("tailwindcss/loadConfig");
const fs = require("fs/promises");
const os = require("os");

// ---- Tailwind config 搜索 ---------------------------------------------------
const TAILWIND_CONFIG_FILENAMES = [
  "tailwind.config.js",
  "tailwind.config.cjs",
  "tailwind.config.mjs",
  "tailwind.config.ts",
];
const EXTRA_CONFIG_LOCATIONS = [
  "styles/tailwind.config.js",
  "styles/tailwind.config.cjs",
  "styles/tailwind.config.mjs",
  "styles/tailwind.config.ts",
  "src/tailwind.config.js",
  "src/tailwind.config.cjs",
  "src/tailwind.config.mjs",
  "src/tailwind.config.ts",
];
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    ...TAILWIND_CONFIG_FILENAMES.map((n) => n),
    ...TAILWIND_CONFIG_FILENAMES.map((n) => path.posix.join("..", n)),
    "node_modules/tailwindcss/**/*",
  ])
);

// ---- 外部模块白名单 ---------------------------------------------------------
const EXTERNAL_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);

// 禁 Node 内置模块
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((n) => `node:${n}`),
  "process",
]);

// esbuild 虚拟入口
const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

// Tailwind 基础指令
const BASE_CSS = "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

// 缓存
let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

// ---- 保障沙箱根目录 ----------------------------------------------------------
async function ensureResolveDir() {
  if (!cachedResolveDirPromise) {
    cachedResolveDirPromise = fs
      .mkdtemp(path.join(os.tmpdir(), "preview-entry-"))
      .catch(() => os.tmpdir());
  }
  return cachedResolveDirPromise;
}

// ---- Tailwind config 发现 ----------------------------------------------------
function getAllCandidateConfigPaths() {
  const baseDirs = Array.from(
    new Set([
      process.cwd(),
      path.join(process.cwd(), ".."),
      __dirname,
      path.join(__dirname, ".."),
    ])
  );
  const names = [...TAILWIND_CONFIG_FILENAMES, ...EXTRA_CONFIG_LOCATIONS];
  const results = [];
  for (const base of baseDirs) {
    for (const name of names) {
      results.push(path.join(base, name));
    }
  }
  return results;
}

async function findTailwindConfig() {
  if (cachedTailwindConfigPath) return cachedTailwindConfigPath;
  const candidates = getAllCandidateConfigPaths();
  for (const full of candidates) {
    try {
      await fs.access(full);
      cachedTailwindConfigPath = full;
      console.info(`[compile-preview] Tailwind config FOUND at: ${full}`);
      return cachedTailwindConfigPath;
    } catch {}
  }
  console.warn(
    `[compile-preview] No Tailwind config found. cwd=${process.cwd()} __dirname=${__dirname}`
  );
  return null;
}

async function loadTailwindConfigOrFallback() {
  if (cachedTailwindConfig) return cachedTailwindConfig;
  const configPath = await findTailwindConfig();
  if (configPath) {
    try {
      cachedTailwindConfig = loadConfig(configPath);
      return cachedTailwindConfig;
    } catch (err) {
      console.error(
        `[compile-preview] Failed to load Tailwind config: ${err?.stack || err}`
      );
    }
  }
  console.warn("[compile-preview] Using internal fallback Tailwind config");
  cachedTailwindConfig = {
    darkMode: "class",
    theme: {
      extend: {
        fontFamily: {
          sans: [
            "Inter",
            "system-ui",
            "-apple-system",
            "BlinkMacSystemFont",
            "Segoe UI",
            "sans-serif",
          ],
          mono: [
            "JetBrains Mono",
            "ui-monospace",
            "SFMono-Regular",
            "Menlo",
            "monospace",
          ],
        },
        borderRadius: {
          xl: "1.25rem",
          "2xl": "1.5rem",
          "3xl": "1.75rem",
        },
        boxShadow: {
          "glass-xl": "0 40px 120px rgba(15,23,42,0.45)",
        },
      },
    },
    plugins: [],
  };
  return cachedTailwindConfig;
}

// ---- 收集 lucide-react 命名导入 ---------------------------------------------
function extractLucideImports(userSource) {
  const results = [];
  const re = /import\s*\{\s*([^}]+)\}\s*from\s*['"]lucide-react['"]/g;
  let m;
  while ((m = re.exec(userSource)) !== null) {
    m[1]
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .forEach((part) => {
        const mm = part.split(/\s+as\s+/i);
        const remoteName = mm[0].trim();
        const localName = (mm[1] ? mm[1] : remoteName).trim();
        if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(localName)) {
          results.push({ localName, remoteName });
        }
      });
  }
  const dedup = new Map();
  for (const item of results) {
    if (!dedup.has(item.localName)) dedup.set(item.localName, item);
  }
  return Array.from(dedup.values());
}

// ---- 生成 lucide-react 虚拟 ESM 模块 ----------------------------------------
// 优先用 UMD 的 React 组件；若只有 lucide 核心节点（数组/对象），就地生 React 组件；最后才占位。
function buildLucideModuleSource(list) {
  const exportLines = list.map(({ localName, remoteName }) => {
    return `export const ${localName} = getIcon("${remoteName}");`;
  });

  return `
    const React = window.React;
    const __missingLogged = Object.create(null);

    function PlaceholderIcon(props) {
      const size = (props && props.size) ? props.size : 24;
      const className = props?.className || "";
      const strokeWidth = props?.strokeWidth ?? 2;
      const color = props?.color || "currentColor";
      return React.createElement(
        "svg",
        {
          width: size,
          height: size,
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: color,
          strokeWidth,
          strokeLinecap: "round",
          strokeLinejoin: "round",
          className
        },
        React.createElement("circle", { cx: 12, cy: 12, r: 10, style: { opacity: 0.22 } }),
        React.createElement("line", { x1: 8, y1: 12, x2: 16, y2: 12 })
      );
    }

    // 将 lucide 核心节点（数组或对象）转换为 React 组件
    function createReactIconFromNodes(name, nodes) {
      const Icon = React.forwardRef(function Icon(props, ref) {
        const {
          size = 24,
          color = "currentColor",
          strokeWidth = 2,
          className,
          ...rest
        } = props || {};
        const children = Array.isArray(nodes)
          ? nodes.map((n, i) => {
              // 形如 ["path", { d: "..." }]
              if (Array.isArray(n) && typeof n[0] === "string") {
                const tag = n[0];
                const attrs = n[1] || {};
                return React.createElement(tag, { key: i, ...attrs });
              }
              // 形如 {tag:"path", attrs:{...}}
              if (n && typeof n === "object" && typeof n.tag === "string") {
                return React.createElement(n.tag, { key: i, ...(n.attrs || {}) });
              }
              return null;
            })
          : null;

        return React.createElement(
          "svg",
          {
            ref,
            width: size,
            height: size,
            viewBox: "0 0 24 24",
            fill: "none",
            stroke: color,
            strokeWidth,
            strokeLinecap: "round",
            strokeLinejoin: "round",
            className,
            ...rest
          },
          children
        );
      });
      Icon.displayName = name;
      return Icon;
    }

    function getIconNodesFromCore(core, name) {
      if (!core) return null;

      // 常见几种形态：
      // 1) core[name] = ["svg", attrs, [ ["path",{...}], ... ]]
      // 2) core.icons?.[name] = [ ["path",{...}], ... ]
      // 3) core[name] = { iconNode: [ ["path",{...}], ... ] }
      // 4) core[name] = { node: [ ["path",{...}], ... ] }
      const v1 = core[name];
      if (Array.isArray(v1)) {
        const arr = v1;
        const nodes = Array.isArray(arr[2]) ? arr[2] : null;
        if (nodes) return nodes;
      }
      const v2 = core.icons && core.icons[name];
      if (Array.isArray(v2)) return v2;

      const v3 = core[name];
      if (v3 && typeof v3 === "object") {
        if (Array.isArray(v3.iconNode)) return v3.iconNode;
        if (Array.isArray(v3.node)) return v3.node;
      }

      return null;
    }

    function getGlobalIconMap() {
      // 这些里通常有 “React 组件版图标”
      const componentCandidates = [
        window.lucideReact,
        window.LucideReact,
        window.lucide_react,
        window.lucideReactIcons,
        window.LucideReactIcons
      ];

      for (const lib of componentCandidates) {
        if (lib && typeof lib === "object" && Object.keys(lib).length) {
          return { type: "components", lib };
        }
      }

      // 这些里通常是 “原始节点定义”
      const coreCandidates = [
        window.lucide,          // 常见
        window.lucide_icons,    // 变种
        window.lucideIcons,
        window.LucideIcons
      ];
      for (const lib of coreCandidates) {
        if (lib && typeof lib === "object" && Object.keys(lib).length) {
          return { type: "core", lib };
        }
      }

      // 某些 UMD 直接把组件挂在 window.lucide 上（少见）
      if (window.lucide && typeof window.lucide === "object" && Object.keys(window.lucide).length) {
        return { type: "unknown", lib: window.lucide };
      }

      return { type: "none", lib: {} };
    }

    function getIcon(name) {
      const { type, lib } = getGlobalIconMap();

      if (type === "components") {
        const Comp = lib[name];
        if (typeof Comp === "function") return Comp;
      } else if (type === "core") {
        const nodes = getIconNodesFromCore(lib, name);
        if (nodes) return createReactIconFromNodes(name, nodes);
      } else if (type === "unknown") {
        const maybe = lib[name];
        if (typeof maybe === "function") return maybe;
        const nodes = getIconNodesFromCore(lib, name);
        if (nodes) return createReactIconFromNodes(name, nodes);
      }

      if (!__missingLogged[name]) {
        __missingLogged[name] = 1;
        try { console.warn("[preview] lucide icon missing:", name); } catch {}
      }
      return function MissingIcon(props) { return React.createElement(PlaceholderIcon, props); };
    }

    ${exportLines.join("\n")}

    // default 导出兜底
    export default (getGlobalIconMap().lib || {});
  `;
}

// ---- 安全插件：白名单注入 + 禁 Node 内置 + 阻止目录逃逸 ---------------------
function createSecurityPlugin(resolveDir, lucideList) {
  return {
    name: "preview-security",
    setup(buildCtx) {
      buildCtx.onResolve({ filter: /.*/ }, (args) => {
        if (EXTERNAL_MODULES.has(args.path)) {
          return { path: args.path, namespace: "external-globals" };
        }
        if (NODE_BUILTINS.has(args.path)) {
          return { errors: [{ text: `模块 "${args.path}" 不允许在沙箱中使用。` }] };
        }
        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const base = args.resolveDir || resolveDir;
          const resolved = path.resolve(base, args.path);
          if (!resolved.startsWith(base)) {
            return { errors: [{ text: `不允许访问受限目录之外的文件: ${args.path}` }] };
          }
          return { path: resolved };
        }
        return {
          errors: [{ text: `模块 "${args.path}" 不在允许白名单中（仅支持 React/ReactDOM/lucide-react/当前文件）。` }],
        };
      });

      buildCtx.onLoad({ filter: /.*/, namespace: "external-globals" }, (args) => {
        if (args.path === "react") {
          return { loader: "js", contents: `
            const React = window.React;
            export default React;
            export const useState = React.useState;
            export const useEffect = React.useEffect;
            export const useRef = React.useRef;
            export const useMemo = React.useMemo;
            export const useCallback = React.useCallback;
            export const Fragment = React.Fragment;
          ` };
        }
        if (args.path === "react-dom") {
          return { loader: "js", contents: `export default window.ReactDOM;` };
        }
        if (args.path === "react-dom/client") {
          return { loader: "js", contents: `
            const ReactDOM = window.ReactDOM;
            if (!ReactDOM?.createRoot) throw new Error('ReactDOM.createRoot not found.');
            export function createRoot(container){ return ReactDOM.createRoot(container); }
          ` };
        }
        if (args.path === "react/jsx-runtime") {
          return { loader: "js", contents: `
            const React = window.React;
            export const Fragment = React.Fragment;
            export function jsx(t,p,k){ return React.createElement(t,{...p,key:k}); }
            export function jsxs(t,p,k){ return React.createElement(t,{...p,key:k}); }
          ` };
        }
        if (args.path === "react/jsx-dev-runtime") {
          return { loader: "js", contents: `
            const React = window.React;
            export const Fragment = React.Fragment;
            export function jsxDEV(t,p,k){ return React.createElement(t,{...p,key:k}); }
          ` };
        }
        if (args.path === "lucide-react") {
          return { loader: "js", contents: buildLucideModuleSource(lucideList) };
        }
        return { errors: [{ text: `未知 external 模块: ${args.path}` }] };
      });
    },
  };
}

// ---- 工具：格式化 esbuild 错误 ----------------------------------------------
function formatEsbuildError(error) {
  if (error?.errors?.length) {
    return error.errors.map((e) => {
      const loc = e.location ? `${e.location.file || "用户代码"}:${e.location.line}:${e.location.column}` : "";
      return `${loc}${loc ? " - " : ""}${e.text}`;
    }).join("\n");
  }
  return error?.message || "编译失败";
}

// ---- 打包用户代码为 IIFE ----------------------------------------------------
async function bundleSource(source) {
  const resolveDir = await ensureResolveDir();
  const lucideList = extractLucideImports(source);
  const securityPlugin = createSecurityPlugin(resolveDir, lucideList);

  const result = await build({
    write: false,
    bundle: true,
    format: "iife",
    target: ["es2018"],
    platform: "browser",
    treeShaking: true,
    logLevel: "silent",
    define: { "process.env.NODE_ENV": '"production"' },
    plugins: [
      {
        name: "preview-virtual-entry",
        setup(b) {
          b.onResolve({ filter: new RegExp(`^${VIRTUAL_ENTRY_PATH}$`) }, () => ({ path: VIRTUAL_ENTRY_PATH, namespace: "virtual" }));
          b.onLoad({ filter: /.*/, namespace: "virtual" }, () => ({
            loader: "tsx",
            resolveDir,
            contents: `
              import React from "react";
              import { createRoot } from "react-dom/client";
              import UserComponent from "${USER_CODE_VIRTUAL_PATH}";

              const report = (p)=>{ try{
                const d = p?.stack || p?.message || String(p);
                if (window.parent && window.parent !== window) {
                  window.parent.postMessage({ type:"CODE_PLAYGROUND_ERROR", message:d },"*");
                }
              }catch(e){} };

              function mount(){
                const el = document.getElementById("root");
                if(!el) return report(new Error("未找到 #root"));
                try { createRoot(el).render(React.createElement(UserComponent)); }
                catch(err){ console.error(err); report(err); }
              }
              window.addEventListener("error", e => { if(e?.error) report(e.error); else if(e?.message) report(new Error(e.message)); });
              window.addEventListener("unhandledrejection", e => { if(e?.reason) report(e.reason); });
              if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
            `,
          }));
          b.onResolve({ filter: new RegExp(`^${USER_CODE_VIRTUAL_PATH}$`) }, () => ({ path: USER_CODE_VIRTUAL_PATH, namespace: "user" }));
          b.onLoad({ filter: /.*/, namespace: "user" }, () => ({ loader: "tsx", resolveDir, contents: source }));
        },
      },
      securityPlugin,
    ],
    entryPoints: [VIRTUAL_ENTRY_PATH],
  });

  if (!result.outputFiles?.length) throw new Error("未能生成可执行预览脚本");
  return result.outputFiles[0].text;
}

// ---- 生成 Tailwind CSS（关闭 preflight 规避 ENOENT） ------------------------
async function generateTailwindCSS(source) {
  const cfg = await loadTailwindConfigOrFallback();

  let corePlugins = { preflight: false };
  if (cfg.corePlugins && typeof cfg.corePlugins === "object" && !Array.isArray(cfg.corePlugins)) {
    corePlugins = { ...cfg.corePlugins, preflight: false };
  }

  const effective = { ...cfg, corePlugins, content: [{ raw: source, extension: "jsx" }] };
  const result = await postcss([tailwindcss(effective)]).process(BASE_CSS, { from: undefined });
  return result.css;
}

// ---- HTTP handler -----------------------------------------------------------
function parseRequestBody(req) {
  if (!req.body) return {};
  if (typeof req.body === "string") {
    try { return JSON.parse(req.body); } catch { throw new Error("请求体不是合法的 JSON"); }
  }
  return req.body;
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method === "OPTIONS") { res.status(204).end(); return; }
  if (req.method !== "POST") { res.status(405).json({ error: "Method Not Allowed" }); return; }

  let payload;
  try { payload = parseRequestBody(req); }
  catch (e) { res.status(400).json({ error: e.message || "请求体解析失败" }); return; }

  const source = payload?.source;
  if (typeof source !== "string" || !source.trim()) {
    res.status(400).json({ error: "缺少有效的 source 字符串" });
    return;
  }

  try {
    const [js, css] = await Promise.all([bundleSource(source), generateTailwindCSS(source)]);
    res.status(200).json({ js, css });
  } catch (error) {
    res.status(error?.statusCode || 400).json({ error: formatEsbuildError(error) });
  }
};

module.exports.config = { includeFiles: TAILWIND_INCLUDE_FILES };
