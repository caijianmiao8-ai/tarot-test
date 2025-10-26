// api/compile-preview.js
// ✅ 兼容 RemoteDesktopUI 的最终版
// 关键特性：
// - lucide-react 安全代理（任何图标名都不会变成 undefined）
// - React/ReactDOM 映射到 iframe 全局，避免多版本冲突
// - Tailwind 动态生成 + preflight 关闭
// - 安全沙箱（禁 Node 内置模块、禁跨目录 import）

const { build } = require("esbuild");
const path = require("path");
const { builtinModules } = require("module");
const postcss = require("postcss");
const tailwindcss = require("tailwindcss");
const loadConfig = require("tailwindcss/loadConfig");
const fs = require("fs/promises");
const os = require("os");

// 可能存在的 tailwind 配置文件名
const TAILWIND_CONFIG_FILENAMES = [
  "tailwind.config.js",
  "tailwind.config.cjs",
  "tailwind.config.mjs",
  "tailwind.config.ts",
];

// 有些项目把 tailwind 配置放在 src/ 或 styles/
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

// 给 Vercel 函数打包时要携带的依赖文件
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),
    ...TAILWIND_CONFIG_FILENAMES.map((name) => path.posix.join("..", name)),
    "node_modules/tailwindcss/**/*",
  ])
);

// 浏览器环境里允许 import 的模块白名单
// 这些模块不会真的被打进 bundle，而是被我们映射成 iframe 全局变量或代理
const EXTERNAL_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);

// 禁止 import Node 内置模块
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

// esbuild 用的两个虚拟入口
const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

// 我们用 Tailwind 动态生成 CSS
const BASE_CSS =
  "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

// 这些是轻量缓存，避免重复磁盘访问
let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

/**
 * 创建一个安全的、临时的 resolveDir。
 * esbuild 在解析相对 import 的时候会以它为基准。
 * 我们用它来阻隔“../../../../etc/passwd”之类的访问。
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
 * 生成所有可能的 tailwind.config.* 搜索路径
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
 * 找实际存在的 tailwind.config.* 文件
 */
async function findTailwindConfig() {
  if (cachedTailwindConfigPath) {
    return cachedTailwindConfigPath;
  }

  const candidates = getAllCandidateConfigPaths();

  for (const fullPath of candidates) {
    try {
      await fs.access(fullPath);
      cachedTailwindConfigPath = fullPath;
      console.info(
        `[compile-preview] Tailwind config FOUND at: ${fullPath}`
      );
      return cachedTailwindConfigPath;
    } catch {
      // 没找到就继续
    }
  }

  console.warn(
    `[compile-preview] No Tailwind config found. cwd=${process.cwd()} __dirname=${__dirname}`
  );
  return null;
}

/**
 * 载入 tailwind 配置；如果没有，就用兜底配置
 * 兜底里我们：
 * - darkMode="class"
 * - 保留你在 UI 里会用到的圆角、阴影、字体
 * - 不主动 reset 浏览器默认样式（preflight 我们后面会关）
 */
