// api/compile-preview.js

const { build } = require("esbuild");
const path = require("path");
const { builtinModules } = require("module");
const postcss = require("postcss");
const tailwindcss = require("tailwindcss");
const loadConfig = require("tailwindcss/loadConfig");
const fs = require("fs/promises");
const os = require("os");

/**
 * Tailwind 配置文件的常见命名
 */
const TAILWIND_CONFIG_FILENAMES = [
  "tailwind.config.js",
  "tailwind.config.cjs",
  "tailwind.config.mjs",
  "tailwind.config.ts",
];

/**
 * 还有一些人会把配置放到 styles/ 或 src/ 下面
 */
const EXTRA_CONFIG_LOCATIONS = [
  "styles/tailwind.config.js",
  "styles/tailwind.config.cjs",
  "styles/tailwind.config.mjs",
  "styles/tailwind.config.ts",
  "src/tailwind.config.js",
  "src/tailwind.config.cjs",
  "src/tailwind.config.mjs",
  "src/tailwind.config.ts",
  "src/styles/tailwind.config.js",
  "src/styles/tailwind.config.cjs",
  "src/styles/tailwind.config.mjs",
  "src/styles/tailwind.config.ts",
];

/**
 * 我们需要把某些文件强制打包进 Vercel 的 serverless 函数运行环境。
 *
 * 场景：
 *  - Vercel 会把函数和依赖打成一个 /var/task 包
 *  - 但不会自动把 tailwindcss 的内部资源文件 (比如 lib/css/preflight.css) 全带上
 *  - 如果缺了就会报 ENOENT: preflight.css not found
 *
 * includeFiles 允许我们手动指定“把这些额外文件/目录也一起打进函数包里”。
 *
 * 我们要带：
 *  1. 项目根目录下的 tailwind.config.js（以及它的各种可能命名）
 *  2. 上一级的 tailwind.config.js（如果函数的 cwd 变成 /var/task/api）
 *  3. 整个 node_modules/tailwindcss/**/* 目录，这样 preflight.css 之类的内置资源不会丢
 */
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    // tailwind.config.* at cwd
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),
    // tailwind.config.* at parent of cwd (to handle /var/task/api runtime)
    ...TAILWIND_CONFIG_FILENAMES.map((name) =>
      path.posix.join("..", name)
    ),
    // and ship Tailwind's own package assets
    "node_modules/tailwindcss/**/*",
  ])
);

/**
 * 允许 import 的包白名单（防止用户代码随便 require 任何东西）
 */
const ALLOWED_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);

/**
 * Node 内置模块 - 在预览环境里禁用
 */
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

/**
 * 我们用虚拟模块名来表示用户的代码输入，和我们自动生成的入口
 */
const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

/**
 * 基础 CSS 指令。Tailwind 会把 @tailwind base/components/utilities 展开成完整样式
 */
const BASE_CSS =
  "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

/**
 * 缓存，避免每次请求都重新生成
 */
let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

/**
 * esbuild 需要一个“安全的根目录”来解析相对路径 import
 * 我们用 tmp 目录，防止用户 import ../../../../etc/passwd 这种东西
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
 * Vercel 的 serverless 函数运行时，可能有两种常见形态：
 *   cwd         = /var/task
 *   __dirname   = /var/task/api
 *
 * 或者反过来。
 *
 * 你的 tailwind.config.js 大概率在仓库根（/var/task）。
 * 我们需要往多个“可能的基准目录”里去找。
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

  const names = [
    ...TAILWIND_CONFIG_FILENAMES,
    ...EXTRA_CONFIG_LOCATIONS,
  ];

  const results = [];
  for (const base of baseDirs) {
    for (const name of names) {
      results.push(path.join(base, name));
    }
  }

  return results;
}

/**
 * 实际上尝试访问 tailwind.config.*，找到第一个存在的
 */
async function findTailwindConfig() {
  if (cachedTailwindConfigPath) {
    return cachedTailwindConfigPath;
  }

  const candidates = getAllCandidateConfigPaths();
  for (const fullPath of candidates) {
    try {
      console.info(
        `[compile-preview] checking Tailwind config at: ${fullPath}`
      );
      await fs.access(fullPath);
      cachedTailwindConfigPath = fullPath;
      console.info(
        `[compile-preview] Tailwind config FOUND at: ${fullPath}`
      );
      return cachedTailwindConfigPath;
    } catch {
      // ignore this one
    }
  }

  console.warn(
    `[compile-preview] No Tailwind config found.
cwd=${process.cwd()}
__dirname=${__dirname}`
  );
  return null;
}

/**
 * 加载 tailwind 配置：
 * - 如果找到真实的 tailwind.config.js（或 .cjs/.mjs/.ts），就用它
 * - 如果找不到，就使用 fallbackConfig（内置你要的那套高质感主题：Inter 字体、圆角玻璃面板、阴影）
 *
 * 重点：我们不再因为没找到 config 就直接抛 500。
 * 这样即使在某些部署形态下 Vercel 没正确把配置文件塞进函数包，
 * 右侧画布依然能渲染高质量 UI，而不是报错和空白。
 */
