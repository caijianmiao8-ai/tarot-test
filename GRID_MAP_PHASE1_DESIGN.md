# 网格地图系统 Phase 1 设计文档

## 概述

Phase 1 实现基础网格地图系统，将世界划分为结构化的格子，每个格子包含精确的环境、NPC、物体信息。AI 只能基于格子数据进行描述，检查点通过精确的 grid_id 匹配来完成。

---

## 1. 数据库架构

### 1.1 新表：location_grids

```sql
CREATE TABLE location_grids (
    id VARCHAR(36) PRIMARY KEY,
    location_id VARCHAR(36) REFERENCES world_locations(id) ON DELETE CASCADE,
    grid_name VARCHAR(100) NOT NULL,
    grid_type VARCHAR(50) NOT NULL,  -- 'town_square', 'building_interior', 'street', 'shop', 'wilderness', etc.
    description TEXT NOT NULL,

    -- 空间结构
    grid_position JSONB DEFAULT '{"x": 0, "y": 0}',
    connected_grids JSONB DEFAULT '[]',  -- [{grid_id, direction, description}]

    -- 环境元素
    atmosphere TEXT,
    lighting VARCHAR(50),  -- 'bright', 'dim', 'dark', 'flickering'

    -- NPC 存在
    npcs_present JSONB DEFAULT '[]',  -- [{npc_id, activity, position}]

    -- 可交互物体
    interactive_objects JSONB DEFAULT '[]',  -- [{id, name, type, description, interaction_type}]

    -- 元数据
    is_safe BOOLEAN DEFAULT true,
    first_visit_description TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_location_grids_location ON location_grids(location_id);
```

### 1.2 修改现有表：player_world_progress

```sql
ALTER TABLE player_world_progress
ADD COLUMN current_grid_id VARCHAR(36) REFERENCES location_grids(id);

CREATE INDEX idx_player_world_progress_grid ON player_world_progress(current_grid_id);
```

### 1.3 修改现有表：world_quests

检查点结构添加 grid_id 字段：

```json
{
  "checkpoints": [
    {
      "id": 1,
      "description": "在十字路镇与马库斯对话，了解商队详情",
      "location": "loc_crossroads_town_001",
      "grid_id": "grid_marcus_shop_inside",  // 新增
      "required_action": "dialogue",
      "target_npc": "npc_marcus_001"
    }
  ]
}
```

---

## 2. 十字路镇网格布局设计

### 2.1 空间结构

```
[城北道路]
    |
[城门广场] --- [镇中心广场] --- [商业街区]
                    |                |
                [酒馆门口]      [马库斯商铺]
                    |
                [酒馆内部]
```

### 2.2 网格详细设计

#### Grid 1: 镇中心广场 (Town Square)
```json
{
  "id": "grid_town_square_001",
  "location_id": "loc_crossroads_town_001",
  "grid_name": "镇中心广场",
  "grid_type": "town_square",
  "description": "十字路镇的中心广场，石板铺就的地面干净整洁。广场中央有一座古老的石制喷泉，清澈的水流从雕刻精美的狮子口中涌出。周围商铺林立，人来人往。",

  "grid_position": {"x": 1, "y": 1},

  "connected_grids": [
    {
      "grid_id": "grid_town_gate_001",
      "direction": "north",
      "description": "北面是城门广场，通往城外"
    },
    {
      "grid_id": "grid_commercial_street_001",
      "direction": "east",
      "description": "东面是商业街区，能看到马库斯的商铺招牌"
    },
    {
      "grid_id": "grid_tavern_entrance_001",
      "direction": "south",
      "description": "南面是酒馆入口，传来欢声笑语"
    }
  ],

  "atmosphere": "热闹繁忙，商贩叫卖声此起彼伏，偶尔传来马车驶过的声音",
  "lighting": "bright",

  "npcs_present": [
    {
      "npc_id": "npc_town_crier_001",
      "activity": "站在喷泉旁大声宣读最新的镇务公告",
      "position": "喷泉旁"
    },
    {
      "npc_id": "npc_fruit_vendor_001",
      "activity": "在摊位前整理新鲜水果",
      "position": "广场西侧"
    }
  ],

  "interactive_objects": [
    {
      "id": "obj_fountain_001",
      "name": "古老喷泉",
      "type": "landmark",
      "description": "一座有百年历史的石制喷泉，雕刻着守护镇子的狮子形象",
      "interaction_type": "examine"
    },
    {
      "id": "obj_notice_board_001",
      "name": "公告板",
      "type": "information",
      "description": "木制公告板上贴满了悬赏令和招工启事",
      "interaction_type": "read"
    }
  ],

  "is_safe": true,
  "first_visit_description": "你第一次来到十字路镇的中心广场。这里比你想象的更加繁荣，各种族的冒险者和商人在此交流。空气中弥漫着烤面包和香料的气味。"
}
```

