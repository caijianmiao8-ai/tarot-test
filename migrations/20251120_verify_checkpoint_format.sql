-- ========================================
-- 验证检查点数据格式
-- ========================================
-- 目的：检查当前数据库中的检查点是否包含必需的 grid_id, action_type, target_npc 字段

DO $$
DECLARE
    quest_rec RECORD;
    checkpoint_json jsonb;
    cp RECORD;
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE '检查点格式验证';
    RAISE NOTICE '========================================';

    -- 查询所有任务的检查点
    FOR quest_rec IN
        SELECT id, quest_name, checkpoints
        FROM world_quests
        WHERE world_id IN (SELECT id FROM adventure_worlds WHERE world_name = '边境之地')
    LOOP
        RAISE NOTICE '';
        RAISE NOTICE '任务: % (ID: %)', quest_rec.quest_name, quest_rec.id;
        RAISE NOTICE '----------------------------------------';

        -- 遍历检查点数组
        FOR cp IN SELECT * FROM jsonb_array_elements(quest_rec.checkpoints)
        LOOP
            checkpoint_json := cp.value;

            RAISE NOTICE '检查点 %: %',
                checkpoint_json->>'id',
                checkpoint_json->>'description';

            -- 检查必需字段
            IF checkpoint_json ? 'grid_id' THEN
                RAISE NOTICE '  ✓ grid_id: %', checkpoint_json->>'grid_id';
            ELSE
                RAISE NOTICE '  ✗ 缺少 grid_id';
            END IF;

            IF checkpoint_json ? 'action_type' THEN
                RAISE NOTICE '  ✓ action_type: %', checkpoint_json->>'action_type';
            ELSE
                RAISE NOTICE '  ✗ 缺少 action_type';
            END IF;

            IF checkpoint_json ? 'target_npc' THEN
                RAISE NOTICE '  ✓ target_npc: %', checkpoint_json->>'target_npc';
            ELSE
                RAISE NOTICE '  - 无 target_npc (可选)';
            END IF;

            -- 检查旧字段
            IF checkpoint_json ? 'location' THEN
                RAISE NOTICE '  ! 包含旧字段 location: %', checkpoint_json->>'location';
            END IF;

            RAISE NOTICE '';
        END LOOP;
    END LOOP;

    RAISE NOTICE '========================================';
    RAISE NOTICE '验证完成';
    RAISE NOTICE '========================================';
END $$;
