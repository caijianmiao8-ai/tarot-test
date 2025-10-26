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
 * 有些项目把 tailwind.config.* 放到 styles/ 或 src/ 下面
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
 *   “把这些额外文件也一起打包进 serverless 函数运行环境”
 *
 * 为什么？
 *  - Vercel 会把这个函数和依赖打成 /var/task
 *  - Tailwind 在运行时会去读它自带的一些资源，比如 preflight.css
 *  - 默认打包有时不会带上这些额外资源 -> ENOENT
 *
 * 我们强行 include：
 *  1. 可能存在的 tailwind.config.*（当前目录 + 上级目录）
 *  2. 整个 tailwindcss 包 (node_modules/tailwindcss/**)，这样它的内部 css 资源不会丢
 */
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    // tailwind.config.* at cwd
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),

    // tailwind.config.* one level up (for runtimes like /var/task/api)
    ...TAILWIND_CONFIG_FILENAMES.map((name) =>
      path.posix.join("..", name)
    ),

    // include the whole tailwindcss package so preflight.css etc is available
    "node_modules/tailwindcss/**/*",
  ])
);

/**
 * 允许用户代码 import 的依赖白名单
 * 其他 import 会直接被拒绝
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
 * Node 内置模块（这些在浏览器预览环境里是禁止的）
 */
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

/**
 * 我们使用虚拟模块名来承载用户传进来的 React 组件
 * 以及我们自动生成的入口
 */
const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

/**
 * Tailwind 的基础指令
 * 我们会用 PostCSS+Tailwind 把它展开成最终 CSS
 */
const BASE_CSS =
  "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

/**
 * 缓存，避免每次都重新准备
 */
let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

/**
 * esbuild 需要一个“安全根目录”用于解析相对 import
 * 我们用 /tmp 下的临时目录，避免用户试图用相对路径逃逸到系统文件
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
 * Vercel 上这个函数的 cwd/__dirname 可能是:
 *   /var/task
 *   /var/task/api
 * tailwind.config.js 通常在仓库根 (/var/task)
 *
 * 我们广撒网：cwd、cwd/..、__dirname、__dirname/.. 全试
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
      // not found, keep going
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
 *  - 如果能找到真实 tailwind.config.*，我们用它
 *  - 如果找不到，就 fallback 一个内置的配置
 *
 * fallback 的作用：
 *  即使 tailwind.config.js 没被正确打包进 serverless 函数，
 *  右侧 iframe 也不会白屏；它仍然会拿到一套“高质感”的默认主题
 *  （Inter 字体、JetBrains Mono、圆角玻璃卡片阴影等）
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

  // 兜底配置：别割裂你的视觉风格
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
            "Roboto",
            "Helvetica Neue",
            "Arial",
            "Noto Sans",
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
 *  - 禁 Node 内置模块
 *  - 禁掉不在白名单的 npm 包
 *  - 禁止相对路径逃出允许的 sandbox 目录
 */
function createSecurityPlugin(resolveDir) {
  return {
    name: "preview-security",
    setup(build) {
      build.onResolve({ filter: /.*/ }, (args) => {
        // 我们虚拟注入的用户模块
        if (args.namespace === "user") {
          return { path: args.path, namespace: "user" };
        }

        // 禁 Node 内置模块 (fs, process, path, etc.)
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在预览中使用。`,
              },
            ],
          };
        }

        // 处理相对或绝对路径的 import
        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const baseDir = args.resolveDir || resolveDir;
          const resolved = path.resolve(baseDir, args.path);

          // 防止逃离我们的 sandbox 根目录
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

        // 允许白名单依赖（react, react-dom, lucide-react 等）
        if (
          ALLOWED_MODULES.has(args.path) ||
          (args.importer && args.importer.includes("node_modules"))
        ) {
          return { path: args.path };
        }

        // 拒绝一切不在白名单中的依赖
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
 * 把 esbuild 的报错转成可读文本，方便右上角 overlay 展示
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
 * 用 esbuild 把用户的 React 代码打成一个 IIFE
 * 1. 我们声明一个 virtual-entry 入口模块
 * 2. 入口里：
 *    - import 用户组件
 *    - createRoot(#root).render(<UserComponent />)
 *    - 捕捉运行时错误 / Promise 拒绝并用 postMessage 通知父窗口
 * 3. esbuild 输出一个单文件的立即执行脚本，iframe 里直接跑
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
          // 我们的入口 virtual-entry
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

// 捕捉运行时错误和未处理的 Promise 拒绝
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
 * 用 Tailwind (通过 PostCSS) 生成当前用户代码所需的 CSS：
 *   - content 指向用户传入的 JSX 源码
 *   - Tailwind JIT 只吐出真正用到的类
 *   - 我们用 loadTailwindConfigOrFallback()，即使没真实 config 也能渲染漂亮 UI
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
 * /api/compile-preview 主入口
 * - 成功时返回 { js, css }
 * - 出错时返回 { error }
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
 * - 把 tailwind.config.* 带进来（当前目录 & 上级目录）
 * - 把整个 tailwindcss 包带进来（包含 preflight.css 等内部资源）
 *
 * 这就是修 ENOENT: preflight.css 的关键。
 */
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
