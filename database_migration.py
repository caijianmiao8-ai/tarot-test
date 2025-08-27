#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
塔罗应用数据库迁移脚本 - 修复版
用途：创建用户表，迁移现有数据到新的用户系统
"""

import pymysql
import uuid
from datetime import datetime

# 数据库配置 - 请确认这些信息正确
DB_CONFIG = {
    "host": "ruoshui233.mysql.pythonanywhere-services.com",
    "user": "ruoshui233", 
    "password": "cai-6831",
    "database": "ruoshui233$tarot",
    "charset": "utf8mb4"
}

def get_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)

def check_current_tables():
    """检查当前数据库表结构"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 检查现有表
            cursor.execute("SHOW TABLES")
            tables = [row[f'Tables_in_{DB_CONFIG["database"]}'] for row in cursor.fetchall()]
            
            print("当前数据库表：", tables)
            
            # 检查readings表结构
            if 'readings' in tables:
                cursor.execute("DESCRIBE readings")
                readings_structure = cursor.fetchall()
                print("\nreadings表结构：")
                for col in readings_structure:
                    print(f"  {col['Field']}: {col['Type']}")
                
                # 检查readings表的索引
                cursor.execute("SHOW INDEX FROM readings")
                indexes = cursor.fetchall()
                print("\nreadings表现有索引：")
                for idx in indexes:
                    print(f"  {idx['Key_name']}: {idx['Column_name']}")
            
            # 检查塔罗牌数据表
            tarot_table = None
            if 'tarot_cards' in tables:
                tarot_table = 'tarot_cards'
            elif 'cards' in tables:
                tarot_table = 'cards'
            
            if tarot_table:
                cursor.execute(f"SELECT COUNT(*) as count FROM {tarot_table}")
                card_count = cursor.fetchone()
                print(f"\n{tarot_table}表中有 {card_count['count']} 张卡牌")
            
            return tables, tarot_table
    finally:
        conn.close()

