"""
AI 世界冒险游戏 - 数据访问层 (DAO)
遵循项目现有的 DAO 设计模式
"""
from database import DatabaseManager
import uuid
from datetime import datetime


class AdventureWorldTemplateDAO:
    """世界模板数据访问"""

    @staticmethod
    def get_all_active():
        """获取所有激活的世界模板"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM adventure_world_templates
                    WHERE is_active = TRUE
                    ORDER BY id
                """)
                return cur.fetchall()

    @staticmethod
    def get_by_id(template_id):
        """根据 ID 获取模板"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM adventure_world_templates
                    WHERE id = %s
                """, (template_id,))
                return cur.fetchone()


class AdventureWorldDAO:
    """世界实例数据访问"""

    @staticmethod
    def create(world_data):
        """创建世界"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO adventure_worlds
                    (id, owner_user_id, template_id, world_name, world_description,
                     world_lore, stability, danger, mystery,
                     locations_data, factions_data, npcs_data)
                    VALUES (%(id)s, %(owner_user_id)s, %(template_id)s,
                            %(world_name)s, %(world_description)s, %(world_lore)s,
                            %(stability)s, %(danger)s, %(mystery)s,
                            %(locations_data)s::jsonb, %(factions_data)s::jsonb,
                            %(npcs_data)s::jsonb)
                    RETURNING *
                """, world_data)
                world = cur.fetchone()
                conn.commit()
                return world

    @staticmethod
    def get_by_id(world_id):
        """根据 ID 获取世界"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM adventure_worlds WHERE id = %s
                """, (world_id,))
                return cur.fetchone()

    @staticmethod
    def get_user_worlds(user_id, include_archived=False):
        """获取用户的世界列表"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                if include_archived:
                    cur.execute("""
                        SELECT * FROM adventure_worlds
                        WHERE owner_user_id = %s
                        ORDER BY created_at DESC
                    """, (user_id,))
                else:
                    cur.execute("""
                        SELECT * FROM adventure_worlds
                        WHERE owner_user_id = %s AND is_archived = FALSE
                        ORDER BY created_at DESC
                    """, (user_id,))
                return cur.fetchall()

    @staticmethod
    def update_stats(world_id, stability=None, danger=None, mystery=None):
        """更新世界状态指标"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                updates = []
                params = {}

                if stability is not None:
                    updates.append("stability = %(stability)s")
                    params['stability'] = stability
                if danger is not None:
                    updates.append("danger = %(danger)s")
                    params['danger'] = danger
                if mystery is not None:
                    updates.append("mystery = %(mystery)s")
                    params['mystery'] = mystery

                if not updates:
                    return False

                params['world_id'] = world_id
                sql = f"""
                    UPDATE adventure_worlds
                    SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %(world_id)s
                """
                cur.execute(sql, params)
                conn.commit()
                return cur.rowcount > 0

    @staticmethod
    def increment_total_runs(world_id):
        """增加世界的总局数"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE adventure_worlds
                    SET total_runs = total_runs + 1
                    WHERE id = %s
                """, (world_id,))
                conn.commit()


