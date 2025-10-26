// api/compile-preview.js
// 最终版：
// 1. 动态生成 lucide-react 的命名导出（按用户真正 import 的图标名生成）
// 2. 每个导出的图标都是有效的 React 组件：要么是真图标，要么是安全占位符
// 3. 彻底解决 "Element type is invalid ... got: undefined" 这种报错
// 4. Tailwind fallback 日志仍然会出现，这只是提示，没有副作用

const { build } = require("esbuild");
const path = require("path");
const { builtinModules } = require("module");
const postcss = require("postcss");
const tailwindcss = require("tailwindcss");
const loadConfig = require("tailwindcss/loadConfig");
const fs = require("fs/promises");
const os = require("os");

// === tailwind 相关路径推测 ===
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

// vercel runtime 打包需要
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),
    ...TAILWIND_CONFIG_FILENAMES.map((name) => path.posix.join("..", name)),
    "node_modules/tailwindcss/**/*",
  ])
);

// 我们允许的外部依赖（在浏览器跑，不打进 bundle，或者用我们动态生成的 polyfill）
const EXTERNAL_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);

// 禁 node 内置
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

// esbuild 的两个虚拟入口名
const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

const BASE_CSS =
  "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

/**
 * 创建临时 resolveDir，作为 esbuild 的安全沙箱根目录
 */
async function ensureResolveDir() {
  if (!cachedResolveDirPromise) {
    cachedResolveDirPromise = fs
      .mkdtemp(path.join(os.tmpdir(), "preview-entry-"))
      .catch(() => os.tmpdir());
  }
  return cachedResolveDirPromise;
}

/**
 * 给 tailwind 找可能的 config 路径
 */
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

/**
 * 实际探测 tailwind config
 */
