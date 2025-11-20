-- ========================================
-- Phase 1: 网格地图系统迁移（最终修复版）
-- ========================================
-- 兼容实际的数据库 schema

-- ========================================
-- 1. 创建 location_grids 表
-- ========================================

CREATE TABLE IF NOT EXISTS location_grids (
    id VARCHAR(36) PRIMARY KEY,
    location_id VARCHAR(36) REFERENCES world_locations(id) ON DELETE CASCADE,
    grid_name VARCHAR(100) NOT NULL,
    grid_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,

    -- 空间结构
    grid_position JSONB DEFAULT '{"x": 0, "y": 0}',
    connected_grids JSONB DEFAULT '[]',

    -- 环境元素
    atmosphere TEXT,
    lighting VARCHAR(50) DEFAULT 'bright',

    -- NPC 存在
    npcs_present JSONB DEFAULT '[]',

    -- 可交互物体
    interactive_objects JSONB DEFAULT '[]',

    -- 元数据
    is_safe BOOLEAN DEFAULT true,
    first_visit_description TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_location_grids_location ON location_grids(location_id);

-- ========================================
-- 2. 修改 player_world_progress 表
-- ========================================

ALTER TABLE player_world_progress
ADD COLUMN IF NOT EXISTS current_grid_id VARCHAR(36) REFERENCES location_grids(id);

CREATE INDEX IF NOT EXISTS idx_player_world_progress_grid ON player_world_progress(current_grid_id);

-- ========================================
-- 3. 创建必要的地点和NPC
-- ========================================

-- 检查并创建十字路镇地点
INSERT INTO world_locations (
    id, world_id, location_name, location_type, description,
    danger_level, is_discovered, visit_count
)
SELECT
    'loc_crossroads_town_001',
    w.id,
    '十字路镇',
    'town',
    '一座繁荣的边境小镇，位于几条主要商道的交汇处。镇子不大但五脏俱全，有市场、酒馆、商铺和守卫。这里是冒险者的集散地，也是通往暗影之森的最后一个安全据点。',
    3,
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 创建关键NPC（使用实际存在的列）
-- 马库斯
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_marcus_001',
    w.id,
    'loc_crossroads_town_001',
    '马库斯',
    '商队主人',
    '精明而谨慎的商人，对暗影之森的异常情况很担忧。他的商队最近在暗影之森边缘失踪，他怀疑不是普通的盗匪所为。',
    '中年商人，穿着考究的商人服装，眼神精明但透着担忧',
    'worried',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 酒馆老板
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_innkeeper_001',
    w.id,
    'loc_crossroads_town_001',
    '老板娘艾琳',
    '酒馆老板',
    '热情健谈，消息灵通，对镇上的八卦了如指掌。她知道很多关于暗影之森的传说和近期失踪事件。',
    '中年妇女，总是面带微笑，手脚麻利地照顾客人',
    'friendly',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 吟游诗人
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_bard_001',
    w.id,
    'loc_crossroads_town_001',
    '吟游诗人莱昂',
    '吟游诗人',
    '神秘浪漫，总是用诗歌和歌谣讲述故事。他曾经去过暗影之森深处，见到过一些不寻常的东西。',
    '年轻的精灵吟游诗人，手持精美的竖琴，眼神深邃',
    'neutral',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 资深冒险者
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_veteran_adventurer_001',
    w.id,
    'loc_crossroads_town_001',
    '退役战士格伦',
    '资深冒险者',
    '沉默寡言但经验丰富，见过很多危险。他曾是一支探险队的幸存者，其他队友都在森林中遇难。',
    '满脸伤疤的老战士，身穿破旧的皮甲，眼神警惕',
    'serious',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 镇守卫
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_town_guard_001',
    w.id,
    'loc_crossroads_town_001',
    '守卫队长托马斯',
    '镇守卫',
    '尽职尽责，对镇子的安全非常上心。他担心森林里的威胁可能会蔓延到镇子。',
    '身穿制服的守卫队长，手持长矛，站姿笔直',
    'neutral',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 商队车夫
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_caravan_driver_001',
    w.id,
    'loc_crossroads_town_001',
    '车夫约翰',
    '商队车夫',
    '粗犷豪爽，见多识广的老司机。他听说过很多关于森林的恐怖故事。',
    '魁梧的中年男子，皮肤晒得黝黑，声音洪亮',
    'neutral',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 镇务传令官
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_town_crier_001',
    w.id,
    'loc_crossroads_town_001',
    '传令官威廉',
    '镇务传令官',
    '声音洪亮，喜欢宣布各种消息。他每天都会公布镇上的新闻和悬赏。',
    '穿着镇务官制服的年轻人，手持铜铃',
    'friendly',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 水果小贩
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_fruit_vendor_001',
    w.id,
    'loc_crossroads_town_001',
    '小贩莉莉',
    '水果小贩',
    '勤劳朴实的小商贩。她的生意最近不太好，因为商队减少了。',
    '朴素的村妇打扮，摊位上摆着新鲜水果',
    'friendly',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 街头少年
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_street_kid_001',
    w.id,
    'loc_crossroads_town_001',
    '街头少年汤姆',
    '街头少年',
    '机灵鬼怪，对镇上的事情一清二楚。他经常偷听大人们的对话，知道很多小道消息。',
    '衣着破旧的少年，眼神机灵，动作敏捷',
    'curious',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- 醉酒的客人
INSERT INTO world_npcs (
    id, world_id, current_location_id, npc_name, role, personality,
    description, mood, is_alive, interaction_count
)
SELECT
    'npc_drunk_patron_001',
    w.id,
    'loc_crossroads_town_001',
    '醉汉老杰克',
    '醉酒的客人',
    '整天醉醺醺，但有时会说出意外的真话。他声称在醉酒时见过森林里的幽灵。',
    '衣衫不整的老酒鬼，脸色通红，走路摇晃',
    'neutral',
    true,
    0
FROM adventure_worlds w
WHERE w.world_name = '边境之地'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

-- ========================================
-- 4. 插入十字路镇的 6 个网格
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
        {"grid_id": "grid_town_gate_001", "direction": "north", "description": "北面是城门广场，通往城外", "target_name": "城门广场"},
        {"grid_id": "grid_commercial_street_001", "direction": "east", "description": "东面是商业街区，能看到马库斯的商铺招牌", "target_name": "商业街区"},
        {"grid_id": "grid_tavern_entrance_001", "direction": "south", "description": "南面是酒馆入口，传来欢声笑语", "target_name": "酒馆入口"}
    ]',

    '热闹繁忙，商贩叫卖声此起彼伏，偶尔传来马车驶过的声音',
    'bright',

    '[
        {"npc_id": "npc_town_crier_001", "npc_name": "传令官威廉", "activity": "站在喷泉旁大声宣读最新的镇务公告", "position": "喷泉旁"},
        {"npc_id": "npc_fruit_vendor_001", "npc_name": "小贩莉莉", "activity": "在摊位前整理新鲜水果", "position": "广场西侧"}
    ]',

    '[
        {"id": "obj_fountain_001", "name": "古老喷泉", "type": "landmark", "description": "一座有百年历史的石制喷泉，雕刻着守护镇子的狮子形象", "interaction_type": "examine"},
        {"id": "obj_notice_board_001", "name": "公告板", "type": "information", "description": "木制公告板上贴满了悬赏令和招工启事", "interaction_type": "read"}
    ]',

    true,
    '你第一次来到十字路镇的中心广场。这里比你想象的更加繁荣，各种族的冒险者和商人在此交流。空气中弥漫着烤面包和香料的气味。'
)
ON CONFLICT (id) DO NOTHING;

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
        {"grid_id": "grid_town_square_001", "direction": "west", "description": "西面是镇中心广场", "target_name": "镇中心广场"},
        {"grid_id": "grid_marcus_shop_001", "direction": "east", "description": "东面是马库斯商铺的入口", "target_name": "马库斯商铺"}
    ]',

    '商业气息浓厚，偶尔有马车运送货物经过',
    'bright',

    '[
        {"npc_id": "npc_marcus_001", "npc_name": "马库斯", "activity": "站在商铺门口，正与一位顾客道别", "position": "商铺门口"},
        {"npc_id": "npc_street_kid_001", "npc_name": "街头少年汤姆", "activity": "蹲在街角观察过往行人", "position": "街道南侧"}
    ]',

    '[
        {"id": "obj_marcus_sign_001", "name": "马库斯商铺招牌", "type": "landmark", "description": "精心绘制的木制招牌，上面画着满载货物的马车", "interaction_type": "examine"},
        {"id": "obj_cargo_crates_001", "name": "货物箱", "type": "container", "description": "堆放在商铺门口的几个木箱，看起来是新到的货物", "interaction_type": "examine"}
    ]',

    true,
    '你来到商业街区。马库斯的商铺在这里格外显眼，看起来生意兴隆。'
)
ON CONFLICT (id) DO NOTHING;

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
        {"grid_id": "grid_commercial_street_001", "direction": "west", "description": "西面是商铺门口，通往商业街区", "target_name": "商业街区"}
    ]',

    '安静整洁，偶尔传来商品摆放的声音',
    'bright',

    '[
        {"npc_id": "npc_marcus_001", "npc_name": "马库斯", "activity": "站在柜台后整理账本，看到你进来会抬起头", "position": "柜台后"}
    ]',

    '[
        {"id": "obj_shop_counter_001", "name": "商铺柜台", "type": "furniture", "description": "精心打磨的木制柜台，上面摆放着账本和货币箱", "interaction_type": "examine"},
        {"id": "obj_weapon_rack_001", "name": "武器架", "type": "display", "description": "靠墙的武器架上挂着各式武器，都保养得很好", "interaction_type": "examine"},
        {"id": "obj_map_table_001", "name": "地图桌", "type": "information", "description": "角落的桌子上展开着一张区域地图，上面标注着商队路线", "interaction_type": "examine"}
    ]',

    true,
    '你走进马库斯的商铺。这里比外表看起来更大，商品种类繁多且摆放有序。马库斯显然是个经验丰富的商人。'
)
ON CONFLICT (id) DO NOTHING;

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
        {"grid_id": "grid_town_square_001", "direction": "south", "description": "南面是镇中心广场", "target_name": "镇中心广场"}
    ]',

    '略显紧张，守卫保持警惕，马车夫忙碌地准备货物',
    'bright',

    '[
        {"npc_id": "npc_town_guard_001", "npc_name": "守卫队长托马斯", "activity": "站在城门旁，检查进出人员", "position": "城门左侧"},
        {"npc_id": "npc_caravan_driver_001", "npc_name": "车夫约翰", "activity": "检查马车轮子，准备出发", "position": "广场中央"}
    ]',

    '[
        {"id": "obj_town_gate_001", "name": "镇子大门", "type": "landmark", "description": "坚固的木制大门，上面刻着十字路镇的徽记", "interaction_type": "examine"},
        {"id": "obj_merchant_cart_001", "name": "商队马车", "type": "vehicle", "description": "一辆装满货物的马车，看起来即将出发", "interaction_type": "examine"}
    ]',

    true,
    '你来到城门广场。这里是镇子与外界的连接点，充满了冒险的气息。'
)
ON CONFLICT (id) DO NOTHING;

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
        {"grid_id": "grid_town_square_001", "direction": "north", "description": "北面是镇中心广场", "target_name": "镇中心广场"},
        {"grid_id": "grid_tavern_interior_001", "direction": "south", "description": "推门进入酒馆内部", "target_name": "酒馆内部"}
    ]',

    '温暖诱人，传来的笑声和音乐让人想要进去休息',
    'bright',

    '[
        {"npc_id": "npc_drunk_patron_001", "npc_name": "醉汉老杰克", "activity": "靠在门口墙边，醉醺醺地哼着小调", "position": "门口右侧"}
    ]',

    '[
        {"id": "obj_tavern_sign_001", "name": "酒馆招牌", "type": "landmark", "description": "精美的彩绘招牌，描绘着一匹骏马跃过栅栏", "interaction_type": "examine"}
    ]',

    true,
    '你来到跃马酒馆门口。这里看起来是镇上最热闹的地方。'
)
ON CONFLICT (id) DO NOTHING;

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
        {"grid_id": "grid_tavern_entrance_001", "direction": "north", "description": "北面是酒馆门口", "target_name": "酒馆入口"}
    ]',

    '喧闹但友好，充满了冒险者的交谈声和欢笑声',
    'dim',

    '[
        {"npc_id": "npc_innkeeper_001", "npc_name": "老板娘艾琳", "activity": "在吧台后擦拭酒杯，与客人交谈", "position": "吧台后"},
        {"npc_id": "npc_bard_001", "npc_name": "吟游诗人莱昂", "activity": "坐在角落弹奏竖琴，唱着关于远方冒险的歌谣", "position": "角落"},
        {"npc_id": "npc_veteran_adventurer_001", "npc_name": "退役战士格伦", "activity": "独自坐在靠窗的位置喝酒，似乎在思考什么", "position": "窗边桌"}
    ]',

    '[
        {"id": "obj_fireplace_001", "name": "壁炉", "type": "landmark", "description": "温暖的壁炉，火焰舞动着橙色的光芒", "interaction_type": "examine"},
        {"id": "obj_quest_board_001", "name": "任务板", "type": "information", "description": "墙上的木板，钉着几张委托书和悬赏令", "interaction_type": "read"},
        {"id": "obj_bar_counter_001", "name": "吧台", "type": "furniture", "description": "长长的木制吧台，摆满了各种酒瓶", "interaction_type": "examine"}
    ]',

    true,
    '你推门走进酒馆。温暖的空气和热闹的氛围立刻包围了你。这里是冒险者聚集的地方，空气中弥漫着故事和机会的气息。'
)
ON CONFLICT (id) DO NOTHING;

