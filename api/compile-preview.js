// api/compile-preview.js
//
// 服务器端实时编译器（给预览 iframe 用）。
// 功能：
//   1. 用 esbuild 把用户在编辑器里写的 React 组件打成一个 IIFE。
//   2. React / ReactDOM / lucide-react 通过全局(window.*)注入（不打包 node_modules）。
//   3. Tailwind 按需生成，强制关闭 preflight，避免 Vercel 读取 preflight.css 报 ENOENT。
//   4. 自动生成“虚拟 lucide-react 模块”以保证图标可用。
//   5. 去除导入白名单：除 Node 内置高危模块外，任意 npm 包（如 framer-motion）通过 esm.sh CDN 拉取并打包。
//   6. 强沙箱：禁 Node 内置、禁路径逃逸；修复 esm.sh 子依赖的“根相对路径/裸导入”解析。
// 兼容性：target 下调，避免移动端 Safari/Android WebView 语法错误。

const { build } = require("esbuild");
const path = require("path");
const { builtinModules } = require("module");
const postcss = require("postcss");
const tailwindcss = require("tailwindcss");
const loadConfig = require("tailwindcss/loadConfig");
const fs = require("fs/promises");
const os = require("os");
const https = require("https");
const http = require("http");

// ----------------------------------------------------------------------------
// Tailwind 配置发现
// ----------------------------------------------------------------------------

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

// 告诉 Vercel 打包 tailwindcss 本体与常见配置文件
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    ...TAILWIND_CONFIG_FILENAMES.map((n) => n),
    ...TAILWIND_CONFIG_FILENAMES.map((n) => path.posix.join("..", n)),
    "node_modules/tailwindcss/**/*",
  ])
);

// ----------------------------------------------------------------------------
// 外部依赖（通过 window.* 注入的“全局外部”）
// ----------------------------------------------------------------------------

const EXTERNAL_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);

// 禁 Node 内置模块 / 进程对象（高危）
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((n) => `node:${n}`),
  "process",
]);

// 虚拟入口常量
const USER_CODE_VIRTUAL_PATH = "user-code";     // 你的组件源码
const VIRTUAL_ENTRY_PATH   = "virtual-entry";   // 注入的 root/mount 脚本

// Tailwind 指令
const BASE_CSS = "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

// 缓存
let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

// ----------------------------------------------------------------------------
// 安全的 resolveDir（esbuild 需要一个根目录）
// ----------------------------------------------------------------------------
async function ensureResolveDir() {
  if (!cachedResolveDirPromise) {
    cachedResolveDirPromise = fs
      .mkdtemp(path.join(os.tmpdir(), "preview-entry-"))
      .catch(() => os.tmpdir());
  }
  return cachedResolveDirPromise;
}

// ----------------------------------------------------------------------------
// Tailwind 配置查找 + 加载
// ----------------------------------------------------------------------------
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
    } catch {
      // continue
    }
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