#### Grid 2: 商业街区 (Commercial Street)
```json
{
  "id": "grid_commercial_street_001",
  "location_id": "loc_crossroads_town_001",
  "grid_name": "商业街区",
  "grid_type": "street",
  "description": "狭窄但整洁的石板街道，两侧是各式商铺。最显眼的是马库斯的综合商店，门口挂着\"可靠商队·马库斯\"的招牌。",

  "grid_position": {"x": 2, "y": 1},

  "connected_grids": [
    {
      "grid_id": "grid_town_square_001",
      "direction": "west",
      "description": "西面是镇中心广场"
    },
    {
      "grid_id": "grid_marcus_shop_001",
      "direction": "east",
      "description": "东面是马库斯商铺的入口"
    }
  ],

  "atmosphere": "商业气息浓厚，偶尔有马车运送货物经过",
  "lighting": "bright",

  "npcs_present": [
    {
      "npc_id": "npc_marcus_001",
      "activity": "站在商铺门口，正与一位顾客道别",
      "position": "商铺门口"
    },
    {
      "npc_id": "npc_street_kid_001",
      "activity": "蹲在街角观察过往行人",
      "position": "街道南侧"
    }
  ],

  "interactive_objects": [
    {
      "id": "obj_marcus_sign_001",
      "name": "马库斯商铺招牌",
      "type": "landmark",
      "description": "精心绘制的木制招牌，上面画着满载货物的马车",
      "interaction_type": "examine"
    },
    {
      "id": "obj_cargo_crates_001",
      "name": "货物箱",
      "type": "container",
      "description": "堆放在商铺门口的几个木箱，看起来是新到的货物",
      "interaction_type": "examine"
    }
  ],

  "is_safe": true,
  "first_visit_description": "你来到商业街区。马库斯的商铺在这里格外显眼，看起来生意兴隆。"
}
```

#### Grid 3: 马库斯商铺内部 (Marcus Shop Interior) - 关键检查点位置
```json
{
  "id": "grid_marcus_shop_001",
  "location_id": "loc_crossroads_town_001",
  "grid_name": "马库斯商铺内部",
  "grid_type": "building_interior",
  "description": "宽敞的商铺内部，货架上摆满了各种商品——从日常用品到冒险装备应有尽有。空气中有淡淡的皮革和香料气味。柜台后是通往仓库的门。",

  "grid_position": {"x": 3, "y": 1},

  "connected_grids": [
    {
      "grid_id": "grid_commercial_street_001",
      "direction": "west",
      "description": "西面是商铺门口，通往商业街区"
    }
  ],

  "atmosphere": "安静整洁，偶尔传来商品摆放的声音",
  "lighting": "bright",

  "npcs_present": [
    {
      "npc_id": "npc_marcus_001",
      "activity": "站在柜台后整理账本，看到你进来会抬起头",
      "position": "柜台后"
    }
  ],

  "interactive_objects": [
    {
      "id": "obj_shop_counter_001",
      "name": "商铺柜台",
      "type": "furniture",
      "description": "精心打磨的木制柜台，上面摆放着账本和货币箱",
      "interaction_type": "examine"
    },
    {
      "id": "obj_weapon_rack_001",
      "name": "武器架",
      "type": "display",
      "description": "靠墙的武器架上挂着各式武器，都保养得很好",
      "interaction_type": "examine"
    },
    {
      "id": "obj_map_table_001",
      "name": "地图桌",
      "type": "information",
      "description": "角落的桌子上展开着一张区域地图，上面标注着商队路线",
      "interaction_type": "examine"
    }
  ],

  "is_safe": true,
  "first_visit_description": "你走进马库斯的商铺。这里比外表看起来更大，商品种类繁多且摆放有序。马库斯显然是个经验丰富的商人。"
}
```

