// api/compile-preview.js
//
// ✅ 最终版：
// - 图标不再报错、不再是黑框，占位是一个轻柔的 SVG
// - 自动生成 lucide-react 的命名导出，彻底解决 undefined 组件导致的 React 报错
// - Tailwind 使用正常 preflight，布局/间距/圆角/字体恢复到设计稿那种“App级UI”
// - iframe 环境仍是安全沙箱（不允许 fs 等 Node 内置模块）
//
// 这个文件跑在 Vercel 的 serverless 侧，用 esbuild 把用户左侧编辑器的 React 源码
// 打包成一段可以直接塞进 iframe 里的 <script> 代码 + 一段按需生成的 Tailwind CSS。

const { build } = require("esbuild");
const path = require("path");
const { builtinModules } = require("module");
const postcss = require("postcss");
const tailwindcss = require("tailwindcss");
const loadConfig = require("tailwindcss/loadConfig");
const fs = require("fs/promises");
const os = require("os");

// --- tailwind config 搜索相关 -------------------------------------------------

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

// vercel 函数部署时，一起打包哪些文件（让线上也能读到 tailwind 配置）
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),
    ...TAILWIND_CONFIG_FILENAMES.map((name) => path.posix.join("..", name)),
    "node_modules/tailwindcss/**/*",
  ])
);

// --- 沙箱允许的外部模块（会被我们用特殊方式注入，而不是直接打包 node_modules） ---
const EXTERNAL_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);

// 禁止导入 Node 内置模块
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

// esbuild 里的两个虚拟模块名
const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

// Tailwind 的基础指令
const BASE_CSS =
  "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

// 缓存
let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

// -----------------------------------------------------------------------------
// helpers: 路径 & tailwind config 发现
// -----------------------------------------------------------------------------

async function ensureResolveDir() {
  // 给 esbuild 一个安全的“根目录”，禁止 ../.. 爬出去
  if (!cachedResolveDirPromise) {
    cachedResolveDirPromise = fs
      .mkdtemp(path.join(os.tmpdir(), "preview-entry-"))
      .catch(() => os.tmpdir());
  }
  return cachedResolveDirPromise;
}

function getAllCandidateConfigPaths() {
  // 我们尝试在这些 baseDir 下找 tailwind.config.*
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

  // fallback：我们手动扩展一下常用圆角/投影/字体
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

// -----------------------------------------------------------------------------
// lucide-react 处理：
// 我们会在打包前扫描用户源码里 import { IconName } from 'lucide-react'
// 然后动态生成一个“虚拟 lucide-react 模块”，里面显式写：
//   export const IconName = getIcon("IconName");
// 这样 esbuild 知道每个命名导出都存在，React 不会遇到 undefined。
// -----------------------------------------------------------------------------

function extractLucideImports(userSource) {
  // 支持：
  //   import { Monitor, Wifi } from 'lucide-react'
  //   import { Shield as ShieldIcon } from 'lucide-react'
  //
  // 返回：[{ localName: "Monitor", remoteName: "Monitor" }, ...]
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
      // 只接收合法变量名，避免奇怪语法污染
      if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(localName)) {
        results.push({ localName, remoteName });
      }
    });
  }

  // 去重同名 localName
  const dedupMap = new Map();
  for (const item of results) {
    if (!dedupMap.has(item.localName)) {
      dedupMap.set(item.localName, item);
    }
  }
  return Array.from(dedupMap.values());
}

function buildLucideModuleSource(lucideList) {
  // 给每个导入到的图标都声明一个静态导出：
  // export const Monitor = getIcon("Monitor");
  // export const ShieldIcon = getIcon("Shield");
  const exportLines = lucideList.map(({ localName, remoteName }) => {
    return `export const ${localName} = getIcon("${remoteName}");`;
  });

  return `
    const React = window.React;

    // 优雅的占位符：一个通用的 SVG 圆圈+横线，继承 currentColor，
    // 没有黑色方块、没有粗边框，看起来更像“图标缺失占位”而不是 UI bug。
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

    // 从 iframe 全局里尝试拿真实的 lucide-react UMD 导出的图标组件。
    // 不同版本/打包方式可能挂在不同的名字上，我们尽量多试几个。
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
          // 我们只需要第一个长得像“图标字典”的对象
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
        // 找到了真实图标组件 => 原样返回
        return Comp;
      }

      // 没找到 => 返回一个稳定的函数组件，内部渲染 PlaceholderIcon。
      // 注意：返回的是 function，而不是直接返回 <PlaceholderIcon/>，
      // 这样 React 仍然认为它是一个合法的组件类型。
      return function MissingIcon(props) {
        return React.createElement(PlaceholderIcon, props);
      };
    }

    ${exportLines.join("\n")}

    // default 导出给一些奇葩写法兜底（基本用不到）
    const __lucideDefault = getGlobalIconMap();
    export default __lucideDefault;
  `;
}

