# 网格地图系统设计 - 结构化世界探索

## 核心理念

**问题：** AI控制太多，导致游戏行为随机、不可预测
**解决：** 引入网格地图系统，用结构化数据约束AI

---

## 系统架构

### 1. 三层空间结构

```
世界 (World)
  └─ 地点 (Location) - 如"十字路镇"
       └─ 格子 (Grid) - 如"镇中心广场"、"马库斯商铺"、"城门口"
```

### 2. 数据表设计

#### A. location_grids 表（新增）

```sql
CREATE TABLE location_grids (
    id VARCHAR(36) PRIMARY KEY,
    location_id VARCHAR(36) REFERENCES world_locations(id),
    
    -- 基础信息
    grid_name VARCHAR(100),          -- "镇中心广场"
    grid_type VARCHAR(50),           -- "shop"/"street"/"building"/"wilderness"
    description TEXT,                -- 格子的详细描述
    
    -- 空间信息
    grid_position JSONB,             -- {x: 2, y: 3} 在地点中的位置
    connected_grids JSONB,           -- ["grid-id-1", "grid-id-2"] 相邻格子
    
    -- 环境属性
    atmosphere TEXT,                 -- "繁忙"/"安静"/"阴森"
    lighting VARCHAR(50),            -- "明亮"/"昏暗"/"黑暗"
    weather_affected BOOLEAN,        -- 是否受天气影响
    
    -- 交互元素
    npcs_present JSONB,              -- [{"npc_id": "xxx", "activity": "站在柜台后"}]
    objects JSONB,                   -- [{"name": "告示板", "interactive": true, "description": "..."}]
    events JSONB,                    -- [{"trigger": "first_visit", "description": "..."}]
    
    -- 探索状态
    requires_discovery BOOLEAN,      -- 是否需要探索才能发现
    discovery_condition TEXT,        -- "从艾伦处得知" 
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### B. 修改 world_npcs 表

```sql
ALTER TABLE world_npcs 
ADD COLUMN current_grid_id VARCHAR(36) REFERENCES location_grids(id),
ADD COLUMN activity_schedule JSONB;  -- NPC的行程表

-- activity_schedule 示例
{
  "morning": {"grid_id": "grid-shop-inside", "activity": "整理货架"},
  "afternoon": {"grid_id": "grid-town-square", "activity": "闲聊"},
  "evening": {"grid_id": "grid-tavern", "activity": "喝酒"}
}
```

#### C. 玩家位置追踪

```sql
ALTER TABLE player_world_progress
ADD COLUMN current_grid_id VARCHAR(36) REFERENCES location_grids(id);
```

---

## 工作流程

### 1. 玩家行动处理

```python
# 当玩家行动时
player_action = "我走向马库斯的商铺"

# 1. 确定当前格子
current_grid = get_player_grid(user_id, world_id)

# 2. 获取格子的结构化数据
grid_data = {
    'name': '镇中心广场',
    'description': '十字路镇的中心，人来人往...',
    'atmosphere': '繁忙',
    'npcs': [
        {'name': '马库斯', 'position': '商铺门口', 'activity': '整理货物'},
        {'name': '守卫', 'position': '岗哨旁', 'activity': '巡逻'}
    ],
    'objects': [
        {'name': '告示板', 'description': '上面贴着悬赏令'},
        {'name': '喷泉', 'description': '清澈的水流'}
    ],
    'connected_grids': ['马库斯商铺内部', '城门口', '小巷']
}

# 3. 分析玩家意图
if "走向" in player_action and "马库斯" in player_action:
    # 移动到相连的格子
    target_grid = find_grid_with_npc('马库斯', grid_data['connected_grids'])
    move_player_to_grid(user_id, target_grid)
    
# 4. 构建严格约束的AI提示
ai_prompt = f"""
【当前格子】
名称：{grid_data['name']}
描述：{grid_data['description']}
氛围：{grid_data['atmosphere']}

【可见的NPC】
{format_npcs(grid_data['npcs'])}

【可交互物品】
{format_objects(grid_data['objects'])}

【可前往】
{format_connected_grids(grid_data['connected_grids'])}

【玩家行动】
{player_action}

**你只能基于以上信息回应，不能编造不存在的内容。**
描述玩家行动的结果，必须符合当前格子的真实情况。
"""
```

### 2. 检查点检测（精确版）

```python
# 检查点定义（更精确）
checkpoint = {
    "id": 1,
    "description": "在马库斯商铺与他对话",
    "location_id": "loc-crossroads-town",
    "grid_id": "grid-marcus-shop-inside",     # 必须在这个格子
    "required_action": "dialogue",
    "required_npc": "npc-marcus-merchant"
}

