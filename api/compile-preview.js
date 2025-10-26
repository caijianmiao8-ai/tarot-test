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
 * 有些项目会把 tailwind.config.* 放到 styles/ 或 src/ 下面
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
 * 我们请求 Vercel 把这些文件/目录一起打进 serverless 函数：
 * 1. tailwind.config.*（当前目录、上级目录）
 * 2. 整个 tailwindcss 包 (node_modules/tailwindcss/**)
 *
 * 注意：在你的项目里 includeFiles 不一定完全生效，但留着没坏处。
 */
const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    // tailwind.config.* at cwd
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),

    // tailwind.config.* one level up (for runtimes like /var/task/api)
    ...TAILWIND_CONFIG_FILENAMES.map((name) =>
      path.posix.join("..", name)
    ),

    // try to ship the full tailwindcss package so internal css assets exist
    "node_modules/tailwindcss/**/*",
  ])
);

/**
 * 允许的依赖白名单（除了它们，其它 npm 包都不让用）
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
 * Node 内置模块（这些不允许在浏览器沙箱里）
 */
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

/**
 * 我们在 esbuild 里虚拟注入两个模块：
 * - user-code: 用户输入的 React 组件
 * - virtual-entry: 我们自动生成的入口，负责 createRoot/render 和错误上报
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
 * esbuild 需要一个安全的根目录，防止用户用相对路径逃出沙箱
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
 * 针对 Vercel 的实际运行情况：
 *   - cwd 通常像 /var/task
 *   - __dirname 对这个函数来说像 /var/task/api
 * tailwind.config.js 可能在仓库根（部署后对应 /var/task/tailwind.config.js）
 * 也可能（我们手动复制）在 /var/task/api/tailwind.config.js
 * 所以我们把这几种地方都尝试一下。
 */
function getAllCandidateConfigPaths() {
  const baseDirs = Array.from(
    new Set([
      process.cwd(),               // /var/task
      path.join(process.cwd(), ".."), // /var
      __dirname,                   // /var/task/api
      path.join(__dirname, ".."),  // /var/task
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
      // continue
    }
  }

  console.warn(
    `[compile-preview] No Tailwind config found.
cwd=${process.cwd()}
__dirname=${__dirname}
`
  );
  return null;
}

/**
 * 加载 tailwind.config.*
 * 找不到就 fallback 到我们内置主题（带 Inter / JetBrains Mono / 大圆角 / 玻璃阴影）
 * fallback 模式下我们不再报 500，而是照样生成 CSS
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
 * esbuild 安全插件
 *
 * 目标：
 *  - 阻止危险 import (Node 内置模块、非白名单外部包、目录逃逸)
 *  - 不要拦截「好人」(react / react-dom / lucide-react 等)
 *
 * 重点：如果我们决定“允许这个 import”，我们就 **return nothing**，
 * 让 esbuild 继续用默认解析逻辑，这样它能找到 node_modules 并把依赖打包进最终 bundle。
 *
 * 只有在我们需要亲自改写/拒绝解析时才 return 一个对象。
 */
function createSecurityPlugin(resolveDir) {
  return {
    name: "preview-security",
    setup(build) {
      build.onResolve({ filter: /.*/ }, (args) => {
        // 1. 禁止 Node 内置模块，比如 fs / path / process，
        //    也包括 node:fs 这种前缀形式
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 "${args.path}" 不允许在预览中使用。`,
              },
            ],
          };
        }

        // 2. 处理相对路径 / 绝对路径 import
        //    这种情况我们要做沙箱越界检查，然后给出绝对路径
        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const baseDir = args.resolveDir || resolveDir;
          const resolved = path.resolve(baseDir, args.path);

          // 阻止目录逃逸（import ../../../etc/passwd 这种骚操作）
          if (!resolved.startsWith(baseDir)) {
            return {
              errors: [
                {
                  text: `不允许访问受限目录之外的文件: ${args.path}`,
                },
              ],
            };
          }

          // 这里我们返回绝对路径，esbuild OK
          return { path: resolved };
        }

        // 3. 对于 "react", "react-dom/client", "lucide-react" 这类白名单依赖：
        //    我们什么都不返回，交给 esbuild 默认解析，它会去 node_modules 找到真实绝对路径。
        if (ALLOWED_MODULES.has(args.path)) {
          return; // allow, do not block, do not override
        }

        // 4. 依赖链内部：如果 importer 自己已经来自 node_modules，
        //    说明这是 react / lucide-react 内部的二级 import，
        //    我们也默认允许（不 return，继续让 esbuild 自己解析）。
        if (args.importer && args.importer.includes("node_modules")) {
          return;
        }

        // 5. 走到这里还没被允许的，全部拒绝
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
 * 把 esbuild 的报错转为可读字符串
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
 * 用 esbuild 把用户 JSX 打成单文件 IIFE：
 *  - 我们生成 virtual-entry:
 *    - import 用户组件
 *    - createRoot(#root).render(<UserComponent />)
 *    - 捕捉运行时错误并 postMessage 回父窗口
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
          // 注入 virtual-entry 入口
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

// 捕捉运行时异常 & 未处理 Promise 拒绝
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

          // 注入用户代码模块 user-code
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
 *  - 使用实际的 tailwind.config.* 或 fallback
 *  - 强制 corePlugins.preflight = false
 *    避免 Tailwind 读取它内置的 preflight.css（Vercel 打包有时不会带那个文件）
 *    这一步就是为了解决你之前的 ENOENT: preflight.css 500 崩溃
 */
async function generateTailwindCSS(source) {
  const loadedConfig = await loadTailwindConfigOrFallback();

  // 合并 / 覆盖 corePlugins
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
 * - 正常时返回 { js, css }
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
 * Vercel 函数打包配置
 * - 试图把 tailwind.config.* 和 tailwindcss 包一起带上
 *   （有的构建路径下它会忽略，但我们现在也不再依赖 preflight.css 了）
 */
module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};