-- ========================================
-- 5. 更新任务检查点，添加 grid_id
-- ========================================

DO $$
DECLARE
    quest_id_var VARCHAR(36);
BEGIN
    SELECT id INTO quest_id_var
    FROM world_quests
    WHERE quest_name = '森林深处的呼唤'
    LIMIT 1;

    IF quest_id_var IS NOT NULL THEN
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
        WHERE id = quest_id_var;

        RAISE NOTICE '✓ 已更新任务检查点，添加 grid_id';
    ELSE
        RAISE NOTICE '⚠ 未找到任务"森林深处的呼唤"，跳过检查点更新';
    END IF;
END $$;

-- ========================================
-- 6. 初始化玩家网格位置
-- ========================================

UPDATE player_world_progress
SET current_grid_id = 'grid_town_square_001'
WHERE current_location_id = 'loc_crossroads_town_001'
  AND current_grid_id IS NULL;

-- ========================================
-- 7. 验证和总结
-- ========================================

DO $$
DECLARE
    grid_count INTEGER;
    npc_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO grid_count FROM location_grids WHERE location_id = 'loc_crossroads_town_001';
    SELECT COUNT(*) INTO npc_count FROM world_npcs WHERE current_location_id = 'loc_crossroads_town_001';

    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Phase 1 网格地图系统迁移完成！';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE '已创建：';
    RAISE NOTICE '  ✓ location_grids 表';
    RAISE NOTICE '  ✓ % 个网格（十字路镇）', grid_count;
    RAISE NOTICE '  ✓ % 个NPC', npc_count;
    RAISE NOTICE '  ✓ player_world_progress.current_grid_id 列';
    RAISE NOTICE '  ✓ 已更新任务检查点';
    RAISE NOTICE '';
    RAISE NOTICE '🎮 测试步骤：';
    RAISE NOTICE '  1. 刷新游戏页面';
    RAISE NOTICE '  2. 输入：我走向商业街区';
    RAISE NOTICE '  3. 输入：我走进马库斯的商铺，询问商队的情况';
    RAISE NOTICE '  4. 观察检查点是否完成';
    RAISE NOTICE '';
END $$;
