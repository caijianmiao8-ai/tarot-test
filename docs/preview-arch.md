# 实时预览编译服务说明

## 架构概览

- 新增的 `api/compile-preview.js` 是一个 Vercel Node Serverless Function，用于在服务端即时打包来自前端代码编辑器的 React 组件源码。
- 前端 (`blueprints/games/code_playground/static/main.js`) 会在用户停止输入约 320ms 后，将完整源码通过 `POST /api/compile-preview` 发送给该函数。
- 函数使用 `esbuild`（Node 版本）把用户组件与运行时包装代码一起打包成单文件 JavaScript，并使用 `tailwindcss` JIT 根据源码生成实时样式。
- API 返回 `{ js, css }`，前端将其注入到 `<iframe>` 的 Blob HTML 中，实现高保真实时预览。

## 依赖白名单

- 目前允许的外部依赖是 `react`、`react-dom`、`lucide-react` 以及它们在构建时使用的内部依赖。
- 如果需要扩展，可以在 `ALLOWED_MODULES` 中加入新的包名，或根据 `args.importer` 实现更细粒度的判断逻辑。
- 出于安全考虑，Serverless 函数会阻止访问 Node 内置模块以及超出临时沙箱目录的文件路径。

## Tailwind 样式

- 根目录新增 `tailwind.config.js`，集中维护 UI 设计所需的字体、阴影与渐变等扩展。
- 函数通过 `tailwindcss` 的 `@tailwind base/components/utilities` 输出完整 CSS，并把用户源码作为 `raw` 内容喂给 JIT，确保只生成实际使用到的类。
- 若需新增 safelist 或插件，可直接在 `tailwind.config.js` 中修改；Serverless 函数会自动读取最新配置。

## 本地调试提示

1. 安装 Node 依赖：`npm install`
2. 启动本地后端（Flask）以及任何需要的前端资源。
3. 在浏览器中打开实时画板页面，修改代码即可触发服务端编译。

> 注意：Serverless 函数会返回 400 表示用户代码问题（如导入了未授权模块），500 表示服务端配置异常（例如缺少 Tailwind 配置）。