async function findTailwindConfig() {
  if (cachedTailwindConfigPath) return cachedTailwindConfigPath;

  const candidates = getAllCandidateConfigPaths();
  for (const full of candidates) {
    try {
      await fs.access(full);
      cachedTailwindConfigPath = full;
      console.info(
        `[compile-preview] Tailwind config FOUND at: ${full}`
      );
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

/**
 * 载入 tailwind 配置，否则用 fallback
 */
async function loadTailwindConfigOrFallback() {
  if (cachedTailwindConfig) return cachedTailwindConfig;

  const configPath = await findTailwindConfig();
  if (configPath) {
    try {
      cachedTailwindConfig = loadConfig(configPath);
      return cachedTailwindConfig;
    } catch (err) {
      console.error(
        `[compile-preview] Failed to load Tailwind config: ${
          err?.stack || err
        }`
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

/**
 * 把用户源码里 "import {...} from 'lucide-react'" 的内容抽出来
 * 返回数组: [{ localName: 'Monitor', remoteName: 'Monitor' }, ...]
 * 也支持别名: import { Monitor as MonitorIcon } ...
 * → { localName: 'MonitorIcon', remoteName: 'Monitor' }
 */
function extractLucideImports(userSource) {
  const results = [];
  const importRegex =
    /import\s*\{\s*([^}]+)\}\s*from\s*['"]lucide-react['"]/g;

  let match;
  while ((match = importRegex.exec(userSource)) !== null) {
    const inner = match[1]; // "Monitor, Wifi, Shield as ShieldIcon, ..."
    inner.split(",").forEach((rawPart) => {
      const part = rawPart.trim();
      if (!part) return;
      // 支持 "Name as Alias"
      const m = part.split(/\s+as\s+/i);
      const remoteName = m[0].trim();
      const localName = m[1] ? m[1].trim() : remoteName;
      // 只要是合法的 JS 变量名我们就记录
      if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(localName)) {
        results.push({ localName, remoteName });
      }
    });
  }

  // 去重，同一个 localName 只保留第一个
  const dedupMap = new Map();
  for (const item of results) {
    if (!dedupMap.has(item.localName)) {
      dedupMap.set(item.localName, item);
    }
  }
  return Array.from(dedupMap.values());
}

/**
 * 生成 lucide-react 这个虚拟模块的源码（ESM!）
 * 我们为用户 import 的每个图标名显式写出命名导出：
 *
 *   export const Monitor = getIcon("Monitor");
 *   export const Wifi = getIcon("Wifi");
 *   export const Shield = getIcon("Shield");
 *
 * getIcon() 会在运行时从 window.lucide / window.LucideReact 里拿真组件，
 * 拿不到就返回一个安全占位组件（不会是 undefined）。
 *
 * 这样 esbuild 会看到这些静态命名导出，
 * 不会再去做那种“解构 CommonJS 返回对象”的套路，
 * React 也就不会再拿到 undefined。
 */
function buildLucideModuleSource(lucideList) {
  // 如果用户没有 import 任何图标，也要返回个最小模块，避免 esbuild 报错
  const exportLines = lucideList.map(({ localName, remoteName }) => {
    return `export const ${localName} = getIcon("${remoteName}");`;
  });

  return `
    const React = window.React;

    function PlaceholderIcon(props) {
      const size = (props && props.size) ? props.size : 16;
      const className = props && props.className ? props.className : "";
      const style = {
        display: 'inline-block',
        width: size + 'px',
        height: size + 'px',
        borderRadius: '4px',
        backgroundColor: 'rgba(148,163,184,0.4)', // slate-400/40
        border: '1px solid rgba(148,163,184,0.6)', // slate-400/60
        lineHeight: 0
      };
      return React.createElement('span', { style, className });
    }

    function getIcon(name) {
      const lib = window.lucide || window.LucideReact || {};
      const Comp = lib[name];
      if (Comp) {
        return Comp;
      }
      // 返回一个真正的函数组件包装 PlaceholderIcon，
      // 确保 React 看到的是 function () { ... }，而不是直接的元素
      return function MissingIcon(props) {
        return React.createElement(PlaceholderIcon, props);
      };
    }

    ${exportLines.join("\n")}

    // 给一个默认导出，虽然基本用不到，但可以防止各种奇怪用法崩溃
    const __lucideDefault = window.lucide || window.LucideReact || {};
    export default __lucideDefault;
  `;
}

/**
 * 安全插件：
 * - 限制 import 来源，阻止 Node 内置模块
 * - 把 react / react-dom / react/jsx-runtime 之类映射到 iframe 全局
 * - 把 lucide-react 映射成我们动态生成的 ESM 模块源代码
 */
function createSecurityPlugin(resolveDir, lucideList) {
  return {
    name: "preview-security",
    setup(buildCtx) {
      // onResolve: 任何 import 先走这里
      buildCtx.onResolve({ filter: /.*/ }, (args) => {
        if (EXTERNAL_MODULES.has(args.path)) {
          // 我们用 special namespace "external-globals"
          return {
            path: args.path,
            namespace: "external-globals",
          };
        }

        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在沙箱预览中使用（Node 内置已禁用）。`,
              },
            ],
          };
        }

        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const baseDir = args.resolveDir || resolveDir;
          const resolved = path.resolve(baseDir, args.path);
          if (!resolved.startsWith(baseDir)) {
            return {
              errors: [
                {
                  text: `不允许访问受限目录之外的文件: ${args.path}`,
                },
              ],
            };
          }
          return { path: resolved };
        }

        // 其他任何外部包都不允许
        return {
          errors: [
            {
              text: `模块 "${args.path}" 不在允许的依赖白名单中。只能使用 React、ReactDOM、lucide-react 以及当前文件内声明的组件。`,
            },
          ],
        };
      });

      // onLoad: 根据 namespace 返回模块的实际源码
      buildCtx.onLoad(
        { filter: /.*/, namespace: "external-globals" },
        (args) => {
          // ---- react ----
          if (args.path === "react") {
            return {
              loader: "js",
              contents: `
                // 把 iframe 里的 React 暴露成模块
                export default window.React;
                export const useState = window.React.useState;
                export const useEffect = window.React.useEffect;
                export const useRef = window.React.useRef;
                export const useMemo = window.React.useMemo;
                export const useCallback = window.React.useCallback;
                export const Fragment = window.React.Fragment;
              `,
            };
          }

          // ---- react-dom ----
          if (args.path === "react-dom") {
            return {
              loader: "js",
              contents: `
                export default window.ReactDOM;
              `,
            };
          }

          // ---- react-dom/client ----
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

          // ---- react/jsx-runtime ----
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

          // ---- react/jsx-dev-runtime ----
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

          // ---- lucide-react ----
          if (args.path === "lucide-react") {
            // 动态 ESM 模块源码，包含所有图标的命名导出
            const lucideModuleSource = buildLucideModuleSource(lucideList);
            return {
              loader: "js",
              contents: lucideModuleSource,
            };
          }

          // 理论上不会走到这里
          return {
            errors: [
              {
                text: `未知的 external 模块: ${args.path}`,
              },
            ],
          };
        }
      );
    },
  };
}

/**
 * esbuild 报错转成纯文本
 */
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

/**
 * 把用户传来的源码打包成浏览器可执行 IIFE
 * - virtual-entry 负责 createRoot() 渲染
 * - user-code 就是用户写的那个组件（export default ...）
 */
async function bundleSource(source) {
  const resolveDir = await ensureResolveDir();

  // 抓出用户 import 的所有 lucide-react 图标名
  const lucideList = extractLucideImports(source);

  // 带着这些图标名去构建安全插件
  const securityPlugin = createSecurityPlugin(resolveDir, lucideList);

  const result = await build({
    write: false,
    bundle: true,
    format: "iife",
    target: ["es2018"],
    platform: "browser",
    treeShaking: true,
    logLevel: "silent",
    define: {
      "process.env.NODE_ENV": '"production"',
    },
    plugins: [
      {
        name: "preview-virtual-entry",
        setup(buildCtx) {
          // virtual-entry：负责 mount
          buildCtx.onResolve(
            { filter: new RegExp(`^${VIRTUAL_ENTRY_PATH}$`) },
            () => ({
              path: VIRTUAL_ENTRY_PATH,
              namespace: "virtual",
            })
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
                      {
                        type: "CODE_PLAYGROUND_ERROR",
                        message: detail
                      },
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

          // user-code：用户粘贴的代码本体
          buildCtx.onResolve(
            { filter: new RegExp(`^${USER_CODE_VIRTUAL_PATH}$`) },
            () => ({
              path: USER_CODE_VIRTUAL_PATH,
              namespace: "user",
            })
          );

          buildCtx.onLoad({ filter: /.*/, namespace: "user" }, () => ({
            loader: "tsx",
            resolveDir,
            contents: source,
          }));
        },
      },

      // 我们的安全/依赖注入插件
      securityPlugin,
    ],
    entryPoints: [VIRTUAL_ENTRY_PATH],
  });

  if (!result.outputFiles || result.outputFiles.length === 0) {
    throw new Error("未能生成可执行的预览脚本");
  }

  return result.outputFiles[0].text;
}

/**
 * 用 Tailwind 生成只包含本次源码需要的 class
 * - 我们强制关闭 preflight，避免把 iframe 的输入框/按钮 reset 掉
 */
async function generateTailwindCSS(source) {
  const loadedConfig = await loadTailwindConfigOrFallback();

  let mergedCorePlugins = { preflight: false };
  if (
    loadedConfig.corePlugins &&
    typeof loadedConfig.corePlugins === "object" &&
    !Array.isArray(loadedConfig.corePlugins)
  ) {
    mergedCorePlugins = {
      ...loadedConfig.corePlugins,
      preflight: false,
    };
  }

  const effectiveConfig = {
    ...loadedConfig,
    corePlugins: mergedCorePlugins,
    content: [{ raw: source, extension: "jsx" }],
  };

  const result = await postcss([tailwindcss(effectiveConfig)]).process(
    BASE_CSS,
    { from: undefined }
  );

  return result.css;
}

/**
 * 解析请求体
 */
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

/**
 * 这是 /api/compile-preview 的 handler
 * 入参: { source: string }
 * 出参: { js, css } 或 { error }
 */
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
      (error && typeof error.statusCode === "number" && error.statusCode) ||
      400;

    const message = formatEsbuildError(error);
    res.status(statusCode).json({ error: message });
  }
};

// 告诉 vercel 要把可能的 tailwind 配置文件也打包上
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