// -----------------------------------------------------------------------------
// 安全插件：
// - 禁 Node 内置模块
// - 禁止随便 import 其他包
// - 注入 react/react-dom/.../lucide-react 的浏览器端实现
// -----------------------------------------------------------------------------

function createSecurityPlugin(resolveDir, lucideList) {
  return {
    name: "preview-security",
    setup(buildCtx) {
      // 1) onResolve: 控制 import 指向哪里
      buildCtx.onResolve({ filter: /.*/ }, (args) => {
        // 白名单里的模块 => 我们用 namespace external-globals 去特殊处理
        if (EXTERNAL_MODULES.has(args.path)) {
          return {
            path: args.path,
            namespace: "external-globals",
          };
        }

        // 禁掉 Node 内置模块
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在沙箱预览中使用（Node 内置已禁用）。`,
              },
            ],
          };
        }

        // 允许相对路径 / 绝对路径，但必须留在 resolveDir 里，禁止爬出去
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

        // 其他第三方依赖一律拒绝
        return {
          errors: [
            {
              text: `模块 "${args.path}" 不在允许的依赖白名单中。只能使用 React、ReactDOM、lucide-react 以及当前文件内声明的组件。`,
            },
          ],
        };
      });

      // 2) onLoad: 针对 external-globals namespace 注入真正的模块源码
      buildCtx.onLoad(
        { filter: /.*/, namespace: "external-globals" },
        (args) => {
          // react
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

          // react-dom
          if (args.path === "react-dom") {
            return {
              loader: "js",
              contents: `
                const ReactDOM = window.ReactDOM;
                export default ReactDOM;
              `,
            };
          }

          // react-dom/client
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

          // react/jsx-runtime
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

          // react/jsx-dev-runtime
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

          // lucide-react 关键逻辑：动态 ESM，给每个导入的图标都一个静态导出
          if (args.path === "lucide-react") {
            const lucideModuleSource = buildLucideModuleSource(lucideList);
            return {
              loader: "js",
              contents: lucideModuleSource,
            };
          }

          // theoretically shouldn't get here
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

// -----------------------------------------------------------------------------
// esbuild 错误 -> 文本
// -----------------------------------------------------------------------------

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

// -----------------------------------------------------------------------------
// 把用户粘贴的源码打包成浏览器可执行 IIFE
// virtual-entry: 负责 createRoot + 渲染用户组件
// user-code:     就是用户写的那个文件（必须 default export）
// -----------------------------------------------------------------------------

async function bundleSource(source) {
  const resolveDir = await ensureResolveDir();

  // 找出用户 import 了哪些 lucide-react 图标
  const lucideList = extractLucideImports(source);

  // 构建安全插件（包含我们的 lucide-react 虚拟模块）
  const securityPlugin = createSecurityPlugin(resolveDir, lucideList);

  const result = await build({
    write: false,
    bundle: true,
    format: "iife", // 直接是一个立即执行函数，丢进 <script> 就可以跑
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
          // virtual-entry 模块：负责 mount
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

          // user-code 模块：就是用户粘贴的那段 React 代码本体
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

      // 安全/依赖注入插件
      securityPlugin,
    ],
    entryPoints: [VIRTUAL_ENTRY_PATH],
  });

  if (!result.outputFiles || result.outputFiles.length === 0) {
    throw new Error("未能生成可执行的预览脚本");
  }

  return result.outputFiles[0].text;
}

// -----------------------------------------------------------------------------
// Tailwind: 从用户源码提取 class，生成 CSS
// 这次我们让 Tailwind 的 preflight 正常启用（不强行关掉）
// 这样 body margin:0 / box-sizing 等基础重置跟真实项目一致，布局回归正常
// -----------------------------------------------------------------------------

async function generateTailwindCSS(source) {
  const loadedConfig = await loadTailwindConfigOrFallback();

  // 不再手动强制 preflight:false
  // 给 tailwind 一个正确的 config + 我们的源码作为 content
  const effectiveConfig = {
    ...loadedConfig,
    content: [{ raw: source, extension: "jsx" }],
  };

  const result = await postcss([tailwindcss(effectiveConfig)]).process(
    BASE_CSS,
    { from: undefined }
  );

  return result.css;
}

// -----------------------------------------------------------------------------
// 请求体验证 & 响应
// -----------------------------------------------------------------------------

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

// vercel: 把 tailwind 相关文件一并打包
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