# 检测逻辑（严格）
def check_completion(checkpoint, player_state, player_action):
    # 1. 玩家必须在正确的格子
    if player_state.current_grid_id != checkpoint['grid_id']:
        return False
    
    # 2. 行动类型必须匹配
    action_type = analyze_action(player_action)
    if action_type != checkpoint['required_action']:
        return False
    
    # 3. 必须与指定NPC互动
    if checkpoint['required_npc'] not in player_action:
        return False
    
    return True
```

---

## 示例：十字路镇的格子划分

```json
{
  "location_id": "loc-crossroads-town",
  "location_name": "十字路镇",
  "grids": [
    {
      "id": "grid-town-square",
      "name": "镇中心广场",
      "description": "十字路镇最繁华的地方，三条主要道路在此交汇...",
      "atmosphere": "繁忙",
      "npcs": [
        {"npc_id": "npc-guard-1", "activity": "站岗巡逻"},
        {"npc_id": "npc-merchant-woman", "activity": "摆摊叫卖"}
      ],
      "objects": [
        {"name": "告示板", "description": "商会发布的悬赏令"},
        {"name": "中央喷泉", "description": "镇子的地标"}
      ],
      "connected_grids": ["grid-marcus-shop-front", "grid-tavern-entrance", "grid-town-gate"]
    },
    {
      "id": "grid-marcus-shop-front",
      "name": "马库斯商铺门口",
      "description": "一家规模不小的杂货铺，招牌上写着'马库斯贸易行'",
      "npcs": [
        {"npc_id": "npc-marcus-merchant", "activity": "整理货物箱"}
      ],
      "objects": [
        {"name": "货物箱", "description": "堆放的商品"}
      ],
      "connected_grids": ["grid-town-square", "grid-marcus-shop-inside"]
    },
    {
      "id": "grid-marcus-shop-inside",
      "name": "马库斯商铺内部",
      "description": "货架上摆满了各种商品，从食物到工具应有尽有",
      "npcs": [
        {"npc_id": "npc-marcus-merchant", "activity": "站在柜台后"}
      ],
      "objects": [
        {"name": "货架", "description": "琳琅满目的商品"},
        {"name": "账本", "description": "马库斯的生意记录"}
      ],
      "connected_grids": ["grid-marcus-shop-front"]
    },
    {
      "id": "grid-tavern-entrance",
      "name": "醉酒鹿酒馆门口",
      "description": "镇上最热闹的酒馆，门口挂着一个鹿角招牌",
      "npcs": [
        {"npc_id": "npc-drunk-patron", "activity": "醉醺醺地倚着墙"}
      ],
      "connected_grids": ["grid-town-square", "grid-tavern-inside"]
    },
    {
      "id": "grid-town-gate",
      "name": "城门口",
      "description": "通往荒野的城门，守卫严密",
      "npcs": [
        {"npc_id": "npc-guard-captain", "activity": "检查过往行人"}
      ],
      "connected_grids": ["grid-town-square", "grid-forest-edge"]
    }
  ]
}
```

---

## 优势

### 1. AI行为可控
- AI只能描述格子中实际存在的内容
- 不能编造不存在的NPC或物品
- 行为受结构化数据约束

### 2. 检查点检测精确
- 玩家必须在正确的grid
- 必须执行正确的action
- 必须与正确的NPC互动
- 三重验证，不会误判

### 3. 空间感明确
- 玩家清楚知道自己在哪里
- 可以看到相邻的地方
- 移动逻辑清晰

### 4. 易于扩展
- 添加新格子只需插入数据
- 不需要修改代码逻辑
- 模块化设计

---

## 实现步骤

1. 创建 location_grids 表
2. 为"十字路镇"设计 5-8 个格子
3. 修改 player_world_progress 添加 current_grid_id
4. 更新 api_run_action 使用格子数据构建AI提示
5. 重写检查点检测逻辑（精确匹配grid_id）
6. 添加格子切换逻辑
7. UI显示当前格子信息

---

**这样，游戏就从"自由AI叙事"变成"结构化地图探索"，更可控、更精确。**