class AdventureCharacterDAO:
    """角色数据访问"""

    @staticmethod
    def create(character_data):
        """创建角色"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO adventure_characters
                    (id, user_id, char_name, char_class, background, personality,
                     appearance, ability_combat, ability_social, ability_stealth,
                     ability_knowledge, ability_survival, equipment_data, relationships_data)
                    VALUES (%(id)s, %(user_id)s, %(char_name)s, %(char_class)s,
                            %(background)s, %(personality)s, %(appearance)s,
                            %(ability_combat)s, %(ability_social)s, %(ability_stealth)s,
                            %(ability_knowledge)s, %(ability_survival)s,
                            %(equipment_data)s::jsonb, %(relationships_data)s::jsonb)
                    RETURNING *
                """, character_data)
                character = cur.fetchone()
                conn.commit()
                return character

    @staticmethod
    def get_by_id(character_id):
        """根据 ID 获取角色"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM adventure_characters WHERE id = %s
                """, (character_id,))
                return cur.fetchone()

    @staticmethod
    def get_user_characters(user_id, only_alive=True):
        """获取用户的角色列表"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                if only_alive:
                    cur.execute("""
                        SELECT * FROM adventure_characters
                        WHERE user_id = %s AND is_alive = TRUE
                        ORDER BY created_at DESC
                    """, (user_id,))
                else:
                    cur.execute("""
                        SELECT * FROM adventure_characters
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                    """, (user_id,))
                return cur.fetchall()

    @staticmethod
    def mark_death(character_id, death_reason):
        """标记角色死亡"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE adventure_characters
                    SET is_alive = FALSE, death_reason = %s
                    WHERE id = %s
                """, (death_reason, character_id))
                conn.commit()

    @staticmethod
    def increment_total_runs(character_id):
        """增加角色的总局数"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE adventure_characters
                    SET total_runs = total_runs + 1
                    WHERE id = %s
                """, (character_id,))
                conn.commit()


class AdventureRunDAO:
    """跑团局数据访问"""

    @staticmethod
    def create(run_data):
        """创建 Run"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO adventure_runs
                    (id, world_id, character_id, user_id, run_title, run_type,
                     mission_objective, status, max_turns, ai_conversation_id, metadata)
                    VALUES (%(id)s, %(world_id)s, %(character_id)s, %(user_id)s,
                            %(run_title)s, %(run_type)s, %(mission_objective)s,
                            %(status)s, %(max_turns)s, %(ai_conversation_id)s,
                            %(metadata)s::jsonb)
                    RETURNING *
                """, run_data)
                run = cur.fetchone()
                conn.commit()
                return run

    @staticmethod
    def get_by_id(run_id):
        """根据 ID 获取 Run"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM adventure_runs WHERE id = %s
                """, (run_id,))
                return cur.fetchone()

    @staticmethod
    def get_user_runs(user_id, status=None):
        """获取用户的 Run 列表"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute("""
                        SELECT * FROM adventure_runs
                        WHERE user_id = %s AND status = %s
                        ORDER BY started_at DESC
                    """, (user_id, status))
                else:
                    cur.execute("""
                        SELECT * FROM adventure_runs
                        WHERE user_id = %s
                        ORDER BY started_at DESC
                    """, (user_id,))
                return cur.fetchall()

    @staticmethod
    def update_turn(run_id, turn_number):
        """更新回合数"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE adventure_runs
                    SET current_turn = %s
                    WHERE id = %s
                """, (turn_number, run_id))
                conn.commit()

    @staticmethod
    def complete_run(run_id, outcome, summary, impact_on_world=None, impact_on_character=None):
        """完成 Run(结算)"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE adventure_runs
                    SET status = 'completed',
                        outcome = %s,
                        summary = %s,
                        impact_on_world = %s::jsonb,
                        impact_on_character = %s::jsonb,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                """, (outcome, summary, impact_on_world, impact_on_character, run_id))
                run = cur.fetchone()
                conn.commit()
                return run


class AdventureRunMessageDAO:
    """Run 对话消息数据访问"""

    @staticmethod
    def save_message(message_data):
        """保存消息"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO adventure_run_messages
                    (id, run_id, role, content, turn_number, action_type, dice_rolls)
                    VALUES (%(id)s, %(run_id)s, %(role)s, %(content)s,
                            %(turn_number)s, %(action_type)s, %(dice_rolls)s::jsonb)
                    RETURNING *
                """, message_data)
                message = cur.fetchone()
                conn.commit()
                return message

    @staticmethod
    def get_run_messages(run_id, limit=100):
        """获取 Run 的所有消息"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM adventure_run_messages
                    WHERE run_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                """, (run_id, limit))
                return cur.fetchall()

    @staticmethod
    def get_messages_by_turn(run_id, turn_number):
        """获取特定回合的消息"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM adventure_run_messages
                    WHERE run_id = %s AND turn_number = %s
                    ORDER BY created_at ASC
                """, (run_id, turn_number))
                return cur.fetchall()
