const { build } = require("esbuild");
const path = require("path");
const { builtinModules } = require("module");
const postcss = require("postcss");
const tailwindcss = require("tailwindcss");
const loadConfig = require("tailwindcss/loadConfig");
const fs = require("fs/promises");
const os = require("os");

const TAILWIND_CONFIG_CANDIDATES = [
  "tailwind.config.js",
  "tailwind.config.cjs",
  "tailwind.config.mjs",
  "tailwind.config.ts",
  "styles/tailwind.config.js",
  "styles/tailwind.config.cjs",
  "styles/tailwind.config.mjs",
  "src/tailwind.config.js",
  "src/styles/tailwind.config.js",
];

const TAILWIND_INCLUDE_FILES = TAILWIND_CONFIG_CANDIDATES.map((candidate) =>
  path.posix.join("..", candidate)
);

const ALLOWED_MODULES = new Set([
  "react",
  "react-dom",
  "react-dom/client",
  "react/jsx-runtime",
  "react/jsx-dev-runtime",
  "lucide-react",
]);
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

async function findTailwindConfig() {
  if (cachedTailwindConfigPath) {
    return cachedTailwindConfigPath;
  }

  for (const relative of TAILWIND_CONFIG_CANDIDATES) {
    const fullPath = path.join(process.cwd(), relative);
    console.info(`Checking for Tailwind config at: ${fullPath}`);
    try {
      await fs.access(fullPath);
      cachedTailwindConfigPath = fullPath;
      console.info(`Tailwind config found at: ${fullPath}`);
      return cachedTailwindConfigPath;
    } catch (error) {
      continue; // try next candidate
    }
  }

  console.warn("No Tailwind config found in any candidate location.");
  return null;
}

async function loadTailwindConfig() {
  if (cachedTailwindConfig) {
    return cachedTailwindConfig;
  }

  const configPath = await findTailwindConfig();
  if (!configPath) {
    return null;
  }

  try {
    console.info(`Loading Tailwind config from: ${configPath}`);
    cachedTailwindConfig = loadConfig(configPath);
    return cachedTailwindConfig;
  } catch (error) {
    console.error(
      `Failed to load Tailwind config from ${configPath}: ${error?.stack || error}`
    );
    const configError = new Error("无法加载 Tailwind 配置文件");
    configError.statusCode = 500;
    throw configError;
  }
}

function createSecurityPlugin(resolveDir) {
  return {
    name: "preview-security",
    setup(build) {
      build.onResolve({ filter: /.*/ }, (args) => {
        if (args.namespace === "user") {
          return { path: args.path, namespace: "user" };
        }

        if (NODE_BUILTINS.has(args.path)) {
          return {
            errors: [
              {
                text: `模块 \"${args.path}\" 不允许在预览中使用。`,
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

        if (
          ALLOWED_MODULES.has(args.path) ||
          (args.importer && args.importer.includes(`node_modules`))
        ) {
          return { path: args.path };
        }

        return {
          errors: [
            {
              text: `模块 \"${args.path}\" 不在允许的依赖白名单中。`,
            },
          ],
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
          build.onResolve({ filter: new RegExp(`^${VIRTUAL_ENTRY_PATH}$`) }, () => ({
            path: VIRTUAL_ENTRY_PATH,
            namespace: "virtual",
          }));

          build.onLoad({ filter: /.*/, namespace: "virtual" }, () => ({
            loader: "tsx",
            resolveDir,
            contents: `import React from "react";
import { createRoot } from "react-dom/client";
import UserComponent from "${USER_CODE_VIRTUAL_PATH}";

const reportError = (payload) => {
  try {
    const detail = payload && (payload.stack || payload.message)
      ? payload.stack || payload.message
      : String(payload);
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ type: "CODE_PLAYGROUND_ERROR", message: detail }, "*");
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

          build.onResolve({ filter: new RegExp(`^${USER_CODE_VIRTUAL_PATH}$`) }, () => ({
            path: USER_CODE_VIRTUAL_PATH,
            namespace: "user",
          }));

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
  const loaded = await loadTailwindConfig();
  if (!loaded) {
    const missing = new Error(
      "Tailwind 配置文件不存在，请在项目根目录提供 tailwind.config.js"
    );
    missing.statusCode = 500;
    throw missing;
  }

  const config = {
    ...loaded,
    content: [{ raw: source, extension: "jsx" }],
  };

  const result = await postcss([tailwindcss(config)]).process(BASE_CSS, {
    from: undefined,
  });

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
