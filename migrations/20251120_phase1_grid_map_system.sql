-- ========================================
-- Phase 1: 网格地图系统迁移
-- ========================================
-- 创建结构化网格系统，将世界划分为精确的格子
-- 每个格子包含环境、NPC、物体等结构化数据
-- AI 只能基于格子数据进行描述，实现精确的任务进度控制

-- ========================================
-- 1. 创建 location_grids 表
-- ========================================

CREATE TABLE IF NOT EXISTS location_grids (
    id VARCHAR(36) PRIMARY KEY,
    location_id VARCHAR(36) REFERENCES world_locations(id) ON DELETE CASCADE,
    grid_name VARCHAR(100) NOT NULL,
    grid_type VARCHAR(50) NOT NULL,  -- 'town_square', 'building_interior', 'street', 'shop', 'wilderness'
    description TEXT NOT NULL,

    -- 空间结构
    grid_position JSONB DEFAULT '{"x": 0, "y": 0}',
    connected_grids JSONB DEFAULT '[]',  -- [{grid_id, direction, description, target_name}]

    -- 环境元素
    atmosphere TEXT,
    lighting VARCHAR(50) DEFAULT 'bright',  -- 'bright', 'dim', 'dark', 'flickering'

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

COMMENT ON TABLE location_grids IS '世界地点的网格细分，每个网格是一个精确的游戏空间';
COMMENT ON COLUMN location_grids.connected_grids IS '连接的网格 [{grid_id, direction, description, target_name}]';
COMMENT ON COLUMN location_grids.npcs_present IS 'NPC列表 [{npc_id, activity, position}]';
COMMENT ON COLUMN location_grids.interactive_objects IS '可交互物体 [{id, name, type, description, interaction_type}]';

-- ========================================
-- 2. 修改 player_world_progress 表
-- ========================================

ALTER TABLE player_world_progress
ADD COLUMN IF NOT EXISTS current_grid_id VARCHAR(36) REFERENCES location_grids(id);

CREATE INDEX IF NOT EXISTS idx_player_world_progress_grid ON player_world_progress(current_grid_id);

COMMENT ON COLUMN player_world_progress.current_grid_id IS '玩家当前所在的网格ID';

-- ========================================
-- 3. 插入十字路镇的 6 个网格
-- ========================================

-- Grid 1: 镇中心广场
INSERT INTO location_grids (
    id, location_id, grid_name, grid_type, description,
    grid_position, connected_grids,
    atmosphere, lighting,
    npcs_present, interactive_objects,
    is_safe, first_visit_description
) VALUES (
    'grid_town_square_001',
    'loc_crossroads_town_001',
    '镇中心广场',
    'town_square',
    '十字路镇的中心广场，石板铺就的地面干净整洁。广场中央有一座古老的石制喷泉，清澈的水流从雕刻精美的狮子口中涌出。周围商铺林立，人来人往。',

    '{"x": 1, "y": 1}',
    '[
        {
            "grid_id": "grid_town_gate_001",
            "direction": "north",
            "description": "北面是城门广场，通往城外",
            "target_name": "城门广场"
        },
        {
            "grid_id": "grid_commercial_street_001",
            "direction": "east",
            "description": "东面是商业街区，能看到马库斯的商铺招牌",
            "target_name": "商业街区"
        },
        {
            "grid_id": "grid_tavern_entrance_001",
            "direction": "south",
            "description": "南面是酒馆入口，传来欢声笑语",
            "target_name": "酒馆入口"
        }
    ]',

    '热闹繁忙，商贩叫卖声此起彼伏，偶尔传来马车驶过的声音',
    'bright',

    '[
        {
            "npc_id": "npc_town_crier_001",
            "npc_name": "镇务传令官",
            "activity": "站在喷泉旁大声宣读最新的镇务公告",
            "position": "喷泉旁"
        },
        {
            "npc_id": "npc_fruit_vendor_001",
            "npc_name": "水果小贩",
            "activity": "在摊位前整理新鲜水果",
            "position": "广场西侧"
        }
    ]',

    '[
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
    ]',

    true,
    '你第一次来到十字路镇的中心广场。这里比你想象的更加繁荣，各种族的冒险者和商人在此交流。空气中弥漫着烤面包和香料的气味。'
);