#### Grid 4: 城门广场 (Town Gate Square)
```json
{
  "id": "grid_town_gate_001",
  "location_id": "loc_crossroads_town_001",
  "grid_name": "城门广场",
  "grid_type": "town_square",
  "description": "十字路镇的北门广场，厚重的木制大门敞开着。守卫站在门旁警惕地观察进出的人。广场上有几辆准备出发或刚到达的马车。",

  "grid_position": {"x": 1, "y": 0},

  "connected_grids": [
    {
      "grid_id": "grid_town_square_001",
      "direction": "south",
      "description": "南面是镇中心广场"
    },
    {
      "grid_id": "grid_north_road_001",
      "direction": "north",
      "description": "北面是通往暗影之森的道路（未开放）"
    }
  ],

  "atmosphere": "略显紧张，守卫保持警惕，马车夫忙碌地准备货物",
  "lighting": "bright",

  "npcs_present": [
    {
      "npc_id": "npc_town_guard_001",
      "activity": "站在城门旁，检查进出人员",
      "position": "城门左侧"
    },
    {
      "npc_id": "npc_caravan_driver_001",
      "activity": "检查马车轮子，准备出发",
      "position": "广场中央"
    }
  ],

  "interactive_objects": [
    {
      "id": "obj_town_gate_001",
      "name": "镇子大门",
      "type": "landmark",
      "description": "坚固的木制大门，上面刻着十字路镇的徽记",
      "interaction_type": "examine"
    },
    {
      "id": "obj_merchant_cart_001",
      "name": "商队马车",
      "type": "vehicle",
      "description": "一辆装满货物的马车，看起来即将出发",
      "interaction_type": "examine"
    }
  ],

  "is_safe": true,
  "first_visit_description": "你来到城门广场。这里是镇子与外界的连接点，充满了冒险的气息。"
}
```

#### Grid 5: 酒馆入口 (Tavern Entrance)
```json
{
  "id": "grid_tavern_entrance_001",
  "location_id": "loc_crossroads_town_001",
  "grid_name": "酒馆入口",
  "grid_type": "building_entrance",
  "description": "\"跃马酒馆\"的入口，挂着一块画着跃起骏马的招牌。门内传来喧闹的说笑声和音乐声，空气中飘出麦芽酒和炖肉的香味。",

  "grid_position": {"x": 1, "y": 2},

  "connected_grids": [
    {
      "grid_id": "grid_town_square_001",
      "direction": "north",
      "description": "北面是镇中心广场"
    },
    {
      "grid_id": "grid_tavern_interior_001",
      "direction": "south",
      "description": "推门进入酒馆内部"
    }
  ],

  "atmosphere": "温暖诱人，传来的笑声和音乐让人想要进去休息",
  "lighting": "bright",

  "npcs_present": [
    {
      "npc_id": "npc_drunk_patron_001",
      "activity": "靠在门口墙边，醉醺醺地哼着小调",
      "position": "门口右侧"
    }
  ],

  "interactive_objects": [
    {
      "id": "obj_tavern_sign_001",
      "name": "酒馆招牌",
      "type": "landmark",
      "description": "精美的彩绘招牌，描绘着一匹骏马跃过栅栏",
      "interaction_type": "examine"
    }
  ],

  "is_safe": true,
  "first_visit_description": "你来到跃马酒馆门口。这里看起来是镇上最热闹的地方。"
}
```

