// api/compile-preview.js
//
// ✅ 最终修正版（带 ENOENT 修复）
//
// 关键点：
// - lucide-react：为每个导入的图标生成静态命名导出，避免 undefined 组件 -> 不再触发 React invalid element error
// - lucide-react：占位图标是优雅的 SVG，不是黑块
// - Tailwind：在 serverless 环境下我们强制 corePlugins.preflight=false，这样不会去读 node_modules/tailwindcss/lib/css/preflight.css
//   => 修复 ENOENT
// - iframe 侧（main.js 里）我们注入 sandbox-baseline，把 body margin:0 / box-sizing:border-box / 全屏高度 / 字体 / 控件重置 补回来
//   => UI 仍然接近设计稿，而不会乱飞、不会原生按钮丑
//
// - 仍然是安全沙箱：禁止 fs 等 Node 内置模块，禁止任意第三方 import，React/ReactDOM 从 iframe 全局拿

const { build } = require("esbuild");
const path = require("path");
const { builtinModules } = require("module");
const postcss = require("postcss");
const tailwindcss = require("tailwindcss");
const loadConfig = require("tailwindcss/loadConfig");
const fs = require("fs/promises");
const os = require("os");

// ----------------- Tailwind config 搜索 -----------------

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

// vercel 函数部署时告诉它需要一并打包的文件
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),
    ...TAILWIND_CONFIG_FILENAMES.map((name) => path.posix.join("..", name)),
    "node_modules/tailwindcss/**/*",
  ])
);

// ----------------- 允许的外部模块 -----------------

const EXTERNAL_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);

// 禁用 Node 内置
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

// esbuild 虚拟入口
const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

// Tailwind 的基础指令
const BASE_CSS =
  "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

// ----------------- helper: 沙箱根目录 -----------------

async function ensureResolveDir() {
  if (!cachedResolveDirPromise) {
    cachedResolveDirPromise = fs
      .mkdtemp(path.join(os.tmpdir(), "preview-entry-"))
      .catch(() => os.tmpdir());
  }
  return cachedResolveDirPromise;
}

// ----------------- helper: 找 tailwind.config.* -----------------

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
      console.info(
        `[compile-preview] Tailwind config FOUND at: ${full}`
      );
      return cachedTailwindConfigPath;
    } catch {
      // keep looking
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

// ----------------- lucide-react 处理 -----------------
//
// 我们扫描用户源码：import { Monitor, Wifi, Shield as MyShield } from 'lucide-react'
// 然后为每个名字生成：export const Monitor = getIcon("Monitor");
//
// 通过这种“静态命名导出”，esbuild 就不会把这些变成对一个对象的解构，
// React 不会再拿到 undefined 组件。
// 缺的图标我们用优雅占位 SVG（不再是黑块）。
//

function extractLucideImports(userSource) {
  const results = [];
  const importRegex =
    /import\s*\{\s*([^}]+)\}\s*from\s*['"]lucide-react['"]/g;

  let match;
  while ((match = importRegex.exec(userSource)) !== null) {
    const inner = match[1]; // "Monitor, Wifi, Shield as ShieldIcon"
    inner.split(",").forEach((rawPart) => {
      const part = rawPart.trim();
      if (!part) return;
      const m = part.split(/\s+as\s+/i);
      const remoteName = m[0].trim();
      const localName = m[1] ? m[1].trim() : remoteName;
      if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(localName)) {
        results.push({ localName, remoteName });
      }
    });
  }

  const dedup = new Map();
  for (const item of results) {
    if (!dedup.has(item.localName)) {
      dedup.set(item.localName, item);
    }
  }
  return Array.from(dedup.values());
}

