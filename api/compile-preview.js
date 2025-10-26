// api/compile-preview.js
//
// 服务器端实时编译器（给预览 iframe 用）。
// 功能：
//   1. 用 esbuild 把用户在编辑器里写的 React 组件打成一个 IIFE。
//   2. 让 React / ReactDOM / lucide-react 这些库通过全局(window.*)注入，而不是真的打包 node_modules。
//   3. 把 Tailwind 按需跑一遍，只生成当前代码用到的类。我们强制关闭 preflight，避免 Vercel 上读取 preflight.css 报 ENOENT。
//   4. 自动生成一个“虚拟 lucide-react 模块”，解决：
//        - React element type is invalid (组件是 undefined 的问题)
//        - 图标必须能真的渲染，而不是黑框
//   5. 强沙箱：禁止 Node 内置、禁止任意 import 其他包、防止路径逃逸。
//
// 这份代码是完整形态，不要再砍它。

const { build } = require("esbuild");
const path = require("path");
const { builtinModules } = require("module");
const postcss = require("postcss");
const tailwindcss = require("tailwindcss");
const loadConfig = require("tailwindcss/loadConfig");
const fs = require("fs/promises");
const os = require("os");

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

// 我们告诉 Vercel 把 tailwindcss 本体打进来，以便 serverless 环境能 require。
// includeFiles 还能把你的 tailwind.config.js 之类的东西带过来（即使在子目录）
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    ...TAILWIND_CONFIG_FILENAMES.map((n) => n),
    ...TAILWIND_CONFIG_FILENAMES.map((n) => path.posix.join("..", n)),
    "node_modules/tailwindcss/**/*",
  ])
);

// ----------------------------------------------------------------------------
// 外部依赖白名单
// ----------------------------------------------------------------------------

const EXTERNAL_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);

// 禁 Node 内置模块 / 进程对象
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((n) => `node:${n}`),
  "process",
]);

// 虚拟入口常量
const USER_CODE_VIRTUAL_PATH = "user-code";    // 你的组件源码
const VIRTUAL_ENTRY_PATH = "virtual-entry";    // 我们注入的root/mount脚本

// Tailwind 指令
const BASE_CSS = "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

// 缓存
let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

// ----------------------------------------------------------------------------
// 帮助函数：安全的 resolveDir（esbuild 需要一个根目录，不能乱跳）
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
// Tailwind 配置文件查找
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

  // 没找到你的 tailwind.config，就兜底一个非常接近你 UI 的基础主题
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
          // 玻璃态那种大面积柔光阴影
          "glass-xl": "0 40px 120px rgba(15,23,42,0.45)",
        },
      },
    },
    plugins: [],
  };

  return cachedTailwindConfig;
}

// ----------------------------------------------------------------------------
// 图标处理
// ----------------------------------------------------------------------------
//
// 情况：
//   import { Monitor, Gamepad2 } from 'lucide-react';
//
// 在打包阶段我们要合成一个模块 "lucide-react"：
//   export const Monitor = getIcon("Monitor");
//   export const Gamepad2 = getIcon("Gamepad2");
//   ...
//
// getIcon 做 3 层兜底：
//   1. window.lucideReact / window.LucideReact ...: 已经是 React 组件，直接返回
//   2. window.lucide (lucide 核心 UMD): 提供 .icons['monitor'], .icons['gamepad-2']...
//      我们把这些 svg 节点数组包装成 React 组件，再返回
//   3. 实在没有 -> 返回一个轻微的占位 SVG（浅色圆+横线），不会是粗黑框
//
// 关键：lucide 核心是 kebab-case 和带数字中横线，比如 "gamepad-2"
//       lucide-react 是 PascalCase，比如 "Gamepad2"
// 我们在这里做 PascalCase -> kebab-case/小驼峰 的映射，保证 Gamepad2 能找到 gamepad-2
//

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

    // 这个占位图标比“黑色方块”柔和太多：一个轻微透明圆+一条线
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

    // PascalCase("Gamepad2") -> 多种候选key：["gamepad-2","gamepad2","gamepad-2",...]
    function guessCoreKeys(pascalName) {
      const kebab = pascalName
        // fooBar -> foo-bar
        .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
        // FOOBar -> FOO-Bar
        .replace(/([A-Z])([A-Z][a-z])/g, '$1-$2')
        // Thing2 -> Thing-2
        .replace(/([a-zA-Z])([0-9]+)/g, '$1-$2')
        .toLowerCase();

      const simpleLower =
        pascalName.charAt(0).toLowerCase() + pascalName.slice(1);

      return Array.from(
        new Set([
          kebab,                // "gamepad-2"
          simpleLower,          // "gamepad2"
          pascalName,           // "Gamepad2"
          pascalName.toLowerCase(), // "gamepad2" (again)
        ])
      );
    }

    // 把 lucide 原始节点数组转成 React 组件
    // nodes 形如 [ ["path", { d: "..." }], ["line",{...}], ... ]
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

    // 尝试从 core-style 数据里拿节点数组
    function getIconNodesFromCore(core, pascalName) {
      if (!core) return null;

      // lucide UMD 通常是 window.lucide，其中 window.lucide.icons 是一个对象:
      //   { "monitor": [ ["rect",{...}], ["path",{...}] ], "gamepad-2":[...] }
      // 我们要考虑 PascalCase -> kebab-case 映射
      const candidates = guessCoreKeys(pascalName); // ["gamepad-2", "gamepad2", ...]

      for (const key of candidates) {
        // 尝试 core.icons["gamepad-2"]
        if (core.icons && Array.isArray(core.icons[key])) {
          return core.icons[key];
        }

        // 尝试 core[key] = ["svg", attrs, nodes] 这种旧风格
        const direct = core[key];
        if (Array.isArray(direct)) {
          const maybeNodes = Array.isArray(direct[2]) ? direct[2] : null;
          if (maybeNodes) return maybeNodes;
        }

        // 尝试 core[key] = { iconNode:[...]} / { node:[...]}
        if (direct && typeof direct === "object") {
          if (Array.isArray(direct.iconNode)) return direct.iconNode;
          if (Array.isArray(direct.node)) return direct.node;
        }
      }

      return null;
    }

    // 尝试发现全局的图标库
    // - componentCandidates：已经是 React 组件（理想情况）
    // - coreCandidates：核心节点（我们包一层变成 React 组件）
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

      // 某些构建可能把 React 组件直接塞到 window.lucide
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
          return Comp; // 直接是 React 组件，就太棒了
        }
      }

      if (type === "core") {
        const nodes = getIconNodesFromCore(lib, pascalName);
        if (nodes) {
          return createReactIconFromNodes(pascalName, nodes);
        }
      }

      if (type === "unknown") {
        // unknown: 有时 window.lucide 直接是 { Monitor: fn }
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

      // 实在没找到 -> 返回占位，不再是丑陋黑块
      return function MissingIcon(props) {
        return React.createElement(PlaceholderIcon, props);
      };
    }

    ${exportLines.join("\n")}

    // 有些人会 default import lucide-react（虽然不推荐）
    export default (getGlobalIconSource().lib || {});
  `;
}

// ----------------------------------------------------------------------------
// esbuild 安全插件：白名单依赖注入 + 禁 Node 内置 + 禁止路径逃逸
// ----------------------------------------------------------------------------
function createSecurityPlugin(resolveDir, lucideList) {
  return {
    name: "preview-security",
    setup(buildCtx) {
      // onResolve：决定 import 怎么处理
      buildCtx.onResolve({ filter: /.*/ }, (args) => {
        // 白名单模块转到我们的 external-globals namespace
        if (EXTERNAL_MODULES.has(args.path)) {
          return {
            path: args.path,
            namespace: "external-globals",
          };
        }

        // Node 内置模块一律禁止
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在沙箱中使用（Node 内置已禁用）。`,
              },
            ],
          };
        }

        // 相对/绝对路径：必须落在 resolveDir 里，防止逃逸到真实文件系统
        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const base = args.resolveDir || resolveDir;
          const resolved = path.resolve(base, args.path);
          if (!resolved.startsWith(base)) {
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

        // 其他第三方 import，全都禁止
        return {
          errors: [
            {
              text: `模块 "${args.path}" 不在允许白名单中。只能使用 React、ReactDOM、lucide-react 以及当前文件内的代码。`,
            },
          ],
        };
      });

      // onLoad：给这些 external-globals 模块真正的实现（都是用 window.*）
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
            return {
              loader: "js",
              contents: lucideModuleSource,
            };
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

