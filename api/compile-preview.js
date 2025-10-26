// api/compile-preview.js (修复版)

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

const TAILWIND_INCLUDE_FILES = Array.from(
  new Set([
    ...TAILWIND_CONFIG_FILENAMES.map((name) => name),
    ...TAILWIND_CONFIG_FILENAMES.map((name) => path.posix.join("..", name)),
    "node_modules/tailwindcss/**/*",
  ])
);

/**
 * 🔥 关键修改：这些模块标记为 external，不打包，改用 CDN
 */
const EXTERNAL_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);

/**
 * 映射到 CDN 的全局变量名
 */
const EXTERNAL_GLOBALS = {
  "react": "React",
  "react-dom": "ReactDOM",
  "react-dom/client": "ReactDOM",
  "react/jsx-runtime": "React",
  "react/jsx-dev-runtime": "React",
  "lucide-react": "LucideReact",
};

/**
 * Node 内置模块
 */
const NODE_BUILTINS = new Set([
  ...builtinModules,
  ...builtinModules.map((name) => `node:${name}`),
  "process",
]);

const USER_CODE_VIRTUAL_PATH = "user-code";
const VIRTUAL_ENTRY_PATH = "virtual-entry";

const BASE_CSS = "@tailwind base;\n@tailwind components;\n@tailwind utilities;";

let cachedTailwindConfig = null;
let cachedTailwindConfigPath = null;
let cachedResolveDirPromise = null;

async function ensureResolveDir() {
  if (!cachedResolveDirPromise) {
    cachedResolveDirPromise = fs
      .mkdtemp(path.join(os.tmpdir(), "preview-entry-"))
      .catch(() => os.tmpdir());
  }
  return cachedResolveDirPromise;
}

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
  if (cachedTailwindConfigPath) {
    return cachedTailwindConfigPath;
  }

  const candidates = getAllCandidateConfigPaths();

  for (const fullPath of candidates) {
    try {
      console.info(`[compile-preview] checking Tailwind config at: ${fullPath}`);
      await fs.access(fullPath);
      cachedTailwindConfigPath = fullPath;
      console.info(`[compile-preview] Tailwind config FOUND at: ${fullPath}`);
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
  if (cachedTailwindConfig) {
    return cachedTailwindConfig;
  }

  const configPath = await findTailwindConfig();

  if (configPath) {
    try {
      console.info(`[compile-preview] loading Tailwind config from: ${configPath}`);
      cachedTailwindConfig = loadConfig(configPath);
      return cachedTailwindConfig;
    } catch (error) {
      console.error(
        `[compile-preview] Failed to load Tailwind config ${configPath}: ${
          error?.stack || error
        }`
      );
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
 * 🔥 核心修改：新的安全插件，将 external 模块映射到全局变量
 */
function createSecurityPlugin(resolveDir) {
  return {
    name: "preview-security",
    setup(build) {
      // 1. 拦截 external 模块，映射到全局变量
      build.onResolve({ filter: /.*/ }, (args) => {
        // 检查是否是 external 模块
        if (EXTERNAL_MODULES.has(args.path)) {
          return {
            path: args.path,
            namespace: "external-globals",
          };
        }

        // 禁止 Node 内置模块
        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [{ text: `模块 "${args.path}" 不允许在预览中使用。` }],
          };
        }

        // 处理相对路径
        if (args.path.startsWith(".") || path.isAbsolute(args.path)) {
          const baseDir = args.resolveDir || resolveDir;
          const resolved = path.resolve(baseDir, args.path);

          if (!resolved.startsWith(baseDir)) {
            return {
              errors: [{ text: `不允许访问受限目录之外的文件: ${args.path}` }],
            };
          }

          return { path: resolved };
        }

        // 其他模块一律拒绝（除非是 external）
        return {
          errors: [{ text: `模块 "${args.path}" 不在允许的依赖白名单中。` }],
        };
      });

      // 2. 为 external 模块提供全局变量映射
      build.onLoad({ filter: /.*/, namespace: "external-globals" }, (args) => {
        const globalName = EXTERNAL_GLOBALS[args.path];
        
        if (!globalName) {
          return {
            errors: [{ text: `找不到模块 "${args.path}" 的全局变量映射` }],
          };
        }

        // 根据不同的导入方式返回不同的代码
        let contents = "";

        if (args.path === "react") {
          contents = `module.exports = window.${globalName};`;
        } else if (args.path === "react-dom/client") {
          contents = `module.exports = window.ReactDOM;`;
        } else if (args.path === "react/jsx-runtime") {
          contents = `
            const React = window.React;
            module.exports = {
              jsx: React.createElement,
              jsxs: React.createElement,
              Fragment: React.Fragment
            };
          `;
        } else if (args.path === "react/jsx-dev-runtime") {
          contents = `
            const React = window.React;
            module.exports = {
              jsxDEV: React.createElement,
              Fragment: React.Fragment
            };
          `;
        } else if (args.path === "lucide-react") {
          contents = `module.exports = window.${globalName};`;
        } else {
          contents = `module.exports = window.${globalName};`;
        }

        return {
          contents,
          loader: "js",
        };
      });
    },
  };
}

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
      (error && typeof error.statusCode === "number" && error.statusCode) || 400;

    const message = formatEsbuildError(error);
    res.status(statusCode).json({ error: message });
  }
};

module.exports.config = {
  includeFiles: TAILWIND_INCLUDE_FILES,
};