#### Grid 6: 酒馆内部 (Tavern Interior)
```json
{
  "id": "grid_tavern_interior_001",
  "location_id": "loc_crossroads_town_001",
  "grid_name": "酒馆内部",
  "grid_type": "building_interior",
  "description": "温暖舒适的酒馆大厅，壁炉里火焰跳动。木桌木椅摆放整齐，大部分座位都有客人。吧台后面，酒保忙碌地倒酒。角落里有位吟游诗人正在弹奏竖琴。",

  "grid_position": {"x": 1, "y": 3},

  "connected_grids": [
    {
      "grid_id": "grid_tavern_entrance_001",
      "direction": "north",
      "description": "北面是酒馆门口"
    }
  ],

  "atmosphere": "喧闹但友好，充满了冒险者的交谈声和欢笑声",
  "lighting": "dim",

  "npcs_present": [
    {
      "npc_id": "npc_innkeeper_001",
      "activity": "在吧台后擦拭酒杯，与客人交谈",
      "position": "吧台后"
    },
    {
      "npc_id": "npc_bard_001",
      "activity": "坐在角落弹奏竖琴，唱着关于远方冒险的歌谣",
      "position": "角落"
    },
    {
      "npc_id": "npc_veteran_adventurer_001",
      "activity": "独自坐在靠窗的位置喝酒，似乎在思考什么",
      "position": "窗边桌"
    }
  ],

  "interactive_objects": [
    {
      "id": "obj_fireplace_001",
      "name": "壁炉",
      "type": "landmark",
      "description": "温暖的壁炉，火焰舞动着橙色的光芒",
      "interaction_type": "examine"
    },
    {
      "id": "obj_quest_board_001",
      "name": "任务板",
      "type": "information",
      "description": "墙上的木板，钉着几张委托书和悬赏令",
      "interaction_type": "read"
    },
    {
      "id": "obj_bar_counter_001",
      "name": "吧台",
      "type": "furniture",
      "description": "长长的木制吧台，摆满了各种酒瓶",
      "interaction_type": "examine"
    }
  ],

  "is_safe": true,
  "first_visit_description": "你推门走进酒馆。温暖的空气和热闹的氛围立刻包围了你。这里是冒险者聚集的地方，空气中弥漫着故事和机会的气息。"
}
```

---

## 3. 检查点更新

### 3.1 任务：森林深处的呼唤

更新检查点定义，添加精确的 grid_id：

```json
{
  "id": "quest_shadow_forest_001",
  "quest_name": "森林深处的呼唤",
  "checkpoints": [
    {
      "id": 1,
      "description": "在十字路镇与马库斯对话，了解商队详情",
      "location": "loc_crossroads_town_001",
      "grid_id": "grid_marcus_shop_001",
      "required_action": "dialogue",
      "target_npc": "npc_marcus_001"
    },
    {
      "id": 2,
      "description": "在酒馆收集关于暗影之森的情报",
      "location": "loc_crossroads_town_001",
      "grid_id": "grid_tavern_interior_001",
      "required_action": "investigation",
      "target_npc": null
    },
    {
      "id": 3,
      "description": "前往暗影之森边缘，寻找商队踪迹",
      "location": "loc_shadow_forest_edge_001",
      "grid_id": "grid_forest_edge_camp_001",
      "required_action": "exploration",
      "target_npc": null
    }
  ]
}
```

---

## 4. 检查点完成逻辑

### 4.1 三重验证机制

```python
def check_checkpoint_completion(checkpoint, analysis, world_context, player_progress):
    """
    精确的检查点完成检测（基于网格系统）
    """
    # 1. 网格验证（最重要）
    required_grid_id = checkpoint.get('grid_id')
    current_grid_id = player_progress.get('current_grid_id')

    if required_grid_id != current_grid_id:
        return False  # 不在正确的网格，直接失败

    # 2. 行动类型验证
    required_action = checkpoint.get('required_action')
    player_action_type = analysis.get('action_type')

    if required_action == 'dialogue':
        if player_action_type != 'dialogue':
            return False
    elif required_action == 'investigation':
        if player_action_type not in ['dialogue', 'examine', 'search']:
            return False
    elif required_action == 'exploration':
        # 探索类型较宽松，到达网格即可
        pass

    # 3. 目标NPC验证（如果需要）
    target_npc = checkpoint.get('target_npc')
    if target_npc:
        action_targets = analysis.get('targets', [])
        npc_found = any(
            t.get('type') == 'npc' and t.get('id') == target_npc
            for t in action_targets
        )
        if not npc_found:
            return False

    return True
```

### 4.2 工作流程

1. 玩家输入行动：「我走进马库斯的商铺，向他询问商队的情况」
2. 系统解析行动：
   - 检测到移动意图 → 更新 current_grid_id = "grid_marcus_shop_001"
   - 检测到对话意图 → action_type = "dialogue"
   - 检测到目标NPC → target = "npc_marcus_001"