-- Grid 2: 商业街区
INSERT INTO location_grids (
    id, location_id, grid_name, grid_type, description,
    grid_position, connected_grids,
    atmosphere, lighting,
    npcs_present, interactive_objects,
    is_safe, first_visit_description
) VALUES (
    'grid_commercial_street_001',
    'loc_crossroads_town_001',
    '商业街区',
    'street',
    '狭窄但整洁的石板街道，两侧是各式商铺。最显眼的是马库斯的综合商店，门口挂着"可靠商队·马库斯"的招牌。',

    '{"x": 2, "y": 1}',
    '[
        {
            "grid_id": "grid_town_square_001",
            "direction": "west",
            "description": "西面是镇中心广场",
            "target_name": "镇中心广场"
        },
        {
            "grid_id": "grid_marcus_shop_001",
            "direction": "east",
            "description": "东面是马库斯商铺的入口",
            "target_name": "马库斯商铺"
        }
    ]',

    '商业气息浓厚，偶尔有马车运送货物经过',
    'bright',

    '[
        {
            "npc_id": "npc_marcus_001",
            "npc_name": "马库斯",
            "activity": "站在商铺门口，正与一位顾客道别",
            "position": "商铺门口"
        },
        {
            "npc_id": "npc_street_kid_001",
            "npc_name": "街头少年",
            "activity": "蹲在街角观察过往行人",
            "position": "街道南侧"
        }
    ]',

    '[
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
    ]',

    true,
    '你来到商业街区。马库斯的商铺在这里格外显眼，看起来生意兴隆。'
);

-- Grid 3: 马库斯商铺内部（关键检查点位置）
INSERT INTO location_grids (
    id, location_id, grid_name, grid_type, description,
    grid_position, connected_grids,
    atmosphere, lighting,
    npcs_present, interactive_objects,
    is_safe, first_visit_description
) VALUES (
    'grid_marcus_shop_001',
    'loc_crossroads_town_001',
    '马库斯商铺内部',
    'building_interior',
    '宽敞的商铺内部，货架上摆满了各种商品——从日常用品到冒险装备应有尽有。空气中有淡淡的皮革和香料气味。柜台后是通往仓库的门。',

    '{"x": 3, "y": 1}',
    '[
        {
            "grid_id": "grid_commercial_street_001",
            "direction": "west",
            "description": "西面是商铺门口，通往商业街区",
            "target_name": "商业街区"
        }
    ]',

    '安静整洁，偶尔传来商品摆放的声音',
    'bright',

    '[
        {
            "npc_id": "npc_marcus_001",
            "npc_name": "马库斯",
            "activity": "站在柜台后整理账本，看到你进来会抬起头",
            "position": "柜台后"
        }
    ]',

    '[
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
    ]',

    true,
    '你走进马库斯的商铺。这里比外表看起来更大，商品种类繁多且摆放有序。马库斯显然是个经验丰富的商人。'
);

-- Grid 4: 城门广场
INSERT INTO location_grids (
    id, location_id, grid_name, grid_type, description,
    grid_position, connected_grids,
    atmosphere, lighting,
    npcs_present, interactive_objects,
    is_safe, first_visit_description
) VALUES (
    'grid_town_gate_001',
    'loc_crossroads_town_001',
    '城门广场',
    'town_square',
    '十字路镇的北门广场，厚重的木制大门敞开着。守卫站在门旁警惕地观察进出的人。广场上有几辆准备出发或刚到达的马车。',

    '{"x": 1, "y": 0}',
    '[
        {
            "grid_id": "grid_town_square_001",
            "direction": "south",
            "description": "南面是镇中心广场",
            "target_name": "镇中心广场"
        }
    ]',

    '略显紧张，守卫保持警惕，马车夫忙碌地准备货物',
    'bright',

    '[
        {
            "npc_id": "npc_town_guard_001",
            "npc_name": "镇守卫",
            "activity": "站在城门旁，检查进出人员",
            "position": "城门左侧"
        },
        {
            "npc_id": "npc_caravan_driver_001",
            "npc_name": "商队车夫",
            "activity": "检查马车轮子，准备出发",
            "position": "广场中央"
        }
    ]',

    '[
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
    ]',

    true,
    '你来到城门广场。这里是镇子与外界的连接点，充满了冒险的气息。'
);

-- Grid 5: 酒馆入口
INSERT INTO location_grids (
    id, location_id, grid_name, grid_type, description,
    grid_position, connected_grids,
    atmosphere, lighting,
    npcs_present, interactive_objects,
    is_safe, first_visit_description
) VALUES (
    'grid_tavern_entrance_001',
    'loc_crossroads_town_001',
    '酒馆入口',
    'building_entrance',
    '"跃马酒馆"的入口，挂着一块画着跃起骏马的招牌。门内传来喧闹的说笑声和音乐声，空气中飘出麦芽酒和炖肉的香味。',

    '{"x": 1, "y": 2}',
    '[
        {
            "grid_id": "grid_town_square_001",
            "direction": "north",
            "description": "北面是镇中心广场",
            "target_name": "镇中心广场"
        },
        {
            "grid_id": "grid_tavern_interior_001",
            "direction": "south",
            "description": "推门进入酒馆内部",
            "target_name": "酒馆内部"
        }
    ]',

    '温暖诱人，传来的笑声和音乐让人想要进去休息',
    'bright',

    '[
        {
            "npc_id": "npc_drunk_patron_001",
            "npc_name": "醉酒的客人",
            "activity": "靠在门口墙边，醉醺醺地哼着小调",
            "position": "门口右侧"
        }
    ]',

    '[
        {
            "id": "obj_tavern_sign_001",
            "name": "酒馆招牌",
            "type": "landmark",
            "description": "精美的彩绘招牌，描绘着一匹骏马跃过栅栏",
            "interaction_type": "examine"
        }
    ]',

    true,
    '你来到跃马酒馆门口。这里看起来是镇上最热闹的地方。'
);

