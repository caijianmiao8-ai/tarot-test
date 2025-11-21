# 边境之地 TRPG 系统 - 代码审查报告

**审查日期**: 2025-11-21
**审查范围**: world_adventure 蓝图 - 任务进度系统
**严重程度**: 🔴 高 (系统核心功能存在多个致命bug)

---

## 执行摘要

经过全面审查，发现 **7个关键设计问题** 和 **5个致命bug**。核心问题是：**任务进度管理的数据流混乱，导致前后端数据不一致**。

用户报告的问题："进入时，当前第一个任务一直是√" - 这是多个bug叠加的结果。

---

## 🔴 致命Bug列表

### Bug #1: world_id=None 导致任务进度无法加载
**严重程度**: 🔴 致命
**文件**: `game_engine.py:762`
**状态**: ✅ 已修复 (commit 36c65db)

```python
# 错误代码
def get_world_context_for_ai(self, world, progress, run):
    world_id = world.get('id')  # ← 参数名world，但传入的是run_data

# 修复后
world_id = world.get('id') or world.get('world_id')
```

**影响**:
- SQL查询 `WHERE world_id = None` 永远找不到数据
- `checkpoints_completed` 永远是空数组
- 任务进度无法保存或加载

---

### Bug #2: 前端显示错误的任务进度 (用户报告的主要问题)
**严重程度**: 🔴 高
**文件**: `plugin.py:232` + `run_play.html:549`
**状态**: ⚠️ 未修复

**问题分析**:

```python
# plugin.py:232 - 页面加载时
if progress_row and progress_row['quest_progress']:
    quest_progress = progress_row['quest_progress'].get(str(run['current_quest_id']), {})
```

**可能导致错误显示的场景**:

1. **数据库中有脏数据**:
```json
{
  "quest_shadow_forest_001": {
    "checkpoints_completed": [1],  ← 这里有值但实际没完成
    "current_checkpoint": 1
  }
}
```

2. **类型不匹配**:
```python
# 数据库保存时: checkpoints_completed = [1] (整数)
# 前端检查时: checkpoint.id in [1]
# 如果 checkpoint.id 是字符串 "1"，则 "1" in [1] = False
# 如果 checkpoint.id 是整数 1，则 1 in [1] = True
```

3. **migration脚本的问题**:
```sql
-- 20251120_fix_quest_consistency.sql:133
SET quest_progress = jsonb_build_object(
    quest_id_var, jsonb_build_object(
        'checkpoints_completed', '[]'::jsonb,  ← 应该是空数组
        'current_checkpoint', 0
    )
)
WHERE world_id = world_id_var;  ← 但这会覆盖所有玩家的进度！
```

**验证方法**:
```sql
-- 检查数据库中的实际数据
SELECT user_id, world_id, quest_progress
FROM player_world_progress
WHERE world_id = 'official-world-borderlands';
```

---

### Bug #3: quest_progress 可能是 None
**严重程度**: 🟡 中
**文件**: `plugin.py:716`, `plugin.py:829`
**状态**: ⚠️ 部分修复

```python
# 多处代码需要防御性处理
quest_progress = world_context.get('quest_progress') or {}  # ✅ 已修复
quest_progress = world_context.get('quest_progress', {})    # ❌ 如果值是None，仍返回None
```

**问题**: Python的 `dict.get(key, default)` 只在key不存在时返回default，如果key存在但值是None，会返回None。

---

### Bug #4: 检查点ID类型不一致
**严重程度**: 🟡 中
**文件**: 多个文件
**状态**: ⚠️ 未修复

**问题分析**:

```python
# migration中: id是整数
'id', 1,

# 保存时: checkpoint_id 是整数
checkpoint_id = cp['id']  # 1 (int)
quest_progress[quest_id]['checkpoints_completed'].append(checkpoint_id)

# 比较时: 可能类型不匹配
cp.get('id') in completed_ids  # 1 in [1] = True ✅
                                 # "1" in [1] = False ❌
```

---

### Bug #5: 非原子更新导致数据丢失
**严重程度**: 🟡 中
**文件**: `game_engine.py:96-146`
**状态**: ⚠️ 未修复

