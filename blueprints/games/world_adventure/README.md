# AI 世界冒险 (AI World Adventure)

单人跑团 · 持久世界 · AI DM

## 功能特性

- **AI 世界生成**: 使用 AI 生成独特的冒险世界，包括地点、势力、NPC
- **角色创建**: 自定义角色职业和能力（战斗/社交/潜行/知识/生存）
- **AI DM**: 智能 DM 系统，响应玩家行动并推进剧情
- **持久化存储**: 所有世界和游戏进度保存在 Supabase

## 数据库配置

1. 在 Supabase 中运行迁移文件:
   ```bash
   # 位于 migrations/20251120_adventure_system.sql
   ```

2. 该迁移会创建以下表:
   - `adventure_world_templates` - 世界模板
   - `adventure_worlds` - 世界实例
   - `adventure_characters` - 角色
   - `adventure_runs` - 游戏回合
   - `adventure_run_messages` - 对话历史

## AI 配置

### OpenRouter (推荐)

在 Vercel 环境变量中设置:

```
ADVENTURE_AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxx...
OPENROUTER_MODEL=qwen/qwen-2.5-72b-instruct
```

### 其他 AI 提供商

也支持 OpenAI、Claude 和 Dify。详见 `ai_service.py`。

## 使用流程

1. **创建世界**: 选择模板 → 设置参数 → AI 生成世界内容
2. **创建角色**: 选择职业 → 分配能力点（30点）→ 写背景故事
3. **开始冒险**: 选择任务 → 与 AI DM 互动 → 完成目标

## 技术栈

- **后端**: Flask Blueprint
- **数据库**: PostgreSQL (Supabase)
- **AI**: OpenRouter / OpenAI / Claude
- **前端**: Jinja2 模板
