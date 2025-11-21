-- ========================================
-- V2 补丁：添加 quest_progress 列
-- ========================================
-- 如果你已经运行过 20251120_adventure_system_v2_shared_worlds.sql
-- 但遇到 "column quest_progress does not exist" 错误，
-- 请运行此补丁脚本。

-- 添加 quest_progress 列到 player_world_progress 表
ALTER TABLE player_world_progress
ADD COLUMN IF NOT EXISTS quest_progress JSONB DEFAULT '{}';

COMMENT ON COLUMN player_world_progress.quest_progress IS '任务检查点进度 {quest_id: {checkpoints_completed: [1,2], current_checkpoint: 2}}';

-- 验证列已添加
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'player_world_progress' AND column_name = 'quest_progress';

-- 如果看到 quest_progress 列，说明补丁成功！
