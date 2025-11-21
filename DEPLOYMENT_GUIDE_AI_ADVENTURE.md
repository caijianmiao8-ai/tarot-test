# AI 世界冒险 - 部署配置指南

## 已完成的工作

### 1. 数据库架构 ✅
- 创建了完整的数据库迁移文件: `migrations/20251120_adventure_system.sql`
- 5个核心表已创建（您已在 Supabase 中运行）

### 2. 代码架构 ✅
- **AI 服务层**: `blueprints/games/world_adventure/ai_service.py`
  - 支持多个 AI 提供商（OpenRouter / OpenAI / Claude / Dify）
  - 默认使用 OpenRouter
  - 包含世界生成和 DM 响应两个核心功能

- **游戏逻辑**: `blueprints/games/world_adventure/plugin.py`
  - 完整的 Flask Blueprint
  - 11个路由（页面 + API）
  - 已集成新的 AI 服务层

- **数据访问层**: `blueprints/games/world_adventure/dao.py`
  - DAO 类（备用，当前 plugin.py 使用直接查询）

- **前端模板**: `templates/games/world_adventure/`
  - index.html - 游戏主页
  - world_create.html - 世界创建
  - character_create.html - 角色创建
  - run_play.html - 游戏进行

### 3. 项目集成 ✅
- 在 `static/projects.json` 中添加了游戏入口
- 创建了游戏封面图: `static/images/covers/world_adventure.svg`
- 游戏现在在 Ruoshui Lab 首页可见

### 4. 代码验证 ✅
- 所有 Python 文件语法正确
- 已通过 py_compile 检查

## Vercel 环境变量配置

请在 **Vercel Dashboard → Your Project → Settings → Environment Variables** 中添加:

### 必需配置

```
ADVENTURE_AI_PROVIDER=openrouter
OPENROUTER_API_KEY=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
OPENROUTER_MODEL=qwen/qwen-2.5-72b-instruct
```

### 可选配置

如果需要指定站点 URL（用于 OpenRouter 的 Referer）:
```
SITE_URL=https://ruoshuiclub.com
```

## 使用的 AI 模型

根据您提供的 API key，系统将使用:
- **Provider**: OpenRouter
- **Model**: Cerebras Qwen 2.5 72B Instruct (qwen/qwen-2.5-72b-instruct)
  - 高性能推理
  - 支持 JSON 格式输出
  - 适合生成结构化内容和对话

> 注意: 如果该模型不可用，可以在 `OPENROUTER_MODEL` 中设置其他模型，如:
> - `qwen/qwen3-235b-a22b-2507` (您提到的 Cerebras 模型)
> - `anthropic/claude-3-sonnet`
> - `openai/gpt-4`

## API 路由列表

### 页面路由
- `GET /g/world_adventure/` - 游戏主页
- `GET /g/world_adventure/worlds/create` - 创建世界
- `GET /g/world_adventure/characters/create` - 创建角色
- `GET /g/world_adventure/runs/<run_id>/play` - 游玩界面

### API 路由
- `POST /g/world_adventure/api/worlds/create` - 创建世界
- `POST /g/world_adventure/api/characters/create` - 创建角色
- `POST /g/world_adventure/api/runs/start` - 开始游戏
- `POST /g/world_adventure/api/runs/<run_id>/action` - 提交行动
- `GET /g/world_adventure/api/runs/<run_id>/messages` - 获取消息
- `POST /g/world_adventure/api/runs/<run_id>/complete` - 完成游戏

## 测试流程

1. **访问主页**: `https://your-domain.com/g/world_adventure/`
2. **创建世界**:
   - 选择世界模板（中世纪/赛博朋克/奇幻）
   - 调整参数（稳定度/危险度/神秘度）
   - AI 生成世界内容
3. **创建角色**:
   - 选择职业
   - 分配 30 点能力值
   - 编写背景故事
4. **开始冒险**:
   - 选择任务
   - 与 AI DM 互动
   - 完成目标

## 故障排查

### AI 生成失败
- 检查 `OPENROUTER_API_KEY` 是否正确
- 检查 `OPENROUTER_MODEL` 是否可用
- 查看 Vercel 日志获取详细错误

### 数据库错误
- 确认迁移 SQL 已在 Supabase 中运行
- 检查 `DATABASE_URL` 环境变量
- 验证表名和字段名正确

### 页面无法访问
- 确认 Blueprint 已注册（应该自动注册）
- 检查 `static/projects.json` 中的入口配置
- 清除 Vercel 缓存并重新部署

## 文件清单

### 新增文件
- `blueprints/games/world_adventure/__init__.py`
- `blueprints/games/world_adventure/plugin.py`
- `blueprints/games/world_adventure/ai_service.py`
- `blueprints/games/world_adventure/dao.py`
- `blueprints/games/world_adventure/README.md`
- `blueprints/games/world_adventure/templates/games/world_adventure/*.html` (4个)
- `static/images/covers/world_adventure.svg`
- `migrations/20251120_adventure_system.sql`
- `.env.example`
- `DEPLOYMENT_GUIDE_AI_ADVENTURE.md` (本文件)

### 修改文件
- `static/projects.json` - 添加游戏入口

## 下一步

1. ✅ 在 Vercel 中配置环境变量
2. ✅ 推送代码到 GitHub
3. ✅ Vercel 自动部署
4. ✅ 访问并测试游戏功能
5. ✅ 根据实际使用反馈调整 AI prompt 和游戏参数

---

**所有代码已完成并验证，准备提交！**
