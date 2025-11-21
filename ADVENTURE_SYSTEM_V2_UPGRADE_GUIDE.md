# 🎮 AI 世界冒险系统 V2 - 深度改进完整指南

## 📋 目录
- [核心设计理念](#核心设计理念)
- [架构变更总览](#架构变更总览)
- [数据库迁移指南](#数据库迁移指南)
- [新增功能](#新增功能)
- [部署步骤](#部署步骤)
- [测试指南](#测试指南)

---

## 🎯 核心设计理念

### 从"私有碎片世界"到"共享持久世界"

**V1 的问题：**
- ❌ 每个玩家创建独立世界，互不相关
- ❌ 世界数据静态，创建后不变
- ❌ AI上下文太少（只有5条历史消息）
- ❌ 没有任务结构和引导
- ❌ 玩家行动无法影响世界

**V2 的设计：**
- ✅ **3-5个官方共享世界**，所有玩家在同一世界冒险
- ✅ **动态世界扩展**，随玩家探索不断生长
- ✅ **关系网络系统**，玩家行动影响NPC和势力
- ✅ **结构化任务**，多检查点引导
- ✅ **骰子判定系统**，基于能力值的挑战
- ✅ **完整AI上下文**，包含位置、NPC、任务、历史

---

## 🏗️ 架构变更总览

### 新增数据库表（7个）

| 表名 | 用途 | 核心功能 |
|------|------|---------|
| `world_locations` | 地点系统 | 动态扩展的地点，记录访问量 |
| `world_npcs` | NPC系统 | 动态生成的NPC，状态追踪 |
| `world_factions` | 势力系统 | 势力关系和资源管理 |
| `world_quests` | 任务系统 | 结构化任务，多检查点 |
| `player_world_progress` | 进度追踪 | 每个玩家在各世界的探索状态 |
| `player_action_log` | 行动日志 | 完整的行动历史，用于分析 |
| `world_events` | 世界事件 | 玩家触发的世界级事件 |

### 修改的现有表

**`adventure_worlds`** - 添加字段：
- `is_official_world` - 是否为官方共享世界
- `world_slug` - URL友好的标识符
- `player_count` - 活跃玩家数
- `total_locations/npcs/quests` - 统计字段

**`adventure_runs`** - 添加字段：
- `current_quest_id` - 当前任务
- `current_location_id` - 当前位置
- `quest_progress` - 任务进度JSON

**`adventure_run_messages`** - 添加字段：
- `dice_result` - 骰子结果
- `ability_used` - 使用的能力
- `success_level` - 成功等级

### 新增核心模块

**1. `game_engine.py`** - 游戏引擎核心
```python
- DiceSystem          # 骰子判定系统
- QuestSystem         # 任务管理
- WorldStateTracker   # 状态追踪
- WorldExpansionEngine # 世界扩展
- GameEngine          # 主引擎整合
```

**2. `ai_service.py` (增强)** - AI服务
```python
- generate_dm_response_v2()  # 使用完整世界上下文
  - 15条历史对话（vs v1的5条）
  - 当前位置详情
  - 附近NPC列表
  - 任务进度和检查点
  - 已探索地点
  - 骰子判定结果
```

---

## 💾 数据库迁移指南

### 步骤 1: 备份现有数据

```sql
-- 在 Supabase SQL 编辑器中执行
-- 导出现有世界数据（如果需要保留）
SELECT * FROM adventure_worlds WHERE owner_user_id IS NOT NULL;
```

### 步骤 2: 执行 V2 迁移

在 Supabase SQL 编辑器中运行：
```
migrations/20251120_adventure_system_v2_shared_worlds.sql
```

**这将创建：**
- ✅ 7个新表及索引
- ✅ 官方世界：边境之地（带初始地点、NPC、势力、任务）
- ✅ 自动更新时间戳的触发器

### 步骤 3: 验证迁移

```sql
-- 检查新表是否创建成功
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name LIKE 'world_%';

-- 检查官方世界是否创建
SELECT * FROM adventure_worlds WHERE is_official_world = TRUE;

-- 检查初始数据
SELECT COUNT(*) as locations FROM world_locations;
SELECT COUNT(*) as npcs FROM world_npcs;
SELECT COUNT(*) as quests FROM world_quests;
```

**预期结果：**
- 3个地点（十字路镇、低语森林、古代遗迹）
- 2个NPC（艾莲娜、马库斯）
- 3个势力（商会联盟、守夜人、暗影教派）
- 1个任务（失踪的商队，5个检查点）

---

## 🎮 新增功能详解

### 1. 骰子判定系统 🎲

**工作原理：**
- 投掷 d20（20面骰）
- 加上能力修正值（能力值-5）
- 与难度值（DC）比较

**成功等级：**
- 🌟 **大成功** (Critical): 骰出20
- ✅ **成功** (Success): 总值 ≥ DC+5
- ⚠️ **部分成功** (Partial): 总值 ≥ DC
- ❌ **失败** (Failure): 总值 < DC 或骰出1

**触发条件：**
```python
# 自动检测行动类型，判断是否需要检定
攻击/战斗 → 战斗检定 (DC 12)
说服/交涉 → 社交检定 (DC 13)
潜行/隐藏 → 潜行检定 (DC 14)
调查/研究 → 知识检定 (DC 11)
```

**示例输出：**
```
🎲 成功 (骰出 15, 总计 18 vs DC 13)
- 行动顺利完成。
```

### 2. 任务系统 📜

**结构化任务：**
```json
{
  "quest_name": "失踪的商队",
  "checkpoints": [
    {
      "id": 1,
      "description": "与马库斯对话",
      "location": "loc-crossroads-town",
      "completed": false
    },
    {
      "id": 2,
      "description": "前往低语森林搜寻线索",
      "location": "loc-whispering-woods",
      "requires": {"ability": "knowledge", "dc": 12},
      "completed": false
    }
    // ...更多检查点
  ]
}
```

**进度追踪：**
- 每个检查点可以有能力检定要求
- DM会根据当前检查点引导玩家
- 完成检查点时明确告知玩家
- 显示进度（如 2/5 完成）

### 3. 世界状态追踪 🗺️

**记录内容：**
- ✅ 当前位置
- ✅ 已发现的地点列表
- ✅ 遇到过的NPC
- ✅ 与NPC的关系值（-100到+100）
- ✅ 对各势力的声望
- ✅ 完整的行动历史

**示例：**
```python
player_progress = {
    "current_location_id": "loc-crossroads-town",
    "discovered_locations": ["loc-crossroads-town", "loc-whispering-woods"],
    "visited_npcs": ["npc-elena-innkeeper", "npc-marcus-merchant"],
    "npc_relationships": {
        "npc-elena-innkeeper": {"reputation": 70, "interactions": 3}
    },
    "quest_progress": {
        "quest-missing-merchant": {
            "checkpoints_completed": [1, 2],
            "current_checkpoint": 2
        }
    }
}
```

### 4. 增强的AI上下文 🤖

**V1 vs V2 对比：**

| 维度 | V1 | V2 |
|------|----|----|
| 历史消息 | 5条 | 15条 |
| 位置信息 | ❌ 无 | ✅ 详细描述+危险等级 |
| NPC信息 | ❌ 无 | ✅ 附近NPC列表+性格 |
| 任务引导 | ❌ 只有标题 | ✅ 当前步骤+进度 |
| 骰子结果 | ❌ 无 | ✅ 完整判定结果 |
| 已探索 | ❌ 无 | ✅ 发现的地点列表 |

**AI Prompt 长度：**
- V1: ~400 tokens
- V2: ~1200 tokens（3倍上下文）

---

## 🚀 部署步骤

### 1. 数据库部署

```bash
# 在 Supabase SQL 编辑器中执行
migrations/20251120_adventure_system_v2_shared_worlds.sql
```

### 2. 代码部署

**新增文件：**
```
blueprints/games/world_adventure/
├── game_engine.py           ← 新增：游戏引擎核心
└── ai_service.py            ← 更新：增强AI上下文

migrations/
└── 20251120_adventure_system_v2_shared_worlds.sql  ← 新增：V2数据库架构
```

**环境变量（Vercel）：**
```bash
# 已有配置保持不变
OPENROUTER_API_KEY=sk-or-v1-xxx...
ADVENTURE_AI_PROVIDER=openrouter
OPENROUTER_MODEL=qwen/qwen-2.5-72b-instruct
```

### 3. Git 提交

```bash
git add migrations/20251120_adventure_system_v2_shared_worlds.sql
git add blueprints/games/world_adventure/game_engine.py
git add blueprints/games/world_adventure/ai_service.py
git add ADVENTURE_SYSTEM_V2_UPGRADE_GUIDE.md

git commit -m "Add Adventure System V2 - shared persistent worlds with quest/dice/state systems"

git push origin your-branch
```

### 4. Vercel 自动部署

- Vercel 检测到推送后自动部署
- 无需额外配置

---

## 🧪 测试指南

### 测试场景 1: 官方世界访问

1. 访问主页 `/g/world_adventure/`
2. 应该看到官方世界：**边境之地**
3. 选择世界和角色，开始冒险
4. 应该在"十字路镇"开始

**预期：**
- ✅ 世界描述详细
- ✅ 显示稳定度60/危险度55/神秘度70

### 测试场景 2: NPC互动

1. 输入："我想和艾莲娜聊天"
2. DM应该：
   - 识别NPC艾莲娜
   - 让艾莲娜说话
   - 提供旅馆相关的信息或任务线索

**预期：**
- ✅ NPC有对话
- ✅ 记录互动到 `player_world_progress.visited_npcs`

### 测试场景 3: 任务系统

1. 输入："我想接取任务"
2. 应该分配任务："失踪的商队"
3. DM引导：先与马库斯对话
4. 输入："我去找马库斯"
5. 完成检查点1

**预期：**
- ✅ 显示任务目标
- ✅ 明确说明"你完成了XXX"
- ✅ 引导下一步：前往低语森林

### 测试场景 4: 骰子判定

1. 输入："我尝试说服马库斯给我更好的报酬"
2. 应该触发**社交检定**
3. 显示骰子结果

**预期输出：**
```
🎲 成功 (骰出 16, 总计 19 vs DC 13)
马库斯沉思片刻，最终点头同意："好吧，看在你这么有诚意的份上，
我可以再加50金币。但你必须保证货物完好无损。"
```

### 测试场景 5: 位置移动

1. 输入："我前往低语森林"
2. 应该：
   - 更新当前位置
   - 添加到已发现列表
   - 详细描述森林

**预期：**
- ✅ `player_world_progress.current_location_id` 更新
- ✅ `world_locations.visit_count` 增加
- ✅ AI描述环境详细

---

## 📊 数据库查询示例

### 查看玩家进度

```sql
SELECT
    u.email,
    w.world_name,
    p.current_location_id,
    p.discovered_locations,
    p.exploration_percentage
FROM player_world_progress p
JOIN users u ON p.user_id = u.id
JOIN adventure_worlds w ON p.world_id = w.id
WHERE p.user_id = 'your-user-id';
```

### 查看世界统计

```sql
SELECT
    w.world_name,
    w.player_count,
    COUNT(DISTINCT l.id) as total_locations,
    COUNT(DISTINCT n.id) as total_npcs,
    COUNT(DISTINCT q.id) as total_quests
FROM adventure_worlds w
LEFT JOIN world_locations l ON w.id = l.world_id
LEFT JOIN world_npcs n ON w.id = n.world_id
LEFT JOIN world_quests q ON w.id = q.world_id
WHERE w.is_official_world = TRUE
GROUP BY w.id;
```

### 查看玩家行动日志

```sql
SELECT
    created_at,
    action_type,
    action_content,
    dice_roll,
    success,
    outcome
FROM player_action_log
WHERE user_id = 'your-user-id'
ORDER BY created_at DESC
LIMIT 20;
```

---

## 🔄 从 V1 迁移到 V2

### 选项 1: 全新开始（推荐）

1. 运行 V2 迁移SQL
2. 旧的玩家私有世界保留但不使用
3. 所有玩家在官方世界重新开始

### 选项 2: 保留旧数据

1. 运行 V2 迁移SQL
2. 将现有世界标记为"遗留世界"
3. 玩家可以继续旧游戏，但新游戏在官方世界

```sql
-- 标记现有世界为遗留
UPDATE adventure_worlds
SET world_slug = CONCAT('legacy-', id::text)
WHERE owner_user_id IS NOT NULL AND is_official_world IS NOT TRUE;
```

---

## 🎯 下一步计划

### 当前完成 (V2.0)
- ✅ 共享持久世界架构
- ✅ 骰子判定系统
- ✅ 任务检查点系统
- ✅ 状态追踪
- ✅ 增强AI上下文

### 未来规划 (V2.1+)
- [ ] 物品和装备系统
- [ ] 玩家间互动（组队）
- [ ] 世界级事件系统（完善）
- [ ] PvP/合作机制
- [ ] 成就和排行榜
- [ ] 动态生成新地点和NPC
- [ ] 可视化地图

---

## ❓ 常见问题

**Q: 旧的玩家世界会消失吗？**
A: 不会。旧数据仍在数据库中，但建议在官方世界重新开始。

**Q: 骰子判定可以关闭吗？**
A: 目前不可以，但检定失败不会导致游戏结束，只是影响结果。

**Q: 多个玩家会互相影响吗？**
A: 是的。一个玩家杀死NPC，其他玩家也会看到NPC死亡。

**Q: AI会记住之前的对话吗？**
A: 会。V2使用15条历史消息（vs V1的5条），上下文更丰富。

**Q: 可以创建更多官方世界吗？**
A: 可以。复制边境之地的SQL INSERT语句，修改数据即可。

---

## 📝 变更日志

### V2.0.0 (2025-11-20)
- ✅ 重构为共享持久世界架构
- ✅ 新增7个数据库表
- ✅ 实现骰子判定系统
- ✅ 实现结构化任务系统
- ✅ 实现玩家进度追踪
- ✅ 增强AI上下文（3倍提升）
- ✅ 创建官方世界：边境之地

### V1.0.0 (2025-11-19)
- 初始版本：私有世界系统

---

**作者**: Claude (Anthropic AI)
**日期**: 2025-11-20
**版本**: V2.0.0
