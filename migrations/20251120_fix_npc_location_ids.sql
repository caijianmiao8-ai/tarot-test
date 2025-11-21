-- ========================================
-- 修复NPC的location_id不匹配问题
-- ========================================
-- 问题：NPC在world_npcs表中的current_location_id是'loc_crossroads_town_001'
--      但实际location_id是'loc-crossroads-town'
--      导致get_world_context_for_ai查询不到NPC

-- 更新所有十字路镇的NPC到正确的location_id
UPDATE world_npcs
SET current_location_id = 'loc-crossroads-town'
WHERE current_location_id = 'loc_crossroads_town_001';

-- 验证
DO $$
DECLARE
    npc_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO npc_count
    FROM world_npcs
    WHERE current_location_id = 'loc-crossroads-town';

    RAISE NOTICE '✓ 已更新NPC location_id，当前十字路镇NPC数量: %', npc_count;
END $$;
