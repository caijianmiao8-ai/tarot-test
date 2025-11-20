-- ========================================
-- 修复现有记录的 current_grid_id
-- ========================================
-- 为已有的 player_world_progress 记录设置 current_grid_id

-- 更新所有在十字路镇但没有网格ID的玩家
UPDATE player_world_progress
SET current_grid_id = 'grid_town_square_001'
WHERE current_location_id = 'loc_crossroads_town_001'
  AND current_grid_id IS NULL;

-- 验证修复结果
SELECT
    user_id,
    current_location_id,
    current_grid_id,
    lg.grid_name
FROM player_world_progress pwp
LEFT JOIN location_grids lg ON pwp.current_grid_id = lg.id
WHERE current_location_id = 'loc_crossroads_town_001';

-- 显示结果
DO $$
DECLARE
    fixed_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO fixed_count
    FROM player_world_progress
    WHERE current_location_id = 'loc_crossroads_town_001'
      AND current_grid_id = 'grid_town_square_001';

    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ 已修复 % 个玩家的网格位置', fixed_count;
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE '现在刷新游戏页面即可看到网格信息！';
END $$;