```python
# 当前实现
def update_quest_progress(user_id, world_id, quest_id, checkpoint_id):
    # 1. 读取整个quest_progress
    result = cur.fetchone()
    quest_progress = result.get('quest_progress', {})

    # 2. 修改内存中的dict
    quest_progress[quest_id]['checkpoints_completed'].append(checkpoint_id)

    # 3. 写回整个quest_progress
    cur.execute("UPDATE ... SET quest_progress = %s", (json.dumps(quest_progress),))
```

**问题**: 如果两个请求同时完成检查点，会出现：
```
时间轴:
T1: 请求A读取 quest_progress = {quest1: {checkpoints_completed: [1]}}
T2: 请求B读取 quest_progress = {quest1: {checkpoints_completed: [1]}}
T3: 请求A添加检查点2，写入 {quest1: {checkpoints_completed: [1, 2]}}
T4: 请求B添加检查点3，写入 {quest1: {checkpoints_completed: [1, 3]}}
结果: 检查点2丢失了！
```

---

## 🟠 设计问题

### 设计问题 #1: 重复的数据存储
**严重程度**: 🟠 中

**问题**:
- `adventure_runs.quest_progress` (JSONB列)
- `player_world_progress.quest_progress` (JSONB列)

两个表都有 `quest_progress` 列，但代码只使用 `player_world_progress.quest_progress`。

**影响**: 数据冗余，可能导致不一致。

---

### 设计问题 #2: 未使用的字段
**严重程度**: 🟡 低

**未使用的字段**:
1. `checkpoint.completed` - migration中定义，代码从不使用
2. `quest_progress[quest_id]['current_checkpoint']` - 保存但从不读取

**代码中实际使用的判断逻辑**:
```python
# 正确的逻辑
checkpoint_id in quest_progress['checkpoints_completed']

# 从未使用的字段
checkpoint.get('completed')  # ← 这个字段没有意义
```

---

### 设计问题 #3: 参数命名混乱
**严重程度**: 🟠 中

```python
def get_world_context_for_ai(self, world, progress, run):
    # 参数名叫 'world'，但实际传入的是 run_data
    # 参数名叫 'run'，但实际也传入 run_data
```

**影响**: 导致了Bug #1 (world_id=None)

---

### 设计问题 #4: 缺少数据验证
**严重程度**: 🟠 中

**缺少的验证**:
1. checkpoint_id 类型验证 (int vs str)
2. quest_id 存在性验证
3. user_id/world_id 非空验证

---

### 设计问题 #5: migration覆盖所有玩家数据
**严重程度**: 🔴 高

```sql
-- 20251120_fix_quest_consistency.sql:139
UPDATE player_world_progress
SET quest_progress = jsonb_build_object(...)  -- 覆盖整个对象
WHERE world_id = world_id_var;  -- 影响所有玩家
```

**问题**:
- 如果玩家正在进行多个任务，这会清空所有任务进度
- 应该使用 `jsonb_set()` 只更新特定任务

---

### 设计问题 #6: 前端状态更新不完整
**严重程度**: 🟡 中

**当前实现**:
```javascript
// run_play.html:765-768
if (result.current_quest) {
    updateQuestProgress(result.current_quest);
}
```

**问题**: 只有在API返回 `current_quest` 时才更新，页面加载时不会触发。

---

### 设计问题 #7: 调试困难
**严重程度**: 🟡 中

**问题**: 需要添加大量日志才能诊断问题，说明核心逻辑本身不够清晰。

---

## 📊 数据流分析

### 当前数据流 (有问题)

```
1. 页面加载 (plugin.py:192-290)
   ↓
   SELECT quest_progress FROM player_world_progress
   ↓
   传递给模板: quest_progress = {"quest_shadow_forest_001": {"checkpoints_completed": [?], ...}}
   ↓
2. 模板渲染 (run_play.html:549)
   ↓
   {% if checkpoint.id in quest_progress.get('checkpoints_completed', []) %}
   ↓
   显示 ✅ 或 ⭕
   ↓
3. 用户行动 (plugin.py:712-759)
   ↓
   检测检查点完成
   ↓
   update_quest_progress() ← 可能因为world_id=None而失败
   ↓
4. API返回 (plugin.py:854-875)
   ↓
   current_quest: {completed_checkpoint_ids: [...]}
   ↓
5. 前端更新 (run_play.html:940-962)
   ↓
   updateQuestProgress() 动态更新显示
```

