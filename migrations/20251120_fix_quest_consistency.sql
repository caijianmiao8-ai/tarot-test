-- ========================================
-- 修复任务内容一致性问题
-- ========================================
-- 问题：AI提到"失踪的商队"、"守夜人哨所"等不存在或不匹配的内容
-- 原因：任务description与实际网格系统设计不匹配
-- 解决：创建与网格系统完全匹配的任务

DO $$
DECLARE
    world_id_var VARCHAR(36);
    quest_id_var VARCHAR(36) := 'quest_shadow_forest_001';
    marcus_npc_id VARCHAR(36);
    eileen_npc_id VARCHAR(36);
BEGIN
    -- 获取世界ID
    SELECT id INTO world_id_var
    FROM adventure_worlds
    WHERE world_name = '边境之地'
    LIMIT 1;

    -- 获取NPC ID
    SELECT id INTO marcus_npc_id
    FROM world_npcs
    WHERE npc_name = '马库斯'
    AND current_location_id IN ('loc-crossroads-town', 'loc_crossroads_town_001')
    LIMIT 1;

    SELECT id INTO eileen_npc_id
    FROM world_npcs
    WHERE npc_name = '艾琳'
    AND current_location_id IN ('loc-crossroads-town', 'loc_crossroads_town_001')
    LIMIT 1;

    -- 删除旧任务（如果存在）
    DELETE FROM world_quests WHERE id = quest_id_var;

    -- 创建新任务：与网格系统完全匹配
    INSERT INTO world_quests (
        id, world_id, quest_name, quest_type, description,
        difficulty, checkpoints, location_id, quest_giver_npc_id
    ) VALUES (
        quest_id_var,
        world_id_var,
        '森林深处的呼唤',
        'main',
        '马库斯的表弟在暗影森林深处失踪已有数日。他最后的信件提到发现了一处古老遗迹，但此后便杳无音信。',
        5,
        jsonb_build_array(
            jsonb_build_object(
                'id', 1,
                'description', '在商业街的马库斯商铺与马库斯对话，了解失踪者的情况',
                'location', 'loc-crossroads-town',
                'grid_id', 'grid_marcus_shop_001',
                'action_type', 'dialogue',
                'target_npc', '马库斯',
                'completed', false
            ),
            jsonb_build_object(
                'id', 2,
                'description', '前往十字路镇酒馆，向老板娘艾琳打听暗影森林的情报',
                'location', 'loc-crossroads-town',
                'grid_id', 'grid_tavern_interior_001',
                'action_type', 'dialogue',
                'target_npc', '艾琳',
                'completed', false
            ),
            jsonb_build_object(
                'id', 3,
                'description', '前往镇外的暗影森林入口，开始搜寻',
                'location', 'loc-shadow-forest-entrance',
                'grid_id', 'grid_forest_entrance_001',
                'action_type', 'explore',
                'completed', false
            )
        ),
        'loc-crossroads-town',
        marcus_npc_id
    );

    RAISE NOTICE '✓ 已创建新任务"森林深处的呼唤"（ID: %）', quest_id_var;

    -- 更新所有现有的Run，将旧任务替换为新任务
    UPDATE adventure_runs
    SET current_quest_id = quest_id_var
    WHERE current_quest_id = 'quest-missing-merchant'
      AND world_id = world_id_var;

    RAISE NOTICE '✓ 已更新所有Run的任务关联';

    -- 清空所有玩家的任务进度（因为任务内容变了）
    UPDATE player_world_progress
    SET quest_progress = jsonb_build_object(
        quest_id_var, jsonb_build_object(
            'checkpoints_completed', '[]'::jsonb,
            'current_checkpoint', 0
        )
    )
    WHERE world_id = world_id_var;

    RAISE NOTICE '✓ 已重置玩家任务进度';

END $$;
