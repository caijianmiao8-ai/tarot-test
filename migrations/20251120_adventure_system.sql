-- ========================================
-- AI 跑团系统数据表迁移脚本 v1
-- 用途:支持世界生成、角色创建、Run 游玩
-- 执行方式:在 Supabase SQL 编辑器中直接运行
-- 创建时间:2025-11-20
-- ========================================

-- ========================================
-- 1. 世界模板表 (adventure_world_templates)
-- ========================================
CREATE TABLE IF NOT EXISTS adventure_world_templates (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    theme VARCHAR(50),
    default_world_params JSONB,
    prompt_template TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_world_templates_slug
    ON adventure_world_templates(slug);
CREATE INDEX IF NOT EXISTS idx_world_templates_theme
    ON adventure_world_templates(theme);

COMMENT ON TABLE adventure_world_templates IS 'AI 跑团世界模板(预设世界类型)';
COMMENT ON COLUMN adventure_world_templates.slug IS 'URL 友好的唯一标识';
COMMENT ON COLUMN adventure_world_templates.default_world_params IS 'JSONB 格式的默认世界参数(如 stability/danger/mystery 初始值)';
COMMENT ON COLUMN adventure_world_templates.prompt_template IS 'AI 生成世界时的 Prompt 模板';


-- ========================================
-- 2. 世界实例表 (adventure_worlds)
-- ========================================
CREATE TABLE IF NOT EXISTS adventure_worlds (
    id VARCHAR(36) PRIMARY KEY,
    owner_user_id VARCHAR(50),
    template_id INT REFERENCES adventure_world_templates(id) ON DELETE SET NULL,

    -- 世界基本信息
    world_name VARCHAR(200) NOT NULL,
    world_description TEXT,
    world_lore TEXT,

    -- 世界状态指标
    stability INT DEFAULT 50 CHECK (stability >= 0 AND stability <= 100),
    danger INT DEFAULT 50 CHECK (danger >= 0 AND danger <= 100),
    mystery INT DEFAULT 50 CHECK (mystery >= 0 AND mystery <= 100),

    -- 扩展数据(v1 用 JSONB,v2 再拆表)
    locations_data JSONB,
    factions_data JSONB,
    npcs_data JSONB,

    -- 元数据
    total_runs INT DEFAULT 0,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_worlds_owner
    ON adventure_worlds(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_worlds_template
    ON adventure_worlds(template_id);
CREATE INDEX IF NOT EXISTS idx_worlds_created
    ON adventure_worlds(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_worlds_archived
    ON adventure_worlds(is_archived);

COMMENT ON TABLE adventure_worlds IS 'AI 跑团世界实例(玩家生成的世界)';
COMMENT ON COLUMN adventure_worlds.owner_user_id IS '关联 users.id,可为 NULL(支持游客)';
COMMENT ON COLUMN adventure_worlds.stability IS '世界稳定度(0-100)';
COMMENT ON COLUMN adventure_worlds.danger IS '世界危险度(0-100)';
COMMENT ON COLUMN adventure_worlds.mystery IS '世界神秘度(0-100)';
COMMENT ON COLUMN adventure_worlds.locations_data IS 'JSONB 格式的地点列表(v2 可拆表)';
COMMENT ON COLUMN adventure_worlds.factions_data IS 'JSONB 格式的势力列表(v2 可拆表)';
COMMENT ON COLUMN adventure_worlds.npcs_data IS 'JSONB 格式的 NPC 列表(v2 可拆表)';


-- ========================================
-- 3. 玩家角色表 (adventure_characters)
-- ========================================
CREATE TABLE IF NOT EXISTS adventure_characters (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(50),

    -- 角色基本信息
    char_name VARCHAR(100) NOT NULL,
    char_class VARCHAR(50),
    background TEXT,
    personality TEXT,
    appearance TEXT,

    -- 简化能力值(5 个维度,范围 1-10)
    ability_combat INT DEFAULT 5 CHECK (ability_combat >= 1 AND ability_combat <= 10),
    ability_social INT DEFAULT 5 CHECK (ability_social >= 1 AND ability_social <= 10),
    ability_stealth INT DEFAULT 5 CHECK (ability_stealth >= 1 AND ability_stealth <= 10),
    ability_knowledge INT DEFAULT 5 CHECK (ability_knowledge >= 1 AND ability_knowledge <= 10),
    ability_survival INT DEFAULT 5 CHECK (ability_survival >= 1 AND ability_survival <= 10),

    -- 角色状态
    total_runs INT DEFAULT 0,
    is_alive BOOLEAN DEFAULT TRUE,
    death_reason TEXT,

    -- 扩展数据
    equipment_data JSONB,
    relationships_data JSONB,

    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_characters_user
    ON adventure_characters(user_id);
CREATE INDEX IF NOT EXISTS idx_characters_alive
    ON adventure_characters(is_alive);
CREATE INDEX IF NOT EXISTS idx_characters_created
    ON adventure_characters(created_at DESC);

COMMENT ON TABLE adventure_characters IS 'AI 跑团玩家角色(PC,可长期复用)';
COMMENT ON COLUMN adventure_characters.char_name IS '角色名称';
COMMENT ON COLUMN adventure_characters.char_class IS '职业类型(战士/盗贼/学者/谈判家等)';
COMMENT ON COLUMN adventure_characters.ability_combat IS '战斗能力(1-10)';
COMMENT ON COLUMN adventure_characters.ability_social IS '社交/谈判能力(1-10)';
COMMENT ON COLUMN adventure_characters.ability_stealth IS '潜行/敏捷能力(1-10)';
COMMENT ON COLUMN adventure_characters.ability_knowledge IS '知识/智力能力(1-10)';
COMMENT ON COLUMN adventure_characters.ability_survival IS '生存/感知能力(1-10)';
COMMENT ON COLUMN adventure_characters.is_alive IS '角色是否存活';
COMMENT ON COLUMN adventure_characters.death_reason IS '死亡原因(如果已死亡)';


-- ========================================
-- 4. 跑团局表 (adventure_runs)
-- ========================================
CREATE TABLE IF NOT EXISTS adventure_runs (
    id VARCHAR(36) PRIMARY KEY,
    world_id VARCHAR(36) NOT NULL REFERENCES adventure_worlds(id) ON DELETE CASCADE,
    character_id VARCHAR(36) NOT NULL REFERENCES adventure_characters(id) ON DELETE CASCADE,
    user_id VARCHAR(50),

    -- Run 基本信息
    run_title VARCHAR(200),
    run_type VARCHAR(50),
    mission_objective TEXT,

    -- Run 状态
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'failed', 'abandoned')),
    current_turn INT DEFAULT 0,
    max_turns INT DEFAULT 20,

    -- 结算信息
    outcome VARCHAR(20) CHECK (outcome IN ('success', 'failure', 'partial', 'death', NULL)),
    summary TEXT,
    impact_on_world JSONB,
    impact_on_character JSONB,

    -- 时间戳
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,

    -- 扩展
    ai_conversation_id VARCHAR(255),
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_runs_world
    ON adventure_runs(world_id);
CREATE INDEX IF NOT EXISTS idx_runs_character
    ON adventure_runs(character_id);
CREATE INDEX IF NOT EXISTS idx_runs_user
    ON adventure_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_status
    ON adventure_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started
    ON adventure_runs(started_at DESC);

COMMENT ON TABLE adventure_runs IS 'AI 跑团局(一次冒险 = 世界 + 角色 + 任务)';
COMMENT ON COLUMN adventure_runs.run_type IS '任务类型(investigation/exploration/combat/negotiation等)';
COMMENT ON COLUMN adventure_runs.status IS '状态:active(进行中)/completed(已完成)/failed(失败)/abandoned(放弃)';
COMMENT ON COLUMN adventure_runs.current_turn IS '当前回合数';
COMMENT ON COLUMN adventure_runs.max_turns IS '最大回合限制';
COMMENT ON COLUMN adventure_runs.outcome IS '结果:success/failure/partial/death';
COMMENT ON COLUMN adventure_runs.impact_on_world IS 'JSONB 格式:对世界的影响(状态变化/事件等)';
COMMENT ON COLUMN adventure_runs.impact_on_character IS 'JSONB 格式:对角色的影响(能力提升/物品等)';
COMMENT ON COLUMN adventure_runs.ai_conversation_id IS 'Dify/LangChain 等的会话 ID';


-- ========================================
-- 5. Run 对话记录表 (adventure_run_messages)
-- ========================================
CREATE TABLE IF NOT EXISTS adventure_run_messages (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES adventure_runs(id) ON DELETE CASCADE,

    -- 消息内容
    role VARCHAR(20) NOT NULL CHECK (role IN ('dm', 'player')),
    content TEXT NOT NULL,
    turn_number INT,

    -- 元数据
    action_type VARCHAR(50),
    dice_rolls JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_run_messages_run
    ON adventure_run_messages(run_id);
CREATE INDEX IF NOT EXISTS idx_run_messages_created
    ON adventure_run_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_run_messages_turn
    ON adventure_run_messages(run_id, turn_number);

COMMENT ON TABLE adventure_run_messages IS 'AI 跑团 Run 的对话记录';
COMMENT ON COLUMN adventure_run_messages.role IS '角色:dm(AI) 或 player';
COMMENT ON COLUMN adventure_run_messages.turn_number IS '所属回合数';
COMMENT ON COLUMN adventure_run_messages.action_type IS '玩家行动类型(investigate/attack/talk/flee等)';
COMMENT ON COLUMN adventure_run_messages.dice_rolls IS 'JSONB 格式:骰子结果(如果有判定)';


-- ========================================
-- 6. 插入默认世界模板(示例数据)
-- ========================================
INSERT INTO adventure_world_templates (slug, name, description, theme, default_world_params, prompt_template, is_active)
VALUES
    (
        'medieval_village',
        '中世纪边境村庄',
        '一个偏远的中世纪村庄,远离王都,充满未知和危险',
        'medieval',
        '{"stability": 60, "danger": 40, "mystery": 50}'::jsonb,
        '生成一个中世纪背景的边境村庄,包含:村庄名称、主要地点(酒馆/铁匠铺/教堂等)、2-3 个势力(村长派系/教会/商队等)、3-5 个关键 NPC(村长/神父/旅店老板等)',
        TRUE
    ),
    (
        'cyberpunk_district',
        '赛博朋克街区',
        '未来都市的边缘街区,霓虹灯下藏着黑暗交易',
        'cyberpunk',
        '{"stability": 30, "danger": 70, "mystery": 60}'::jsonb,
        '生成一个赛博朋克背景的街区,包含:街区名称、主要地点(夜店/黑市/公司大楼等)、2-3 个势力(公司/帮派/赛博改造诊所等)、3-5 个关键 NPC(帮派头目/黑客/企业特工等)',
        TRUE
    ),
    (
        'fantasy_kingdom',
        '奇幻王都',
        '充满魔法和阴谋的王国首都,权力斗争从未停息',
        'fantasy',
        '{"stability": 50, "danger": 50, "mystery": 70}'::jsonb,
        '生成一个奇幻背景的王都,包含:王都名称、主要地点(王宫/法师塔/市场/冒险者公会等)、2-3 个势力(王室/法师协会/商会等)、3-5 个关键 NPC(国王/大法师/商会会长等)',
        TRUE
    )
ON CONFLICT (slug) DO NOTHING;


-- ========================================
-- 7. 触发器:自动更新 updated_at
-- ========================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为各表添加触发器
DROP TRIGGER IF EXISTS update_world_templates_updated_at ON adventure_world_templates;
CREATE TRIGGER update_world_templates_updated_at
    BEFORE UPDATE ON adventure_world_templates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_worlds_updated_at ON adventure_worlds;
CREATE TRIGGER update_worlds_updated_at
    BEFORE UPDATE ON adventure_worlds
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_characters_updated_at ON adventure_characters;
CREATE TRIGGER update_characters_updated_at
    BEFORE UPDATE ON adventure_characters
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ========================================
-- 8. 验证迁移结果
-- ========================================
DO $$
DECLARE
    table_count INT;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name LIKE 'adventure_%';

    RAISE NOTICE '已创建 % 个 adventure_* 表', table_count;
END $$;

-- 列出所有 adventure_* 表
SELECT table_name,
       (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public'
AND table_name LIKE 'adventure_%'
ORDER BY table_name;

-- ========================================
-- 完成!现在你可以开始开发 AI 跑团系统了
-- ========================================