3. 检查点验证：
   - ✅ grid_id 匹配
   - ✅ action_type 匹配
   - ✅ target_npc 匹配
   - → 完成检查点 1

---

## 5. AI 提示词约束

### 5.1 网格数据注入

```python
def get_grid_context_for_ai(current_grid_id):
    """
    获取当前网格的完整数据，注入AI提示词
    """
    grid = fetch_grid_by_id(current_grid_id)

    context = f"""
【当前位置】
📍 {grid['grid_name']} ({grid['grid_type']})

【环境描述】
{grid['description']}

【氛围】{grid['atmosphere']}
【光线】{grid['lighting']}

【可见NPC】
"""

    for npc in grid['npcs_present']:
        npc_data = fetch_npc_by_id(npc['npc_id'])
        context += f"- {npc_data['npc_name']}: {npc['activity']}\n"

    context += "\n【可交互物体】\n"
    for obj in grid['interactive_objects']:
        context += f"- {obj['name']}: {obj['description']}\n"

    context += "\n【可前往的地点】\n"
    for conn in grid['connected_grids']:
        conn_grid = fetch_grid_by_id(conn['grid_id'])
        context += f"- {conn['direction']}: {conn_grid['grid_name']} - {conn['description']}\n"

    return context
```

### 5.2 AI 约束指令

```python
ai_constraint = """
⚠️ 重要约束 ⚠️

你只能描述【当前位置】数据中存在的内容：
1. 只能描述列出的NPC及其活动
2. 只能描述列出的物体
3. 只能让玩家前往【可前往的地点】中列出的网格
4. 不能随意创造新NPC、新物体、新地点

如果玩家尝试做不在数据范围内的事，你应该：
- 说明该事物不存在或不可用
- 引导玩家关注实际存在的选项
- 例如：「你没有看到那个人」「这里没有那个东西」
"""
```

---

## 6. 玩家移动系统

### 6.1 移动检测

```python
class GridMovementSystem:
    """
    网格移动系统
    """

    @staticmethod
    def detect_movement(action_text, current_grid_id):
        """
        检测玩家是否尝试移动到其他网格
        """
        current_grid = fetch_grid_by_id(current_grid_id)
        connected = current_grid['connected_grids']

        # 检测方向关键词
        direction_map = {
            'north': ['北', '北面', '往北', '向北'],
            'south': ['南', '南面', '往南', '向南'],
            'east': ['东', '东面', '往东', '向东'],
            'west': ['西', '西面', '往西', '向西']
        }

        for conn in connected:
            direction = conn['direction']
            keywords = direction_map.get(direction, [])

            # 检查方向关键词
            if any(kw in action_text for kw in keywords):
                return conn['grid_id']

            # 检查目标网格名称
            target_grid = fetch_grid_by_id(conn['grid_id'])
            if target_grid['grid_name'] in action_text:
                return conn['grid_id']

        return None  # 没有检测到移动

    @staticmethod
    def execute_movement(user_id, world_id, new_grid_id):
        """
        执行移动，更新数据库
        """
        update_player_grid(user_id, world_id, new_grid_id)

        new_grid = fetch_grid_by_id(new_grid_id)

        # 检查是否首次访问
        visit_history = fetch_player_visit_history(user_id, world_id)
        is_first_visit = new_grid_id not in visit_history

        if is_first_visit:
            record_grid_visit(user_id, world_id, new_grid_id)
            description = new_grid.get('first_visit_description') or new_grid['description']
        else:
            description = new_grid['description']

        return {
            'moved': True,
            'new_grid': new_grid,
            'description': description,
            'is_first_visit': is_first_visit
        }
```

---

## 7. UI 更新

### 7.1 左侧边栏添加网格信息

