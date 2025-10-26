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
 * Tailwind 配置文件可能的命名
 */
const TAILWIND_CONFIG_FILENAMES = [
  "tailwind.config.js",
  "tailwind.config.cjs",
  "tailwind.config.mjs",
  "tailwind.config.ts",
];

/**
 * 某些项目会把 tailwind.config.* 放在这些路径
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
 * 我们需要告诉 Vercel：
 *   “请把这些额外文件也一起打包进这个 serverless 函数里运行”
 *
 * 为什么？
 *  - 你的函数会在 Vercel 上被单独打成一个 /var/task 目录
 *  - Tailwind 在运行时会去读它自己的内部资源，比如它内置的 preflight.css
 *  - 默认情况下 Vercel 可能不会把 tailwindcss 包的这些额外静态资源文件带上
 *  - 于是运行时就会报 ENOENT 找不到 preflight.css
 *
 * 我们强制 include：
 *  1. 项目根目录下的 tailwind.config.* 这些文件
 *  2. 如果函数跑在 /var/task/api 目录，还要能访问上一级目录里的 tailwind.config.*，所以也把 ../tailwind.config.* 带上
 *  3. 整个 node_modules/tailwindcss 目录（包含它的内部 css 资源），这样运行时不至于缺 preflight.css
 */
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    // tailwind.config.* at cwd
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),

    // tailwind.config.* at parent of cwd (for runtimes like /var/task/api)
    ...TAILWIND_CONFIG_FILENAMES.map((name) =>
      path.posix.join("..", name)
    ),

    // ship the entire tailwindcss package files, including its internal css assets
    "node_modules/tailwindcss/**/*",
  ])
);

/**
 * 允许用户代码 import 的依赖白名单
 * 任何不在白名单里的模块会被拒绝，防止滥用
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
 * Node 内置模块（我们不允许在浏览器沙箱预览中使用这些）
 */
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

/**
 * 我们使用虚拟模块名来挂载用户输入的 React 组件代码
 * 以及我们的入口文件
 */
const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

/**
 * 基础 Tailwind 指令
 */
const BASE_CSS =
  "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

/**
 * 一些缓存，避免每个请求都重复做昂贵的工作
 */
let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

/**
 * esbuild 需要一个“安全的根目录”来解析相对 import
 * 我们用 tmp 目录，防止用户 import ../../../etc/passwd 之类的越狱
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
 * Vercel serverless 函数的真实运行目录不总是仓库根
 *   - 有时 cwd 是 /var/task
 *   - 有时 cwd 是 /var/task/api
 *   - __dirname 也可能是 /var/task/api
 *
 * 你的 tailwind.config.js 通常在仓库根（/var/task）
 * 我们就把这些可能的基准目录都试一遍
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
 * 实际去检测 tailwind.config.* 是否存在
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
      // ignore, keep trying
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
 *   - 如果我们能找到真实 tailwind.config.*，就用它
 *   - 如果找不到，就 fallback 一个内置配置（带 Inter/JetBrains Mono、圆角大玻璃卡片阴影等）
 *
 * 重点：我们不会再因为没找到 tailwind.config.js 就直接抛 500。
 * 这样右侧预览不会白屏报错，而是还能渲染出“高质感 UI”。
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
      // we'll fall back below
    }
  }

  console.warn(
    "[compile-preview] Using internal fallback Tailwind config (preview will still render)"
  );

  // fallback：保证 UI 依然有 Inter 字体、玻璃卡片、圆角、阴影等
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
            '"Noto Sans'",
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
 *   - 禁止 Node 内置模块（fs/process等）
 *   - 禁止不在白名单里的外部依赖
 *   - 禁止用相对路径逃出我们允许的临时目录
 */
function createSecurityPlugin(resolveDir) {
  return {
    name: "preview-security",
    setup(build) {
      build.onResolve({ filter: /.*/ }, (args) => {
        // 用户代码虚拟模块
        if (args.namespace === "user") {
          return { path: args.path, namespace: "user" };
        }

        // 禁用 Node 内置模块
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在预览中使用。`,
              },
            ],
          };
        }

        // 处理相对/绝对路径 import
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

        // 允许 import 白名单依赖
        if (
          ALLOWED_MODULES.has(args.path) ||
          (args.importer && args.importer.includes("node_modules"))
        ) {
          return { path: args.path };
        }

        // 否则拒绝
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
 * 把 esbuild 报错变成可读文本（让右上角 overlay 能显示友好信息）
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
 * 把用户代码打包成可直接在 iframe 里执行的 IIFE：
 *   - 我们生成一个 virtual-entry，负责：
 *     - import 用户组件
 *     - createRoot(#root).render(<用户组件 />)
 *     - 捕捉运行时错误 / Promise 未处理拒绝，并 postMessage 给父窗口
 *   - esbuild 输出单文件 IIFE，浏览器直接拿这个脚本跑
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
          // 入口 virtual-entry
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

// 捕捉运行时异常 & 未处理的 Promise 拒绝
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

          // 用户输入代码模块 user-code
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
 * 调用 Tailwind (通过 PostCSS) 生成当前代码所需的 CSS：
 *   - content 指向用户当前写的 JSX 源码
 *   - Tailwind 只会产出用到的类
 *   - 结合 fallback 配置后，即使没找到真实 tailwind.config.js，也能生成带质感的 UI
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
 * 解析请求体（POST /api/compile-preview）
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
 * /api/compile-preview 的主入口
 * 成功时返回 { js, css }
 * 失败时返回 { error }
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
 * Vercel 函数打包配置：
 * - 把 tailwind.config.* 带上（当前目录 & 上级目录）
 * - 把整个 node_modules/tailwindcss 目录带上（包含 preflight.css 等运行时依赖）
 *
 * 这一步就是为了解决：
 *   ENOENT: no such file or directory, open '.../tailwindcss/lib/css/preflight.css'
 */
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