function buildLucideModuleSource(lucideList) {
  const exportLines = lucideList.map(({ localName, remoteName }) => {
    return `export const ${localName} = getIcon("${remoteName}");`;
  });

  return `
    const React = window.React;

    // 优雅占位：半透明圆圈 + 一条横线，继承 currentColor
    function PlaceholderIcon(props) {
      const size = (props && props.size) ? props.size : 16;
      const className = props && props.className ? props.className : "";

      return React.createElement(
        "svg",
        {
          width: size,
          height: size,
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: "currentColor",
          strokeWidth: 2,
          strokeLinecap: "round",
          strokeLinejoin: "round",
          className: className
        },
        React.createElement("circle", {
          cx: 12,
          cy: 12,
          r: 10,
          style: { opacity: 0.2 }
        }),
        React.createElement("line", {
          x1: 8,
          y1: 12,
          x2: 16,
          y2: 12
        })
      );
    }

    function getGlobalIconMap() {
      const candidates = [
        window.lucide,
        window.LucideReact,
        window.lucideReact,
        window.lucide_icons,
        window.lucideIcons,
        window.LucideIcons
      ];
      for (let i = 0; i < candidates.length; i++) {
        const lib = candidates[i];
        if (lib && typeof lib === "object") {
          if (Object.keys(lib).length > 0) {
            return lib;
          }
        }
      }
      return {};
    }

    function getIcon(name) {
      const lib = getGlobalIconMap();
      const Comp = lib && lib[name];

      if (Comp) {
        return Comp; // 真图标组件
      }

      // 缺了这个图标 => 返回一个函数组件包装占位符
      return function MissingIcon(props) {
        return React.createElement(PlaceholderIcon, props);
      };
    }

    ${exportLines.join("\n")}

    // 保留 default，防止有人写 import X from 'lucide-react'
    const __lucideDefault = getGlobalIconMap();
    export default __lucideDefault;
  `;
}

// ----------------- 安全插件：拦截 import -----------------

function createSecurityPlugin(resolveDir, lucideList) {
  return {
    name: "preview-security",
    setup(buildCtx) {
      // onResolve: 决定 import 指向
      buildCtx.onResolve({ filter: /.*/ }, (args) => {
        if (EXTERNAL_MODULES.has(args.path)) {
          return { path: args.path, namespace: "external-globals" };
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

        return {
          errors: [
            {
              text: `模块 "${args.path}" 不在允许的依赖白名单中。只能使用 React、ReactDOM、lucide-react 以及当前文件内声明的组件。`,
            },
          ],
        };
      });

      // onLoad: 真正返回这些外部模块的实现源码
      buildCtx.onLoad(
        { filter: /.*/, namespace: "external-globals" },
        (args) => {
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

// ----------------- esbuild 错误变成文本 -----------------

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

// ----------------- 打包用户代码成 IIFE -----------------

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
    define: {
      "process.env.NODE_ENV": '"production"',
    },
    plugins: [
      {
        name: "preview-virtual-entry",
        setup(buildCtx) {
          // virtual-entry：负责在 iframe 里 createRoot() + render(<UserComponent />)
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

          // user-code：用户实际写的组件
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
      securityPlugin,
    ],
    entryPoints: [VIRTUAL_ENTRY_PATH],
  });

  if (!result.outputFiles || result.outputFiles.length === 0) {
    throw new Error("未能生成可执行的预览脚本");
  }

  return result.outputFiles[0].text;
}

// ----------------- 生成 Tailwind CSS -----------------
//
// 这里是关键修复：
// 我们不能让 Tailwind 去注入 preflight（那会在 serverless 里尝试读取 preflight.css -> ENOENT）。
// 但是我们已经在 iframe (main.js) 里手动注入 sandbox-baseline 样式，
// 帮我们做到 body{margin:0}, box-sizing:border-box, html/body/#root 100% 高度, 字体继承等。
// 所以这里可以安全地把 preflight 关掉。
//
// 做法：复制用户 config，然后强行 corePlugins.preflight=false。

async function generateTailwindCSS(source) {
  const loadedConfig = await loadTailwindConfigOrFallback();

  // 我们要构造一个 effectiveConfig：
  // - 继承用户的 tailwind 配置（颜色、圆角、阴影、darkMode 等）
  // - 强行覆盖 corePlugins.preflight=false，避免读取 preflight.css
  // - 指定 content 为用户源码
  let mergedCorePlugins = { preflight: false };

  // 如果用户自己的 config 里有 corePlugins 是对象，就合并（除了我们要强制 preflight:false）
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

// ----------------- 请求解析 & handler -----------------

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
      (error && typeof error.statusCode === "number" && error.statusCode) ||
      400;

    const message = formatEsbuildError(error);
    res.status(statusCode).json({ error: message });
  }
};

// vercel: 把 tailwindcss 打包进去（尽量提高找到其依赖的概率，虽然我们禁止 preflight 了）
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