```html
<!-- 当前网格 -->
<div class="info-section">
    <h4>📍 当前位置</h4>
    <div class="current-grid">
        <div class="grid-name">{{ current_grid.grid_name }}</div>
        <div class="grid-type">{{ current_grid.grid_type }}</div>

        <!-- 可前往的地点 -->
        <div class="connections">
            <h5>可前往：</h5>
            <ul>
                {% for conn in current_grid.connected_grids %}
                <li>
                    <span class="direction">{{ conn.direction }}</span>
                    <span class="target">{{ conn.target_name }}</span>
                </li>
                {% endfor %}
            </ul>
        </div>
    </div>
</div>

<!-- 附近NPC -->
<div class="info-section">
    <h4>👥 附近的人物</h4>
    <ul class="npc-list">
        {% for npc in current_grid.npcs_present %}
        <li class="npc-item">
            <strong>{{ npc.name }}</strong>
            <div class="npc-activity">{{ npc.activity }}</div>
        </li>
        {% endfor %}
    </ul>
</div>

<!-- 可交互物体 -->
<div class="info-section">
    <h4>🔍 可交互物体</h4>
    <ul class="object-list">
        {% for obj in current_grid.interactive_objects %}
        <li class="object-item">
            <strong>{{ obj.name }}</strong>
            <div class="object-desc">{{ obj.description }}</div>
        </li>
        {% endfor %}
    </ul>
</div>
```

---

## 8. 实施步骤

### Phase 1a: 数据库层（第1优先级）

1. 创建 location_grids 表
2. 修改 player_world_progress 添加 current_grid_id
3. 为十字路镇插入 6 个网格数据
4. 更新任务检查点添加 grid_id

### Phase 1b: 后端逻辑（第2优先级）

1. 实现 GridMovementSystem 类
2. 更新 CheckpointDetector 使用 grid_id 验证
3. 更新 ActionAnalyzer 检测移动意图
4. 修改 GameEngine.process_player_action() 集成网格系统

### Phase 1c: AI 集成（第3优先级）

1. 实现 get_grid_context_for_ai()
2. 更新 ai_service.py 注入网格约束
3. 修改 AI 提示词添加严格约束

### Phase 1d: UI 更新（第4优先级）

1. 更新 run_play.html 显示网格信息
2. 添加网格连接可视化
3. 更新 CSS 样式

---

## 9. 测试场景

### 测试 1: 网格移动
1. 玩家输入：「我走向商业街区」
2. 预期：系统检测移动，更新 current_grid_id，显示新网格描述
3. 验证：左侧边栏更新为新网格信息

### 测试 2: 检查点完成
1. 玩家输入：「我走进马库斯的商铺，询问商队的情况」
2. 预期：
   - 系统检测移动到 grid_marcus_shop_001
   - 系统检测对话行动 + 目标NPC
   - 完成检查点 1
3. 验证：任务栏显示 ✅ 第一个检查点

### 测试 3: AI 约束
1. 玩家输入：「我去找城主」（城主不在数据中）
2. 预期：AI 回应「你在这里没有看到城主」并引导关注实际存在的NPC
3. 验证：AI 不会随意创造城主角色

### 测试 4: 首次访问
1. 玩家首次进入某个网格
2. 预期：显示 first_visit_description
3. 验证：再次进入显示普通 description

---

## 10. 预期效果

### 问题解决

| 问题 | Phase 1 解决方案 |
|-----|----------------|
| AI 太随机，创造不存在的内容 | 网格数据约束，AI 只能描述存在的元素 |
| 检查点不推进 | 精确的 grid_id 匹配 + 三重验证 |
| 玩家行动不影响世界 | 网格系统记录访问历史、NPC 互动 |
| 没有线性引导 | 检查点明确指定 grid_id，玩家必须到达 |

### 游戏体验提升

1. **空间感更强**：玩家清楚自己在哪个网格，可以去哪里
2. **目标更明确**：知道要去哪个网格完成任务
3. **世界更真实**：NPC 有固定位置和活动，不会凭空出现
4. **进度可控**：系统能精确判断玩家是否完成检查点

---

## 总结

Phase 1 实现了基础但完整的网格地图系统，核心特性：

✅ 结构化空间数据（6个网格覆盖十字路镇）
✅ 精确的检查点验证（grid_id 匹配）
✅ AI 行为约束（只能描述存在的内容）
✅ 网格移动系统（自动检测和更新）
✅ UI 可视化（显示当前网格和连接）

这为后续 Phase 2（事件触发、NPC 日程）和 Phase 3（战斗、物品）奠定了坚实基础。