async function loadTailwindConfigOrFallback() {
  if (cachedTailwindConfig) {
    return cachedTailwindConfig;
  }

  const configPath = await findTailwindConfig();

  if (configPath) {
    try {
      cachedTailwindConfig = loadConfig(configPath);
      return cachedTailwindConfig;
    } catch (error) {
      console.error(
        `[compile-preview] Failed to load Tailwind config: ${
          error?.stack || error
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
 * 这个插件是整个沙箱的心脏：
 * - 限制 import 来源
 * - 把 react / react-dom / lucide-react 映射成安全的运行时实现
 * - 防止 Node 内置模块
 * - 防止逃出 sandbox 目录
 */
function createSecurityPlugin(resolveDir) {
  return {
    name: "preview-security",
    setup(buildCtx) {
      //
      // 1. onResolve: 控制“这个 import 跳到哪去”
      //
      buildCtx.onResolve({ filter: /.*/ }, (args) => {
        // 白名单外部依赖 => 我们稍后用 onLoad 注入虚拟实现
        if (EXTERNAL_MODULES.has(args.path)) {
          return {
            path: args.path,
            namespace: "external-globals",
          };
        }

        // 禁 Node 内置模块
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在沙箱预览中使用（Node 内置已被禁用）。`,
              },
            ],
          };
        }

        // 允许相对/绝对路径，但要限制在 resolveDir 之下
        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const baseDir = args.resolveDir || resolveDir;
          const resolved = path.resolve(baseDir, args.path);

          // 防止 ../../../../ 逃出 sandbox
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

        // 其他任意第三方依赖一律不允许
        return {
          errors: [
            {
              text: `模块 "${args.path}" 不在允许的依赖白名单中。只能使用 React、ReactDOM、lucide-react 以及当前文件内声明的组件。`,
            },
          ],
        };
      });

      //
      // 2. onLoad: 给 external-globals 命名空间的模块提供具体实现
      //
      buildCtx.onLoad({ filter: /.*/, namespace: "external-globals" }, (args) => {
        let contents = "";

        // === react ===
        if (args.path === "react") {
          // 我们直接把 window.React 作为整个模块导出
          contents = `
            module.exports = window.React;
          `;
        }

        // === react-dom ===
        else if (args.path === "react-dom") {
          contents = `
            module.exports = window.ReactDOM;
          `;
        }

        // === react-dom/client ===
        else if (args.path === "react-dom/client") {
          contents = `
            const ReactDOM = window.ReactDOM;
            if (!ReactDOM || !ReactDOM.createRoot) {
              throw new Error('ReactDOM.createRoot not found. Make sure ReactDOM 18+ is loaded in the iframe.');
            }
            module.exports = {
              createRoot: ReactDOM.createRoot.bind(ReactDOM),
            };
          `;
        }

        // === react/jsx-runtime ===
        else if (args.path === "react/jsx-runtime") {
          contents = `
            const React = window.React;
            module.exports = {
              jsx: React.createElement,
              jsxs: React.createElement,
              Fragment: React.Fragment
            };
          `;
        }

        // === react/jsx-dev-runtime ===
        else if (args.path === "react/jsx-dev-runtime") {
          contents = `
            const React = window.React;
            module.exports = {
              jsxDEV: React.createElement,
              Fragment: React.Fragment
            };
          `;
        }

        // === lucide-react ===
        //
        // 这里是最关键的修复：
        // 我们要兼容像这样的大量命名导入：
        //
        //   import {
        //     Monitor, Smartphone, Settings, Power, Wifi, WifiOff, Clock,
        //     ChevronRight, Grid, Keyboard, Gamepad2, Maximize2, Image,
        //     Zap, Moon, Sun, User, Lock, Eye, EyeOff, LogOut, Bell,
        //     HelpCircle, MessageSquare, Info, MoreVertical, Share2,
        //     Edit, Trash2, Copy, CheckCircle, AlertCircle, Mail,
        //     PhoneCall, BookOpen, Gift, Shield, Volume2, Palette,
        //     Globe, ChevronDown, Home, Plus, Search, Filter
        //   } from 'lucide-react';
        //
        // 我们不能保证 CDN 里真的有每一个同名导出，
        // 所以我们用 Proxy：
        //   - 如果真的有，就返回真实图标
        //   - 没有，就返回一个 PlaceholderIcon
        //
        else if (args.path === "lucide-react") {
          contents = `
            const React = window.React;

            // 一个通用的占位图标组件，不会是 undefined
            function PlaceholderIcon(props) {
              const size = (props && props.size) ? props.size : 16;
              const style = {
                display: 'inline-block',
                width: size + 'px',
                height: size + 'px',
                borderRadius: '4px',
                backgroundColor: 'rgba(148,163,184,0.4)', // slate-400/40
                border: '1px solid rgba(148,163,184,0.6)', // slate-400/60
                lineHeight: 0
              };

              // 允许 className 进来避免 React 报 unknown prop
              const outerStyle = style;
              return React.createElement('span', { style: outerStyle });
            }

            function createLucideProxy(real) {
              // real 可能是 undefined，或者是 CDN 暴露的对象
              const target = (real && typeof real === 'object') ? real : {};

              return new Proxy(target, {
                get(obj, prop) {
                  if (prop === '__esModule') return true;
                  if (prop === 'default') {
                    // 保留 default，防止一些奇怪的 "import xyz from 'lucide-react'"
                    return obj;
                  }
                  // 如果 CDN 真的有对应图标，直接返回
                  if (prop in obj && obj[prop]) {
                    return obj[prop];
                  }
                  // 否则返回占位图标，这样 React 不会炸
                  return PlaceholderIcon;
                }
              });
            }

            // 我们尝试从不同全局变量里取 lucide
            // （不同版本的 UMD 可能暴露成 window.lucide 或 window.LucideReact）
            const lucideGlobal = window.lucide || window.LucideReact || {};

            // 包一层 Proxy，缺啥补啥
            const proxied = createLucideProxy(lucideGlobal);

            module.exports = proxied;
            module.exports.default = proxied;
          `;
        }

        // 兜底：如果 somehow 有别的 external 模块（按理不会走到）
        else {
          return {
            errors: [
              {
                text: `未知的 external 模块: ${args.path}`,
              },
            ],
          };
        }

        return {
          contents,
          loader: "js",
        };
      });
    },
  };
}

/**
 * 把 esbuild 的报错整理成人类可读文本，回传给前端 overlay 显示
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
 * 把用户输入的 React 组件源码打包成一段浏览器可执行的 IIFE
 * - 我们构造了两个虚拟模块：
 *   1. "virtual-entry": 负责在 iframe 里 createRoot(...) 并渲染用户组件
 *   2. "user-code":     就是用户自己写的源码（export default ...）
 */
async function bundleSource(source) {
  const resolveDir = await ensureResolveDir();
  const securityPlugin = createSecurityPlugin(resolveDir);

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
          // 入口模块 (virtual-entry)
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
                      ? payload.stack || payload.message
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

          // 用户源码模块 (user-code)
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

      // 我们的安全/映射插件
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
 * 用 Tailwind 生成需要的 CSS：
 * - content: 我们把整段用户源码丢进去
 * - preflight 强制关掉，避免 iframe 全局 reset 掉原生元素
 */
async function generateTailwindCSS(source) {
  const loadedConfig = await loadTailwindConfigOrFallback();

  // 关掉 preflight，避免把 iframe 的 <input> / <button> 样式全清空
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
 * 解析请求体（兼容 req.body 是对象或字符串）
 */
function parseRequestBody(req) {
  if (!req.body) {
    return {};
  }
  if (typeof req.body === "string") {
    try {
      return JSON.parse(req.body);
    } catch (error) {
      throw new Error("请求体不是合法的 JSON");
    }
  }
  return req.body;
}

/**
 * 主入口：POST /api/compile-preview
 * 入参: { source: string }  (用户在左侧编辑器里写的整段 React 代码)
 * 返回: { js, css } 或 { error }
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

// Vercel 配置：确保部署后还能拿到 tailwind 配置文件
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