### 问题点

1. **步骤1**: 如果数据库中有脏数据（checkpoints_completed包含不该有的ID），会错误显示
2. **步骤3**: 之前world_id=None导致无法保存（已修复）
3. **步骤1和步骤5**: 两个不同的数据来源，可能不一致

---

## 🔧 建议的修复方案

### 立即修复 (P0 - 致命)

#### 修复1: 验证并清理数据库脏数据

```sql
-- 检查是否有错误的进度数据
SELECT
    user_id,
    world_id,
    quest_progress
FROM player_world_progress
WHERE world_id = 'official-world-borderlands'
AND quest_progress IS NOT NULL;

-- 如果发现有错误数据，重置特定用户的进度
UPDATE player_world_progress
SET quest_progress = jsonb_set(
    COALESCE(quest_progress, '{}'::jsonb),
    ARRAY['quest_shadow_forest_001'],
    '{"checkpoints_completed": [], "current_checkpoint": 0}'::jsonb
)
WHERE user_id = 'e66e7e67-7fbe-421a-8a93-29ea3aacbabe'
AND world_id = 'official-world-borderlands';
```

#### 修复2: 添加类型标准化

```python
# game_engine.py:96
@staticmethod
def update_quest_progress(user_id, world_id, quest_id, checkpoint_id):
    # 标准化ID类型为整数
    checkpoint_id = int(checkpoint_id) if not isinstance(checkpoint_id, int) else checkpoint_id

    # ... 其余代码
```

#### 修复3: 添加数据验证日志

```python
# plugin.py:232
if progress_row and progress_row['quest_progress']:
    raw_progress = progress_row['quest_progress']
    quest_progress = raw_progress.get(str(run['current_quest_id']), {})

    # 添加验证日志
    logger.info(f"[页面加载] quest_progress: {quest_progress}")
    logger.info(f"[页面加载] checkpoints_completed: {quest_progress.get('checkpoints_completed', [])}")
```

---

### 中期重构 (P1 - 高)

#### 重构1: 统一任务进度管理器

```python
class QuestProgressManager:
    """统一的任务进度管理器"""

    @staticmethod
    def load_progress(user_id: str, world_id: str, quest_id: str) -> dict:
        """统一加载任务进度"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT quest_progress
                    FROM player_world_progress
                    WHERE user_id = %s AND world_id = %s
                """, (user_id, world_id))

                result = cur.fetchone()
                if not result or not result['quest_progress']:
                    return {'checkpoints_completed': [], 'current_checkpoint': 0}

                return result['quest_progress'].get(quest_id, {
                    'checkpoints_completed': [],
                    'current_checkpoint': 0
                })

    @staticmethod
    def save_checkpoint(user_id: str, world_id: str, quest_id: str, checkpoint_id: int) -> bool:
        """原子地保存检查点"""
        # 标准化ID类型
        checkpoint_id = int(checkpoint_id)

        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                # 使用PostgreSQL的原子操作
                cur.execute("""
                    UPDATE player_world_progress
                    SET quest_progress = jsonb_set(
                        jsonb_set(
                            COALESCE(quest_progress, '{}'::jsonb),
                            ARRAY[%s],
                            COALESCE(
                                quest_progress -> %s,
                                '{"checkpoints_completed": [], "current_checkpoint": 0}'::jsonb
                            )
                        ),
                        ARRAY[%s, 'checkpoints_completed'],
                        (
                            COALESCE(
                                quest_progress -> %s -> 'checkpoints_completed',
                                '[]'::jsonb
                            )::jsonb || %s::jsonb
                        )
                    )
                    WHERE user_id = %s
                    AND world_id = %s
                    AND NOT (quest_progress -> %s -> 'checkpoints_completed' @> %s::jsonb)
                    RETURNING quest_progress -> %s
                """, (
                    quest_id, quest_id,  # 初始化quest对象
                    quest_id,  # 设置路径
                    quest_id,  # 获取现有数组
                    json.dumps([checkpoint_id]),  # 追加新ID
                    user_id, world_id,  # WHERE条件
                    quest_id, json.dumps([checkpoint_id]),  # 防止重复
                    quest_id  # RETURNING
                ))

                conn.commit()
                return cur.rowcount > 0
```