async function loadTailwindConfigOrFallback() {
  if (cachedTailwindConfig) {
    return cachedTailwindConfig;
  }

  const configPath = await findTailwindConfig();
  if (configPath) {
    try {
      console.info(
        `[compile-preview] loading Tailwind config from: ${configPath}`
      );
      cachedTailwindConfig = loadConfig(configPath);
      return cachedTailwindConfig;
    } catch (error) {
      console.error(
        `[compile-preview] Failed to load Tailwind config ${configPath}: ${
          error?.stack || error
        }`
      );
      // fall through to fallback
    }
  }

  console.warn(
    "[compile-preview] Using internal fallback Tailwind config (preview will still render)"
  );

  // fallback: 内置一份“够漂亮”的 tailwind 主题扩展，保证 UI 不会退化成土砖块
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
            '"Segoe UI"',
            "Roboto",
            '"Helvetica Neue"',
            "Arial",
            '"Noto Sans"',
            "sans-serif",
          ],
          mono: [
            "JetBrains Mono",
            "ui-monospace",
            "SFMono-Regular",
            "Menlo",
            "Consolas",
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
 * esbuild 安全插件：
 * - 禁止用户代码 import Node 内置模块（fs/process等）
 * - 禁止 import 不在白名单里的第三方包
 * - 禁止用相对路径逃出我们的安全 tmp 目录
 */
function createSecurityPlugin(resolveDir) {
  return {
    name: "preview-security",
    setup(build) {
      build.onResolve({ filter: /.*/ }, (args) => {
        // 虚拟用户模块
        if (args.namespace === "user") {
          return { path: args.path, namespace: "user" };
        }

        // ban Node 内置
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在预览中使用。`,
              },
            ],
          };
        }

        // 相对路径 / 绝对路径 import
        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const baseDir = args.resolveDir || resolveDir;
          const resolved = path.resolve(baseDir, args.path);

          // 防止逃逸 tmp 根目录
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

        // 允许白名单依赖
        if (
          ALLOWED_MODULES.has(args.path) ||
          (args.importer && args.importer.includes("node_modules"))
        ) {
          return { path: args.path };
        }

        return {
          errors: [
            {
              text: `模块 "${args.path}" 不在允许的依赖白名单中。`,
            },
          ],
        };
      });
    },
  };
}

/**
 * 把 esbuild 的报错清洗成人类读得懂的多行文本
 * （这样右上角红色 overlay 可以直接显示）
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
 * 把用户源代码打成可执行预览脚本：
 * - 我们构造一个 virtual-entry，它做的事是：
 *   - import 用户组件
 *   - createRoot(#root).render(<用户组件 />)
 *   - 捕捉运行时错误并 postMessage 给父窗口
 * - esbuild 输出 IIFE（立即执行函数），浏览器 iframe 直接跑
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
        setup(build) {
          // 入口模块 virtual-entry
          build.onResolve(
            { filter: new RegExp(`^${VIRTUAL_ENTRY_PATH}$`) },
            () => ({
              path: VIRTUAL_ENTRY_PATH,
              namespace: "virtual",
            })
          );

          build.onLoad({ filter: /.*/, namespace: "virtual" }, () => ({
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

// 捕捉运行时报错 / 未处理 Promise 拒绝
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

          // 用户代码模块 user-code
          build.onResolve(
            { filter: new RegExp(`^${USER_CODE_VIRTUAL_PATH}$`) },
            () => ({
              path: USER_CODE_VIRTUAL_PATH,
              namespace: "user",
            })
          );

          build.onLoad({ filter: /.*/, namespace: "user" }, () => ({
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

/**
 * 把 Tailwind 作为 PostCSS 插件跑一遍，生成按需 CSS：
 * - content 是用户当前编辑的 React 源码
 * - 这样返回的 CSS 就只包含你真的用到的类（玻璃态、圆角、渐变、flex/grid等）
 * - 用不到的不会塞进来 → 右侧 iframe 更轻
 *
 * 注意：现在我们用 loadTailwindConfigOrFallback()
 * 即使真实 config 没被打包进去，也会 fallback，
 * 不再直接 500。
 */
async function generateTailwindCSS(source) {
  const loadedConfig = await loadTailwindConfigOrFallback();

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

/**
 * 从 req.body 取出 { source }，兼容字符串/JSON
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
 * /api/compile-preview 入口
 * 返回 { js, css } 或 { error }
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
      (error &&
        typeof error.statusCode === "number" &&
        error.statusCode) ||
      400;

    const message = formatEsbuildError(error);
    res.status(statusCode).json({ error: message });
  }
};

/**
 * 告诉 Vercel：
 * - 把 tailwind.config.js 带进来（无论函数 cwd 是根目录还是 api 子目录）
 * - 把整个 node_modules/tailwindcss 包带进来（里面有 lib/css/preflight.css 等运行时必需的文件）
 *
 * 这一步就是修复 ENOENT: preflight.css 的关键。
 */
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
