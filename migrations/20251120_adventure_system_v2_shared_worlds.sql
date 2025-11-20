-- ========================================
-- AI 跑团系统 v2 - 共享持久世界架构
-- 设计理念：从私有世界转向共享持久世界
-- 创建时间：2025-11-20
-- ========================================

-- ========================================
-- 1. 世界地点表 (动态扩展)
-- ========================================
CREATE TABLE IF NOT EXISTS world_locations (
    id VARCHAR(36) PRIMARY KEY,
    world_id VARCHAR(36) REFERENCES adventure_worlds(id) ON DELETE CASCADE,

    -- 地点基本信息
    location_name VARCHAR(200) NOT NULL,
    location_type VARCHAR(50), -- town/dungeon/wilderness/landmark
    description TEXT,
    danger_level INT DEFAULT 1 CHECK (danger_level >= 1 AND danger_level <= 10),

    -- 地点状态
    is_discovered BOOLEAN DEFAULT FALSE,
    discovered_by_user_id VARCHAR(50), -- 首次发现者
    discovered_at TIMESTAMP,
    visit_count INT DEFAULT 0,

    -- 关联数据
    connected_locations JSONB, -- 连接的其他地点ID列表
    available_quests JSONB, -- 此地可接取的任务
    resident_npcs JSONB, -- 居住的NPC ID列表

    -- 动态生成标记
    is_ai_generated BOOLEAN DEFAULT FALSE,
    generation_context TEXT, -- AI生成时的上下文

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_locations_world ON world_locations(world_id);
CREATE INDEX idx_locations_type ON world_locations(location_type);
CREATE INDEX idx_locations_discovered ON world_locations(is_discovered);

COMMENT ON TABLE world_locations IS '世界地点表 - 动态扩展的地点系统';
COMMENT ON COLUMN world_locations.visit_count IS '玩家访问次数（所有玩家）';


-- ========================================
-- 2. 世界NPC表 (动态扩展)
-- ========================================
CREATE TABLE IF NOT EXISTS world_npcs (
    id VARCHAR(36) PRIMARY KEY,
    world_id VARCHAR(36) REFERENCES adventure_worlds(id) ON DELETE CASCADE,

    -- NPC基本信息
    npc_name VARCHAR(200) NOT NULL,
    role VARCHAR(100), -- merchant/guard/quest_giver/villain
    personality TEXT,
    description TEXT,

    -- 位置信息
    current_location_id VARCHAR(36) REFERENCES world_locations(id),
    home_location_id VARCHAR(36) REFERENCES world_locations(id),

    -- 状态
    is_alive BOOLEAN DEFAULT TRUE,
    health_status VARCHAR(50) DEFAULT 'healthy', -- healthy/injured/dead
    mood VARCHAR(50) DEFAULT 'neutral', -- friendly/neutral/hostile

    -- 关系数据
    faction_id VARCHAR(36), -- 所属势力
    relationships JSONB, -- 与其他NPC的关系

    -- 互动统计
    interaction_count INT DEFAULT 0,
    last_interaction_at TIMESTAMP,

    -- 动态生成标记
    is_ai_generated BOOLEAN DEFAULT FALSE,
    generation_context TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_npcs_world ON world_npcs(world_id);
CREATE INDEX idx_npcs_location ON world_npcs(current_location_id);
CREATE INDEX idx_npcs_faction ON world_npcs(faction_id);

COMMENT ON TABLE world_npcs IS '世界NPC表 - 动态扩展的NPC系统';


-- ========================================
-- 3. 世界势力表
-- ========================================
CREATE TABLE IF NOT EXISTS world_factions (
    id VARCHAR(36) PRIMARY KEY,
    world_id VARCHAR(36) REFERENCES adventure_worlds(id) ON DELETE CASCADE,

    faction_name VARCHAR(200) NOT NULL,
    faction_type VARCHAR(50), -- guild/kingdom/cult/merchant
    description TEXT,

    -- 势力属性
    power_level INT DEFAULT 50 CHECK (power_level >= 0 AND power_level <= 100),
    reputation INT DEFAULT 50 CHECK (reputation >= 0 AND reputation <= 100),
    resources INT DEFAULT 50 CHECK (resources >= 0 AND resources <= 100),

    -- 关系
    allied_factions JSONB, -- 盟友势力ID列表
    enemy_factions JSONB, -- 敌对势力ID列表
    controlled_locations JSONB, -- 控制的地点ID列表

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_factions_world ON world_factions(world_id);

COMMENT ON TABLE world_factions IS '世界势力表';


-- ========================================
-- 4. 任务定义表 (结构化任务)
-- ========================================
CREATE TABLE IF NOT EXISTS world_quests (
    id VARCHAR(36) PRIMARY KEY,
    world_id VARCHAR(36) REFERENCES adventure_worlds(id) ON DELETE CASCADE,

    quest_name VARCHAR(200) NOT NULL,
    quest_type VARCHAR(50), -- main/side/daily/event
    description TEXT,

    -- 任务结构
    difficulty INT DEFAULT 1 CHECK (difficulty >= 1 AND difficulty <= 10),
    recommended_level INT DEFAULT 1,
    checkpoints JSONB NOT NULL, -- 检查点数组

    -- 任务奖励
    rewards JSONB, -- {exp: 100, gold: 50, items: [...]}

    -- 任务条件
    prerequisites JSONB, -- 前置任务
    location_id VARCHAR(36) REFERENCES world_locations(id), -- 任务发布地点
    quest_giver_npc_id VARCHAR(36) REFERENCES world_npcs(id),

    -- 状态
    is_active BOOLEAN DEFAULT TRUE,
    completion_count INT DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quests_world ON world_quests(world_id);
CREATE INDEX idx_quests_location ON world_quests(location_id);
CREATE INDEX idx_quests_type ON world_quests(quest_type);

COMMENT ON TABLE world_quests IS '任务定义表 - 结构化的任务系统';
COMMENT ON COLUMN world_quests.checkpoints IS 'JSON数组：[{id: 1, desc: "...", location: "...", requires: {...}}]';


-- ========================================
-- 5. 玩家世界进度表
-- ========================================
CREATE TABLE IF NOT EXISTS player_world_progress (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    world_id VARCHAR(36) REFERENCES adventure_worlds(id) ON DELETE CASCADE,

    -- 探索进度
    current_location_id VARCHAR(36) REFERENCES world_locations(id),
    discovered_locations JSONB DEFAULT '[]', -- 已发现地点ID列表
    visited_npcs JSONB DEFAULT '[]', -- 遇到的NPC ID列表

    -- 任务进度
    active_quests JSONB DEFAULT '[]', -- 进行中的任务
    completed_quests JSONB DEFAULT '[]', -- 已完成的任务

    -- 关系网络
    npc_relationships JSONB DEFAULT '{}', -- {npc_id: {reputation: 50, interactions: 5}}
    faction_reputation JSONB DEFAULT '{}', -- {faction_id: reputation_score}

    -- 统计
    total_playtime_minutes INT DEFAULT 0,
    total_actions INT DEFAULT 0,
    exploration_percentage INT DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(user_id, world_id)
);

CREATE INDEX idx_progress_user ON player_world_progress(user_id);
CREATE INDEX idx_progress_world ON player_world_progress(world_id);
CREATE INDEX idx_progress_location ON player_world_progress(current_location_id);

COMMENT ON TABLE player_world_progress IS '玩家世界进度表 - 记录每个玩家在各世界的探索状态';


-- ========================================
-- 6. 玩家行动历史表
-- ========================================
CREATE TABLE IF NOT EXISTS player_action_log (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(36) REFERENCES adventure_runs(id) ON DELETE CASCADE,
    user_id VARCHAR(50) NOT NULL,
    world_id VARCHAR(36) REFERENCES adventure_worlds(id) ON DELETE CASCADE,

    action_type VARCHAR(50), -- move/talk/fight/investigate/use_item
    action_content TEXT,

    -- 上下文
    location_id VARCHAR(36) REFERENCES world_locations(id),
    target_npc_id VARCHAR(36) REFERENCES world_npcs(id),

    -- 结果
    dice_roll INT, -- 骰子结果 (1-20)
    success BOOLEAN,
    outcome TEXT, -- DM的响应

    -- 影响
    world_state_changes JSONB, -- 对世界状态的影响
    reputation_changes JSONB, -- 声望变化

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_action_log_run ON player_action_log(run_id);
CREATE INDEX idx_action_log_user ON player_action_log(user_id);
CREATE INDEX idx_action_log_world ON player_action_log(world_id);
CREATE INDEX idx_action_log_created ON player_action_log(created_at DESC);

COMMENT ON TABLE player_action_log IS '玩家行动历史 - 用于分析和AI上下文';


-- ========================================
-- 7. 世界事件表
-- ========================================
CREATE TABLE IF NOT EXISTS world_events (
    id VARCHAR(36) PRIMARY KEY,
    world_id VARCHAR(36) REFERENCES adventure_worlds(id) ON DELETE CASCADE,

    event_name VARCHAR(200) NOT NULL,
    event_type VARCHAR(50), -- discovery/conflict/celebration/disaster
    description TEXT,

    -- 触发信息
    triggered_by_user_id VARCHAR(50),
    triggered_by_action TEXT,

    -- 影响范围
    affected_locations JSONB,
    affected_npcs JSONB,
    affected_factions JSONB,

    -- 状态
    is_active BOOLEAN DEFAULT TRUE,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_world ON world_events(world_id);
CREATE INDEX idx_events_active ON world_events(is_active);

COMMENT ON TABLE world_events IS '世界事件表 - 玩家行动触发的世界级事件';


-- ========================================
-- 8. 修改现有表
-- ========================================

-- 为 adventure_worlds 添加共享世界标记
ALTER TABLE adventure_worlds ADD COLUMN IF NOT EXISTS is_official_world BOOLEAN DEFAULT FALSE;
ALTER TABLE adventure_worlds ADD COLUMN IF NOT EXISTS world_slug VARCHAR(50) UNIQUE;
ALTER TABLE adventure_worlds ADD COLUMN IF NOT EXISTS player_count INT DEFAULT 0;
ALTER TABLE adventure_worlds ADD COLUMN IF NOT EXISTS total_locations INT DEFAULT 0;
ALTER TABLE adventure_worlds ADD COLUMN IF NOT EXISTS total_npcs INT DEFAULT 0;
ALTER TABLE adventure_worlds ADD COLUMN IF NOT EXISTS total_quests INT DEFAULT 0;

COMMENT ON COLUMN adventure_worlds.is_official_world IS '是否为官方共享世界';
COMMENT ON COLUMN adventure_worlds.player_count IS '当前活跃玩家数';

-- 为 adventure_runs 添加任务和位置信息
ALTER TABLE adventure_runs ADD COLUMN IF NOT EXISTS current_quest_id VARCHAR(36) REFERENCES world_quests(id);
ALTER TABLE adventure_runs ADD COLUMN IF NOT EXISTS current_location_id VARCHAR(36) REFERENCES world_locations(id);
ALTER TABLE adventure_runs ADD COLUMN IF NOT EXISTS quest_progress JSONB DEFAULT '{}';

-- 为 adventure_run_messages 添加骰子结果
ALTER TABLE adventure_run_messages ADD COLUMN IF NOT EXISTS dice_result INT;
ALTER TABLE adventure_run_messages ADD COLUMN IF NOT EXISTS ability_used VARCHAR(50);
ALTER TABLE adventure_run_messages ADD COLUMN IF NOT EXISTS success_level VARCHAR(20); -- critical/success/partial/failure


-- ========================================
-- 9. 自动更新时间戳触发器
-- ========================================

-- 为新表创建更新触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_world_locations_updated_at BEFORE UPDATE ON world_locations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_world_npcs_updated_at BEFORE UPDATE ON world_npcs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_world_factions_updated_at BEFORE UPDATE ON world_factions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_world_quests_updated_at BEFORE UPDATE ON world_quests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_player_world_progress_updated_at BEFORE UPDATE ON player_world_progress
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ========================================
-- 10. 初始化官方世界数据
-- ========================================

-- 创建第一个官方世界：边境之地
INSERT INTO adventure_worlds (id, owner_user_id, template_id, world_name, world_slug, world_description, world_lore, stability, danger, mystery, is_official_world, locations_data, factions_data, npcs_data)
VALUES (
    'official-world-borderlands',
    NULL, -- 官方世界无owner
    (SELECT id FROM adventure_world_templates WHERE slug = 'medieval' LIMIT 1),
    '边境之地',
    'borderlands',
    '一片位于文明与荒野交界的广袤土地，充满机遇与危险。古老的遗迹、神秘的森林、繁华的城镇在此交织。',
    '数百年前，边境之地是古代帝国的边陲要塞。帝国覆灭后，这里成为了冒险者、商人和亡命之徒的乐园。三大势力在此角逐：商会联盟控制贸易，守夜人维持秩序，而暗影教派则在阴影中谋划着不可告人的阴谋。',
    60, -- 相对稳定
    55, -- 中等危险
    70, -- 充满未知
    TRUE,
    '[]'::jsonb,
    '[]'::jsonb,
    '[]'::jsonb
) ON CONFLICT (id) DO NOTHING;

-- 为边境之地创建初始地点
INSERT INTO world_locations (id, world_id, location_name, location_type, description, danger_level, is_discovered, connected_locations)
VALUES
(
    'loc-crossroads-town',
    'official-world-borderlands',
    '十字路镇',
    'town',
    '边境之地最大的贸易城镇，位于三条主要道路的交汇处。镇上有繁忙的市场、温暖的旅馆，以及无数等待被讲述的故事。',
    2,
    TRUE,
    '["loc-whispering-woods", "loc-ancient-ruins"]'::jsonb
),
(
    'loc-whispering-woods',
    'official-world-borderlands',
    '低语森林',
    'wilderness',
    '一片神秘的森林，据说树木会在夜晚窃窃私语。许多冒险者进入后再也没有回来。',
    6,
    FALSE,
    '["loc-crossroads-town"]'::jsonb
),
(
    'loc-ancient-ruins',
    'official-world-borderlands',
    '古代遗迹',
    'dungeon',
    '帝国时代的要塞废墟，据说地下深处隐藏着古代的秘密和宝藏。',
    8,
    FALSE,
    '["loc-crossroads-town"]'::jsonb
) ON CONFLICT (id) DO NOTHING;

-- 创建初始NPC
INSERT INTO world_npcs (id, world_id, npc_name, role, personality, description, current_location_id, mood)
VALUES
(
    'npc-elena-innkeeper',
    'official-world-borderlands',
    '艾莲娜',
    'innkeeper',
    '热情、健谈、消息灵通',
    '十字路镇"旅者之息"旅馆的老板娘，她总能从过往的冒险者那里得知各种传闻和秘密。',
    'loc-crossroads-town',
    'friendly'
),
(
    'npc-marcus-merchant',
    'official-world-borderlands',
    '马库斯',
    'merchant',
    '精明、贪婪但公正',
    '商会联盟的代表，掌握着镇上大部分的贸易。他的货物总是明码标价，从不欺诈——当然，价格也从不便宜。',
    'loc-crossroads-town',
    'neutral'
) ON CONFLICT (id) DO NOTHING;

-- 创建初始势力
INSERT INTO world_factions (id, world_id, faction_name, faction_type, description, power_level, reputation)
VALUES
(
    'faction-merchant-guild',
    'official-world-borderlands',
    '商会联盟',
    'guild',
    '由各地商人组成的松散联盟，控制着边境之地的大部分贸易。他们崇尚利益至上，但也维护基本的商业秩序。',
    70,
    60
),
(
    'faction-night-watch',
    'official-world-borderlands',
    '守夜人',
    'guild',
    '由退伍军人和正义之士组成的组织，致力于维护边境的和平与秩序。',
    50,
    75
),
(
    'faction-shadow-cult',
    'official-world-borderlands',
    '暗影教派',
    'cult',
    '神秘的地下组织，信仰禁忌的黑暗力量。他们的真实目的无人知晓。',
    40,
    20
) ON CONFLICT (id) DO NOTHING;

-- 创建初始任务
INSERT INTO world_quests (id, world_id, quest_name, quest_type, description, difficulty, checkpoints, location_id, quest_giver_npc_id)
VALUES
(
    'quest-missing-merchant',
    'official-world-borderlands',
    '失踪的商队',
    'main',
    '一支前往十字路镇的商队在途中神秘失踪。商会联盟悬赏调查此事。',
    3,
    '[
        {"id": 1, "description": "在十字路镇与马库斯对话，了解商队详情", "location": "loc-crossroads-town", "completed": false},
        {"id": 2, "description": "前往低语森林搜寻线索", "location": "loc-whispering-woods", "completed": false},
        {"id": 3, "description": "调查发现的营地遗址", "requires": {"ability": "knowledge", "dc": 12}, "completed": false},
        {"id": 4, "description": "追踪劫匪并夺回货物", "location": "loc-whispering-woods", "requires": {"ability": "combat", "dc": 14}, "completed": false},
        {"id": 5, "description": "返回镇上向马库斯汇报", "location": "loc-crossroads-town", "completed": false}
    ]'::jsonb,
    'loc-crossroads-town',
    'npc-marcus-merchant'
) ON CONFLICT (id) DO NOTHING;


-- ========================================
-- 完成
-- ========================================
COMMENT ON SCHEMA public IS 'AI 跑团系统 v2 - 共享持久世界架构完成';