// ----------------------------------------------------------------------------
// lucide-react 动态模块生成
// ----------------------------------------------------------------------------
function extractLucideImports(userSource) {
  const results = [];
  const importRegex =
    /import\s*\{\s*([^}]+)\}\s*from\s*['"]lucide-react['"]/g;

  let match;
  while ((match = importRegex.exec(userSource)) !== null) {
    const inner = match[1];
    inner
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

function buildLucideModuleSource(lucideList) {
  const exportLines = lucideList.map(({ localName, remoteName }) => {
    return `export const ${localName} = getIcon("${remoteName}");`;
  });

  return `
    const React = window.React;
    const __missingLogged = Object.create(null);

    function PlaceholderIcon(props) {
      const size = props?.size ?? 24;
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
        React.createElement("circle", {
          cx: 12,
          cy: 12,
          r: 10,
          style: { opacity: 0.22 }
        }),
        React.createElement("line", {
          x1: 8,
          y1: 12,
          x2: 16,
          y2: 12
        })
      );
    }

    function guessCoreKeys(pascalName) {
      const kebab = pascalName
        .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
        .replace(/([A-Z])([A-Z][a-z])/g, '$1-$2')
        .replace(/([a-zA-Z])([0-9]+)/g, '$1-$2')
        .toLowerCase();

      const simpleLower =
        pascalName.charAt(0).toLowerCase() + pascalName.slice(1);

      return Array.from(
        new Set([kebab, simpleLower, pascalName, pascalName.toLowerCase()])
      );
    }

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
              if (Array.isArray(n) && typeof n[0] === "string") {
                const tag = n[0];
                const attrs = n[1] || {};
                return React.createElement(tag, { key: i, ...attrs });
              }
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

    function getIconNodesFromCore(core, pascalName) {
      if (!core) return null;

      const candidates = guessCoreKeys(pascalName);

      for (const key of candidates) {
        if (core.icons && Array.isArray(core.icons[key])) {
          return core.icons[key];
        }

        const direct = core[key];
        if (Array.isArray(direct)) {
          const maybeNodes = Array.isArray(direct[2]) ? direct[2] : null;
          if (maybeNodes) return maybeNodes;
        }

        if (direct && typeof direct === "object") {
          if (Array.isArray(direct.iconNode)) return direct.iconNode;
          if (Array.isArray(direct.node)) return direct.node;
        }
      }

      return null;
    }

    function getGlobalIconSource() {
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

      const coreCandidates = [
        window.lucide,
        window.lucide_icons,
        window.lucideIcons,
        window.LucideIcons
      ];

      for (const lib of coreCandidates) {
        if (lib && typeof lib === "object" && Object.keys(lib).length) {
          return { type: "core", lib };
        }
      }

      if (window.lucide && typeof window.lucide === "object") {
        return { type: "unknown", lib: window.lucide };
      }

      return { type: "none", lib: {} };
    }

    function getIcon(pascalName) {
      const { type, lib } = getGlobalIconSource();

      if (type === "components") {
        const Comp = lib[pascalName];
        if (typeof Comp === "function") {
          return Comp;
        }
      }

      if (type === "core") {
        const nodes = getIconNodesFromCore(lib, pascalName);
        if (nodes) {
          return createReactIconFromNodes(pascalName, nodes);
        }
      }

      if (type === "unknown") {
        const maybe = lib[pascalName];
        if (typeof maybe === "function") {
          return maybe;
        }
        const nodes = getIconNodesFromCore(lib, pascalName);
        if (nodes) {
          return createReactIconFromNodes(pascalName, nodes);
        }
      }

      if (!__missingLogged[pascalName]) {
        __missingLogged[pascalName] = 1;
        try {
          console.warn("[preview] lucide icon missing:", pascalName);
        } catch {}
      }

      return function MissingIcon(props) {
        return React.createElement(PlaceholderIcon, props);
      };
    }

    ${exportLines.join("\n")}

    export default (getGlobalIconSource().lib || {});
  `;
}

// ----------------------------------------------------------------------------
// 裸模块名 -> esm.sh CDN URL
// ----------------------------------------------------------------------------
function resolveBareToCDN(spec) {
  // 固定常用包版本和构建参数，减少 302 跳转
  const pinned = {
    "framer-motion":
      "https://esm.sh/framer-motion@11.18.2?external=react,react-dom&target=es2017",
  };
  if (pinned[spec]) return pinned[spec];

  // 其他包：latest + 外部化 react/react-dom，降级到 es2017
  return `https://esm.sh/${spec}@latest?external=react,react-dom&target=es2017`;
}

// ----------------------------------------------------------------------------
// http(s)/data: 导入插件：在打包阶段拉取 CDN 模块内容
// 兼容 esm.sh 返回的相对/根相对/裸导入（统一解析为绝对 URL 或 external-globals）
// ----------------------------------------------------------------------------
function httpImportPlugin() {
  return {
    name: "http-import",
    setup(buildCtx) {
      const urlFilter = /^https?:\/\//;

      // 识别初次出现的 http(s) URL
      buildCtx.onResolve({ filter: urlFilter }, (args) => ({
        path: args.path,
        namespace: "http-url",
      }));

      // 在 http-url 命名空间内，处理相对/根相对/裸导入 与 data:
      buildCtx.onResolve({ filter: /.*/, namespace: "http-url" }, (args) => {
        const spec = args.path;

        // 1) 已是 http(s) 或 data:，透传
        if (/^https?:\/\//i.test(spec) || spec.startsWith("data:")) {
          return { path: spec, namespace: "http-url" };
        }

        const isRelative = spec.startsWith("./") || spec.startsWith("../");
        const isRootAbs = spec.startsWith("/");

        // 2) 相对或根相对：基于 importer 解析为绝对 URL
        if (isRelative || isRootAbs) {
          try {
            const base = new URL(args.importer);
            const resolved = new URL(spec, base);
            return { path: resolved.toString(), namespace: "http-url" };
          } catch {
            return { path: spec, namespace: "http-url" };
          }
        }

        // 3) 裸导入：要么走 external-globals，要么映射到 CDN
        if (EXTERNAL_MODULES.has(spec)) {
          // 交给 external-globals（使用 window.*）
          return { path: spec, namespace: "external-globals" };
        }

        // 一些子模块形式如 'react/jsx-runtime' 也在 EXTERNAL_MODULES 里，已被上面捕获。
        // 其它裸导入 → esm.sh
        const cdn = resolveBareToCDN(spec);
        return { path: cdn, namespace: "http-url" };
      });

      // 加载 http-url 命名空间的内容
      buildCtx.onLoad({ filter: /.*/, namespace: "http-url" }, async (args) => {
        // data:URL 支持
        if (args.path.startsWith("data:")) {
          const comma = args.path.indexOf(",");
          const meta = args.path.slice(5, comma);
          const data = args.path.slice(comma + 1);
          const isBase64 = /;base64/i.test(meta);
          const mime = meta.split(";")[0] || "";
          const text = isBase64
            ? Buffer.from(data, "base64").toString("utf8")
            : decodeURIComponent(data);
          return {
            contents: text,
            loader: mime.includes("css") ? "css" : "js",
          };
        }

        const code = await fetchUrl(args.path);
        return {
          contents: code,
          loader: args.path.endsWith(".css") ? "css" : "js",
        };
      });
    },
  };
}

function fetchUrl(url, maxRedirect = 5) {
  return new Promise((resolve, reject) => {
    if (maxRedirect <= 0) return reject(new Error("Too many redirects"));

    const client = url.startsWith("https:") ? https : http;
    const req = client.get(url, (res) => {
      const { statusCode, headers } = res;
      if (statusCode >= 300 && statusCode < 400 && headers.location) {
        const next = headers.location.startsWith("http")
          ? headers.location
          : new URL(headers.location, url).toString();
        res.resume(); // 丢弃当前响应体
        return fetchUrl(next, maxRedirect - 1).then(resolve, reject);
      }

      if (statusCode !== 200) {
        res.resume();
        return reject(new Error(`GET ${url} -> ${statusCode}`));
      }

      let data = "";
      res.setEncoding("utf8");
      res.on("data", (d) => (data += d));
      res.on("end", () => resolve(data));
    });

    req.on("error", reject);
    req.end();
  });
}

// ----------------------------------------------------------------------------
// esbuild 插件：去白名单 + 注入外部全局 + CDN 改写
// ----------------------------------------------------------------------------
function createSecurityPlugin(resolveDir, lucideList) {
  return {
    name: "preview-security",
    setup(buildCtx) {
      buildCtx.onResolve({ filter: /.*/ }, (args) => {
        // 让 httpImportPlugin 处理 http-url 命名空间
        if (args.namespace === "http-url") return;

        // 1) 通过 window.* 注入的外部模块（不走 CDN）
        if (EXTERNAL_MODULES.has(args.path)) {
          return {
            path: args.path,
            namespace: "external-globals",
          };
        }

        // 2) 禁 Node 内置模块
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在沙箱中使用（Node 内置已禁用）。`,
              },
            ],
          };
        }

        // 3) 相对/绝对路径：必须在 resolveDir 下
        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const base = args.resolveDir || resolveDir;
          const resolved = path.resolve(base, args.path);
          if (!resolved.startsWith(base)) {
            return {
              errors: [{ text: `不允许访问受限目录之外的文件: ${args.path}` }],
            };
          }
          return { path: resolved };
        }

        // 4) 其他（裸模块名） => 改写到 CDN
        const cdnUrl = resolveBareToCDN(args.path);
        return { path: cdnUrl, namespace: "http-url" };
      });

      // 把外部注入模块映射到 window.*
      buildCtx.onLoad({ filter: /.*/, namespace: "external-globals" }, (args) => {
        if (args.path === "react") {
          return {
            loader: "js",
            contents: `
              const React = window.React;
              export default React;
              export const useState = React.useState;
              export const useEffect = React.useEffect;
              export const useRef = React.useRef;
              export const useMemo = React.useMemo;
              export const useCallback = React.useCallback;
              export const Fragment = React.Fragment;
            `,
          };
        }

        if (args.path === "react-dom") {
          return {
            loader: "js",
            contents: `
              const ReactDOM = window.ReactDOM;
              export default ReactDOM;
            `,
          };
        }

        if (args.path === "react-dom/client") {
          return {
            loader: "js",
            contents: `
              const ReactDOM = window.ReactDOM;
              if (!ReactDOM || !ReactDOM.createRoot) {
                throw new Error('ReactDOM.createRoot not found. Make sure ReactDOM 18+ is loaded in the iframe.');
              }
              export function createRoot(container) {
                return ReactDOM.createRoot(container);
              }
            `,
          };
        }

        if (args.path === "react/jsx-runtime") {
          return {
            loader: "js",
            contents: `
              const React = window.React;
              export const Fragment = React.Fragment;
              export function jsx(type, props, key) {
                return React.createElement(type, { ...props, key });
              }
              export function jsxs(type, props, key) {
                return React.createElement(type, { ...props, key });
              }
            `,
          };
        }

        if (args.path === "react/jsx-dev-runtime") {
          return {
            loader: "js",
            contents: `
              const React = window.React;
              export const Fragment = React.Fragment;
              export function jsxDEV(type, props, key) {
                return React.createElement(type, { ...props, key });
              }
            `,
          };
        }

        if (args.path === "lucide-react") {
          const lucideModuleSource = buildLucideModuleSource(lucideList);
          return { loader: "js", contents: lucideModuleSource };
        }

        return { errors: [{ text: `未知的 external 模块: ${args.path}` }] };
      });
    },
  };
}

// ----------------------------------------------------------------------------
// esbuild 错误 -> 字符串
// ----------------------------------------------------------------------------
function formatEsbuildError(error) {
  if (error && Array.isArray(error.errors) && error.errors.length > 0) {
    return error.errors
      .map((item) => {
        if (!item) return "未知的编译错误";
        const location = item.location
          ? `${item.location.file || "用户代码"}:${item.location.line}:${item.location.column}`
          : "";
        return `${location}${location ? " - " : ""}${item.text}`;
      })
      .join("\n");
  }
  return (error && error.message) || "编译失败";
}

// ----------------------------------------------------------------------------
// 把用户源码打成一个 IIFE
// ----------------------------------------------------------------------------
async function bundleSource(source) {
  const resolveDir = await ensureResolveDir();

  // 找出 lucide-react import 的符号
  const lucideList = extractLucideImports(source);

  // 插件组合：虚拟入口 + http 导入 + 安全/CDN 改写
  const securityPlugin = createSecurityPlugin(resolveDir, lucideList);

  const result = await build({
    write: false,
    bundle: true,
    format: "iife", // 直接 <script> 执行
    platform: "browser",
    // 为移动端下调 target，避免 iOS/Android 直接 SyntaxError
    target: ["es2017", "safari13", "ios13", "chrome58", "firefox60", "edge79"],
    treeShaking: true,
    logLevel: "silent",
    charset: "utf8",

    define: {
      "process.env.NODE_ENV": '"production"',
    },

    plugins: [
      {
        name: "preview-virtual-entry",
        setup(buildCtx) {
          // virtual-entry: 负责挂载到 #root，并把运行时错误上报给父窗口
          buildCtx.onResolve(
            { filter: new RegExp(`^${VIRTUAL_ENTRY_PATH}$`) },
            () => ({ path: VIRTUAL_ENTRY_PATH, namespace: "virtual" })
          );

          buildCtx.onLoad({ filter: /.*/, namespace: "virtual" }, () => ({
            loader: "tsx",
            resolveDir,
            contents: `
              import React from "react";
              import { createRoot } from "react-dom/client";
              import UserComponent from "${USER_CODE_VIRTUAL_PATH}";

              const reportError = (payload) => {
                try {
                  const detail =
                    payload && (payload.stack || payload.message)
                      ? (payload.stack || payload.message)
                      : String(payload);
                  if (window.parent && window.parent !== window) {
                    window.parent.postMessage(
                      { type: "CODE_PLAYGROUND_ERROR", message: detail },
                      "*"
                    );
                  }
                } catch (err) {
                  console.error(err);
                }
              };

              const mount = () => {
                const container = document.getElementById("root");
                if (!container) {
                  reportError(new Error("未找到用于渲染的 #root 容器"));
                  return;
                }
                try {
                  const root = createRoot(container);
                  root.render(React.createElement(UserComponent));
                } catch (error) {
                  console.error(error);
                  reportError(error);
                }
              };

              window.addEventListener("error", (event) => {
                if (!event) return;
                if (event.error) {
                  reportError(event.error);
                } else if (event.message) {
                  reportError(new Error(event.message));
                }
              });

              window.addEventListener("unhandledrejection", (event) => {
                if (event && event.reason) {
                  reportError(event.reason);
                }
              });

              if (document.readyState === "loading") {
                document.addEventListener("DOMContentLoaded", mount);
              } else {
                mount();
              }
            `,
          }));

          // user-code: 用户写的组件（要求 default export 一个 React 组件）
          buildCtx.onResolve(
            { filter: new RegExp(`^${USER_CODE_VIRTUAL_PATH}$`) },
            () => ({ path: USER_CODE_VIRTUAL_PATH, namespace: "user" })
          );

          buildCtx.onLoad({ filter: /.*/, namespace: "user" }, () => ({
            loader: "tsx",
            resolveDir,
            contents: source,
          }));
        },
      },

      // 让 esbuild 能拉取 CDN 的 http(s)/data: 模块，且能解析其相对/根相对/裸导入子依赖
      httpImportPlugin(),

      // 去白名单 + 注入外部全局 + CDN 改写
      securityPlugin,
    ],

    entryPoints: [VIRTUAL_ENTRY_PATH],
  });

  if (!result.outputFiles || result.outputFiles.length === 0) {
    throw new Error("未能生成可执行的预览脚本");
  }

  return result.outputFiles[0].text;
}

// ----------------------------------------------------------------------------
// Tailwind CSS 生成（按需裁剪 + 关闭 preflight）
// ----------------------------------------------------------------------------
async function generateTailwindCSS(source) {
  const cfg = await loadTailwindConfigOrFallback();

  // 关闭 preflight，避免 serverless 环境读不到 preflight.css
  let corePlugins = { preflight: false };
  if (
    cfg.corePlugins &&
    typeof cfg.corePlugins === "object" &&
    !Array.isArray(cfg.corePlugins)
  ) {
    corePlugins = { ...cfg.corePlugins, preflight: false };
  }

  const effectiveConfig = {
    ...cfg,
    corePlugins,
    content: [{ raw: source, extension: "jsx" }],
  };

  const result = await postcss([tailwindcss(effectiveConfig)]).process(
    BASE_CSS,
    { from: undefined }
  );

  return result.css;
}

// ----------------------------------------------------------------------------
// HTTP Handler
// ----------------------------------------------------------------------------
function parseRequestBody(req) {
  if (!req.body) return {};
  if (typeof req.body === "string") {
    try {
      return JSON.parse(req.body);
    } catch (err) {
      throw new Error("请求体不是合法的 JSON");
    }
  }
  return req.body;
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method === "OPTIONS") {
    res.status(204).end();
    return;
  }

  if (req.method !== "POST") {
    res.status(405).json({ error: "Method Not Allowed" });
    return;
  }

  let payload;
  try {
    payload = parseRequestBody(req);
  } catch (error) {
    res.status(400).json({ error: error.message || "请求体解析失败" });
    return;
  }

  const source = payload && payload.source;
  if (typeof source !== "string" || !source.trim()) {
    res.status(400).json({ error: "缺少有效的 source 字符串" });
    return;
  }

  try {
    const [js, css] = await Promise.all([
      bundleSource(source),
      generateTailwindCSS(source),
    ]);

    res.status(200).json({ js, css });
  } catch (error) {
    const statusCode =
      (error && typeof error.statusCode === "number" && error.statusCode) || 400;

    const message = formatEsbuildError(error);
    res.status(statusCode).json({ error: message });
  }
};

// 告诉 Vercel：把 tailwindcss 本体和 tailwind.config.* 打进函数包里
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