#### 重构2: 类型安全的比较

```python
# 在所有比较之前标准化类型
def normalize_checkpoint_id(checkpoint_id):
    """标准化检查点ID为整数"""
    if isinstance(checkpoint_id, str):
        try:
            return int(checkpoint_id)
        except ValueError:
            return checkpoint_id
    return checkpoint_id

# 使用时
checkpoint_id = normalize_checkpoint_id(cp.get('id'))
completed_ids = [normalize_checkpoint_id(x) for x in quest_progress.get('checkpoints_completed', [])]
```

---

### 长期优化 (P2 - 中)

1. **删除未使用的字段**: `checkpoint.completed`, `quest_progress.current_checkpoint`
2. **统一数据存储**: 只保留 `player_world_progress.quest_progress`
3. **添加数据库约束**: CHECK约束确保数据有效性
4. **前端状态管理**: 使用Vue/React管理任务进度状态

---

## 🎯 优先级建议

### 立即执行 (今天)
1. ✅ 修复world_id=None (已完成)
2. ⚠️ 验证并清理数据库中的脏数据
3. ⚠️ 添加类型标准化代码

### 本周完成
4. 重构为统一的QuestProgressManager
5. 实现原子更新操作
6. 添加完整的单元测试

### 下个迭代
7. 删除未使用字段
8. 优化前端状态管理
9. 性能优化

---

## 📝 测试检查清单

### 功能测试

- [ ] 新角色首次进入世界，检查点应全部显示 ⭕
- [ ] 完成第一个检查点后，应显示 ✅，其他显示 ⭕
- [ ] 刷新页面，检查点状态应保持正确
- [ ] 切换角色后再回来，检查点状态应保持正确
- [ ] 同时完成多个检查点（快速点击），都应正确保存

### 边界测试

- [ ] world_id 为 None 时应有错误提示
- [ ] quest_id 不存在时应有默认值
- [ ] checkpoint_id 类型不一致时应自动转换
- [ ] 数据库连接失败时应有优雅降级

---

## 📞 总结

**当前状态**: 🔴 不可用于生产环境

**核心问题**:
1. ✅ world_id=None导致数据无法加载（已修复）
2. ⚠️ 数据库中可能存在脏数据导致显示错误
3. ⚠️ 缺少类型标准化和数据验证
4. ⚠️ 非原子更新可能导致数据丢失

**建议**:
1. 立即执行P0修复（验证数据库、添加类型标准化）
2. 本周完成重构为QuestProgressManager
3. 添加完整的测试覆盖

**预计修复时间**:
- P0修复: 2-4小时
- P1重构: 1-2天
- P2优化: 1周

---

## 附录A: 相关文件清单

### 核心文件
- `blueprints/games/world_adventure/plugin.py` (1200+ lines)
- `blueprints/games/world_adventure/game_engine.py` (1100+ lines)
- `blueprints/games/world_adventure/templates/games/world_adventure/run_play.html` (1000+ lines)

### Migration文件
- `migrations/20251120_adventure_system_v2_shared_worlds.sql`
- `migrations/20251120_fix_quest_consistency.sql`
- `migrations/20251120_v2_add_quest_progress_column.sql`

### 需要修改的函数
- `QuestEngine.update_quest_progress()` (game_engine.py:96-146)
- `QuestEngine.get_world_context_for_ai()` (game_engine.py:758-870)
- `run_play_page()` (plugin.py:192-300)
- `api_run_action()` (plugin.py:600-880)

---

**报告结束**