-- Grid 6: 酒馆内部（第二个检查点位置）
INSERT INTO location_grids (
    id, location_id, grid_name, grid_type, description,
    grid_position, connected_grids,
    atmosphere, lighting,
    npcs_present, interactive_objects,
    is_safe, first_visit_description
) VALUES (
    'grid_tavern_interior_001',
    'loc_crossroads_town_001',
    '酒馆内部',
    'building_interior',
    '温暖舒适的酒馆大厅，壁炉里火焰跳动。木桌木椅摆放整齐，大部分座位都有客人。吧台后面，酒保忙碌地倒酒。角落里有位吟游诗人正在弹奏竖琴。',

    '{"x": 1, "y": 3}',
    '[
        {
            "grid_id": "grid_tavern_entrance_001",
            "direction": "north",
            "description": "北面是酒馆门口",
            "target_name": "酒馆入口"
        }
    ]',

    '喧闹但友好，充满了冒险者的交谈声和欢笑声',
    'dim',

    '[
        {
            "npc_id": "npc_innkeeper_001",
            "npc_name": "酒馆老板",
            "activity": "在吧台后擦拭酒杯，与客人交谈",
            "position": "吧台后"
        },
        {
            "npc_id": "npc_bard_001",
            "npc_name": "吟游诗人",
            "activity": "坐在角落弹奏竖琴，唱着关于远方冒险的歌谣",
            "position": "角落"
        },
        {
            "npc_id": "npc_veteran_adventurer_001",
            "npc_name": "资深冒险者",
            "activity": "独自坐在靠窗的位置喝酒，似乎在思考什么",
            "position": "窗边桌"
        }
    ]',

    '[
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
    ]',

    true,
    '你推门走进酒馆。温暖的空气和热闹的氛围立刻包围了你。这里是冒险者聚集的地方，空气中弥漫着故事和机会的气息。'
);

-- ========================================
-- 4. 更新任务检查点，添加 grid_id
-- ========================================

UPDATE world_quests
SET checkpoints = jsonb_set(
    jsonb_set(
        checkpoints,
        '{0,grid_id}',
        '"grid_marcus_shop_001"'
    ),
    '{1,grid_id}',
    '"grid_tavern_interior_001"'
)
WHERE id = 'quest_shadow_forest_001';

-- 验证任务更新
SELECT id, quest_name, checkpoints
FROM world_quests
WHERE id = 'quest_shadow_forest_001';

-- ========================================
-- 5. 初始化玩家网格位置
-- ========================================

-- 将所有在十字路镇的玩家初始化到镇中心广场
UPDATE player_world_progress
SET current_grid_id = 'grid_town_square_001'
WHERE current_location_id = 'loc_crossroads_town_001'
  AND current_grid_id IS NULL;

-- ========================================
-- 6. 验证数据
-- ========================================

-- 验证网格已创建
SELECT
    grid_name,
    grid_type,
    jsonb_array_length(connected_grids) as connections,
    jsonb_array_length(npcs_present) as npc_count,
    jsonb_array_length(interactive_objects) as object_count
FROM location_grids
WHERE location_id = 'loc_crossroads_town_001'
ORDER BY grid_position;

-- 验证连接关系
SELECT
    g1.grid_name as from_grid,
    conn->>'direction' as direction,
    conn->>'target_name' as to_grid
FROM location_grids g1,
     jsonb_array_elements(g1.connected_grids) as conn
WHERE g1.location_id = 'loc_crossroads_town_001'
ORDER BY g1.grid_name;

-- ========================================
-- 完成提示
-- ========================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Phase 1 网格地图系统迁移完成！';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE '已创建：';
    RAISE NOTICE '✓ location_grids 表';
    RAISE NOTICE '✓ 6 个网格（十字路镇）';
    RAISE NOTICE '✓ player_world_progress.current_grid_id 列';
    RAISE NOTICE '✓ 更新任务检查点添加 grid_id';
    RAISE NOTICE '';
    RAISE NOTICE '下一步：';
    RAISE NOTICE '1. 更新 game_engine.py 实现网格移动系统';
    RAISE NOTICE '2. 更新 ai_service.py 添加网格数据约束';
    RAISE NOTICE '3. 更新 UI 显示网格信息';
    RAISE NOTICE '';
END $$;