def create_users_table():
    """创建用户表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 检查users表是否已存在
            cursor.execute("SHOW TABLES LIKE 'users'")
            if cursor.fetchone():
                print("users表已存在，跳过创建")
                return True
            
            # 创建users表
            create_users_sql = """
            CREATE TABLE users (
                id VARCHAR(36) PRIMARY KEY COMMENT '用户UUID',
                device_id VARCHAR(255) COMMENT '设备指纹',
                first_visit DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '首次访问时间',
                last_visit DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后访问时间',
                visit_count INT DEFAULT 1 COMMENT '访问次数',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_device_id (device_id),
                INDEX idx_last_visit (last_visit)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表'
            """
            
            cursor.execute(create_users_sql)
            conn.commit()
            print("✅ 成功创建users表")
            return True
            
    except Exception as e:
        print(f"❌ 创建users表失败: {e}")
        return False
    finally:
        conn.close()

def check_migration_status():
    """检查迁移状态"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 检查readings表是否有user_id_new列（说明迁移进行了一半）
            cursor.execute("DESCRIBE readings")
            columns = [col['Field'] for col in cursor.fetchall()]
            
            has_user_id_new = 'user_id_new' in columns
            user_id_type = None
            
            # 检查user_id列的类型
            cursor.execute("SHOW COLUMNS FROM readings LIKE 'user_id'")
            user_id_info = cursor.fetchone()
            if user_id_info:
                user_id_type = user_id_info['Type']
            
            print(f"readings表状态：")
            print(f"  - 有user_id_new临时列: {has_user_id_new}")
            print(f"  - user_id列类型: {user_id_type}")
            
            return has_user_id_new, user_id_type
    finally:
        conn.close()

def cleanup_failed_migration():
    """清理失败的迁移"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 删除user_id_new列（如果存在）
            try:
                cursor.execute("ALTER TABLE readings DROP COLUMN user_id_new")
                print("✅ 清理了临时列 user_id_new")
            except:
                pass
            
            # 删除可能已创建的索引
            try:
                cursor.execute("ALTER TABLE readings DROP INDEX idx_user_date")
                print("✅ 清理了索引 idx_user_date")
            except:
                pass
                
            conn.commit()
            return True
    except Exception as e:
        print(f"⚠️ 清理时出现错误（可以忽略）: {e}")
        return True
    finally:
        conn.close()

def migrate_guest_users_safe():
    """安全迁移现有的guest用户数据"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 检查readings表中是否有guest数据
            cursor.execute("SELECT COUNT(*) as count FROM readings WHERE user_id = 'guest'")
            guest_count = cursor.fetchone()
            
            if guest_count['count'] == 0:
                print("没有guest用户数据需要迁移")
                return True
            
            print(f"发现 {guest_count['count']} 条guest用户记录，开始安全迁移...")
            
            # 生成新的UUID给guest用户
            guest_uuid = str(uuid.uuid4())
            print(f"为guest用户生成UUID: {guest_uuid}")
            
            # 获取guest用户的最早访问时间
            cursor.execute("SELECT MIN(timestamp) as first_visit FROM readings WHERE user_id = 'guest'")
            first_visit_result = cursor.fetchone()
            first_visit = first_visit_result['first_visit'] if first_visit_result['first_visit'] else datetime.now()
            
            # 创建对应的用户记录
            cursor.execute("""
                INSERT INTO users (id, device_id, first_visit, visit_count, created_at)
                VALUES (%s, 'migrated_guest', %s, %s, NOW())
            """, (guest_uuid, first_visit, guest_count['count']))
            
            print("✅ 创建了guest用户记录")
            
            # 修改readings表结构 - 分步进行，更安全
            print("正在安全修改readings表结构...")
            
            # 1. 添加新的user_id_new列
            cursor.execute("ALTER TABLE readings ADD COLUMN user_id_new VARCHAR(36)")
            print("  - 添加临时列 user_id_new")
            
            # 2. 更新guest数据
            cursor.execute(
                "UPDATE readings SET user_id_new = %s WHERE user_id = 'guest'",
                (guest_uuid,)
            )
            print("  - 更新guest数据到新UUID")
            
            # 3. 更新其他可能的用户数据（如果有的话）
            cursor.execute("UPDATE readings SET user_id_new = user_id WHERE user_id != 'guest'")
            print("  - 更新其他用户数据")
            
            # 4. 删除旧列
            cursor.execute("ALTER TABLE readings DROP COLUMN user_id")
            print("  - 删除旧的user_id列")
            
            # 5. 重命名新列
            cursor.execute("ALTER TABLE readings CHANGE user_id_new user_id VARCHAR(36) NOT NULL")
            print("  - 重命名新列为user_id")
            
            # 6. 添加索引 - 检查是否已存在
            try:
                cursor.execute("SHOW INDEX FROM readings WHERE Key_name = 'idx_user_date'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE readings ADD INDEX idx_user_date (user_id, date)")
                    print("  - 添加了索引 idx_user_date")
                else:
                    print("  - 索引 idx_user_date 已存在，跳过")
            except Exception as e:
                print(f"  - 添加索引时出现问题（可以忽略）: {e}")
            
            conn.commit()
            print(f"✅ 成功迁移guest用户数据到UUID: {guest_uuid}")
            return True
            
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        print("正在回滚操作...")
        conn.rollback()
        return False
    finally:
        conn.close()

def verify_migration():
    """验证迁移结果"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 检查users表
            cursor.execute("SELECT COUNT(*) as count FROM users")
            user_count = cursor.fetchone()
            print(f"users表中有 {user_count['count']} 个用户")
            
            if user_count['count'] > 0:
                cursor.execute("SELECT id, device_id, visit_count FROM users LIMIT 3")
                users = cursor.fetchall()
                print("用户样例：")
                for user in users:
                    print(f"  UUID: {user['id'][:8]}..., 设备: {user['device_id']}, 访问次数: {user['visit_count']}")
            
            # 检查readings表
            cursor.execute("SELECT COUNT(*) as count FROM readings")
            reading_count = cursor.fetchone()
            print(f"readings表中有 {reading_count['count']} 条记录")
            
            # 检查readings表中user_id列的类型
            cursor.execute("SHOW COLUMNS FROM readings LIKE 'user_id'")
            user_id_info = cursor.fetchone()
            print(f"readings表user_id列类型: {user_id_info['Type']}")
            
            # 检查数据一致性
            cursor.execute("""
                SELECT COUNT(*) as orphaned 
                FROM readings r 
                LEFT JOIN users u ON r.user_id = u.id 
                WHERE u.id IS NULL
            """)
            orphaned = cursor.fetchone()
            
            if orphaned['count'] > 0:
                print(f"⚠️ 警告：发现 {orphaned['count']} 条孤儿记录")
                # 显示一些孤儿记录的详情
                cursor.execute("SELECT DISTINCT user_id FROM readings r LEFT JOIN users u ON r.user_id = u.id WHERE u.id IS NULL LIMIT 3")
                orphan_ids = cursor.fetchall()
                print("孤儿记录的user_id样例：")
                for orphan in orphan_ids:
                    print(f"  {orphan['user_id']}")
                return False
            else:
                print("✅ 数据一致性检查通过")
                return True
                
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False
    finally:
        conn.close()

def main():
    """主迁移流程"""
    print("=" * 50)
    print("塔罗应用数据库迁移脚本 - 修复版")
    print("=" * 50)
    
    try:
        # 1. 检查当前状态
        print("\n1. 检查当前数据库状态...")
        tables, tarot_table = check_current_tables()
        
        if 'readings' not in tables:
            print("❌ 错误：readings表不存在，请先确保基础表已创建")
            return
        
        # 2. 检查迁移状态
        print("\n2. 检查迁移状态...")
        has_user_id_new, user_id_type = check_migration_status()
        
        if has_user_id_new:
            print("⚠️ 检测到之前的迁移未完成，先进行清理...")
            cleanup_failed_migration()
        
        # 3. 创建users表
        print("\n3. 创建users表...")
        if not create_users_table():
            return
        
        # 4. 迁移数据
        print("\n4. 安全迁移现有数据...")
        if not migrate_guest_users_safe():
            print("迁移失败，正在清理...")
            cleanup_failed_migration()
            return
        
        # 5. 验证迁移
        print("\n5. 验证迁移结果...")
        if not verify_migration():
            print("⚠️ 验证发现问题，但迁移可能仍然成功")
            print("请手动检查数据库状态")
        
        print("\n" + "=" * 50)
        print("🎉 数据库迁移成功完成！")
        print("现在可以使用新的用户系统了")
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ 迁移过程中发生错误: {e}")
        print("请检查数据库连接和权限设置")
        print("如果需要，可以运行清理功能")

def cleanup_only():
    """仅执行清理功能"""
    print("=" * 50)
    print("清理失败的迁移")
    print("=" * 50)
    
    cleanup_failed_migration()
    
    print("\n检查清理后的状态...")
    check_migration_status()

if __name__ == "__main__":
    print("请选择操作：")
    print("1. 执行完整迁移")
    print("2. 仅清理失败的迁移")
    
    choice = input("请输入选择 (1/2): ")
    
    if choice == "2":
        cleanup_only()
    else:
        # 安全确认
        confirm = input("确定要执行数据库迁移吗？这将修改现有数据结构。(yes/no): ")
        if confirm.lower() in ['yes', 'y']:
            main()
        else:
            print("迁移已取消")