// ----------------------------------------------------------------------------
// esbuild 错误格式化，方便返回给前端 overlay
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
//
// 打包的结构：
//   - virtual-entry: 我们生成的挂载脚本，它在 iframe 里执行，createRoot(#root).render(<UserComponent />)
//   - user-code:     你的源码（必须 default export 一个 React 组件）
// ----------------------------------------------------------------------------
async function bundleSource(source) {
  const resolveDir = await ensureResolveDir();

  // 从用户代码里抓到所有 lucide-react import 的名字
  const lucideList = extractLucideImports(source);

  // 安全插件（白名单 + lucide-react 动态模块）
  const securityPlugin = createSecurityPlugin(resolveDir, lucideList);

  const result = await build({
    write: false,
    bundle: true,
    format: "iife", // 立即执行函数，丢进 <script> 就能跑
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
          // virtual-entry: 负责在 iframe 里挂载
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

              // 往父窗口抛错，展示到右上角 overlay
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

              // 捕获 runtime error / unhandledrejection
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

          // user-code: 你的编辑器里的源码
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

      // 把 React / ReactDOM / lucide-react 变成 window.* 的别名，禁止额外依赖
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
// Tailwind CSS 生成
//
// 问题：Tailwind 的 preflight 默认会去读取它自己的 preflight.css。
// 在 Vercel Serverless 上，有时候那个文件路径解析不到 -> ENOENT。
//
// 我们这里强制 corePlugins.preflight=false 来跳过那个文件。
// 但关闭 preflight 会造成：
//   - box-shadow 自带的 CSS 变量没初始化 -> 只能看到“黑线边框”而不是柔软阴影
//   - reset(边框, box-sizing...)也没注入
//
// 这个问题我们不是在 server 侧解决，而是在 iframe (main.js 里) 手动注入一段 baseline CSS，
// 里面会还原 Tailwind 那些关键变量 (--tw-shadow 等)，加上 box-sizing、font、overflow 等，
// 让阴影正常、滚动正常、字体正常。
// ----------------------------------------------------------------------------
async function generateTailwindCSS(source) {
  const cfg = await loadTailwindConfigOrFallback();

  // 强制关 preflight，避免 ENOENT
  let corePlugins = { preflight: false };
  if (
    cfg.corePlugins &&
    typeof cfg.corePlugins === "object" &&
    !Array.isArray(cfg.corePlugins)
  ) {
    corePlugins = { ...cfg.corePlugins, preflight: false };
  }

  // 把用户当前源码作为 content，这样 Tailwind 只会生成用得到的类
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
      (error && typeof error.statusCode === "number" && error.statusCode) ||
      400;

    const message = formatEsbuildError(error);
    res.status(statusCode).json({ error: message });
  }
};

// 告诉 Vercel：这个无服务器函数要把哪些文件一起打包进来
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
