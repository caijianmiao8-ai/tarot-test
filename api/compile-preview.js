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
 *  - 打包 tailwind.config.*（当前目录、上级目录）
 *  - 打包整个 tailwindcss 包 (node_modules/tailwindcss/**)，
 *    以防它内部资源文件在 Runtime 丢失
 *
 * 注意：你的部署环境里 includeFiles 并不总是 100% 生效，
 * 但保留它不会坏事。
 */
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    // tailwind.config.* at cwd
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),

    // tailwind.config.* one level up (for runtimes like /var/task/api)
    ...TAILWIND_CONFIG_FILENAMES.map((name) =>
      path.posix.join("..", name)
    ),

    // try to ship the whole tailwindcss package (preflight.css etc)
    "node_modules/tailwindcss/**/*",
  ])
);

/**
 * 允许的 import 白名单
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
 * Node 内置模块（在浏览器预览环境中禁止）
 */
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

/**
 * 虚拟模块名：用户 React 代码 + 我们自动生成的入口
 */
const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

/**
 * Tailwind 基础层
 */
const BASE_CSS =
  "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

/**
 * 缓存
 */
let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

/**
 * esbuild 要有一个安全的根目录，避免用户代码用相对路径逃逸
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
 * 在 Vercel serverless 里，cwd 可能是 /var/task
 * 而 __dirname 可能是 /var/task/api
 * 我们都要试
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
 * 找 tailwind.config.*
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
      // keep trying
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
 * 尝试加载 tailwind.config.js
 * 找不到就走 fallback（我们内置一套高质感主题）
 * 关键点：我们现在不再因为找不到而直接 throw 500
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
      // fall through
    }
  }

  console.warn(
    "[compile-preview] Using internal fallback Tailwind config (preview will still render)"
  );

  // 兜底配置：让预览界面依然有 Inter 字体、圆角卡片、玻璃阴影
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
 *  - 禁止 Node 内置模块 (fs, process, path...)
 *  - 禁止 import 不在白名单里的 npm 包
 *  - 禁止相对路径逃出我们的 sandbox 目录
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

        // Node 内置模块禁用
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在预览中使用。`,
              },
            ],
          };
        }

        // 相对/绝对路径 import
        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const baseDir = args.resolveDir || resolveDir;
          const resolved = path.resolve(baseDir, args.path);

          // 防止逃逸
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

        // 白名单依赖 ok
        if (
          ALLOWED_MODULES.has(args.path) ||
          (args.importer && args.importer.includes("node_modules"))
        ) {
          return { path: args.path };
        }

        // 其他全部拒绝
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
 * 让 esbuild 报错变成人类可读字符串
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
 * 用 esbuild 把用户 JSX 打包成 IIFE：
 * - 我们构造 virtual-entry 入口，里面：
 *   - import 用户组件
 *   - createRoot(#root).render(<用户组件 />)
 *   - 捕捉运行时错误并 postMessage 传回父窗口
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
 * 生成 Tailwind CSS：
 * - 用 loadTailwindConfigOrFallback() 拿配置/兜底配置
 * - 强制加上 corePlugins.preflight = false
 *   这样 Tailwind 不会尝试去读它自己的 preflight.css
 *   -> 彻底规避 ENOENT: preflight.css
 */
async function generateTailwindCSS(source) {
  const loadedConfig = await loadTailwindConfigOrFallback();

  // 有些人会自定义 corePlugins，可能是对象，也可能是数组
  // 我们只在“对象”场景下合并，否则直接覆盖成 { preflight:false }
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
 * Vercel 函数打包配置
 * - 请求它把 tailwind.config.* 和 tailwindcss 包也带进运行环境
 *   （有的构建器会听话，有的不会，小概率还是丢）
 * - 我们现在即使丢了 preflight.css 也能跑，因为我们禁用了 preflight
 */
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
