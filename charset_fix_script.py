#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复字符集排序规则不匹配问题
"""

import pymysql

# 数据库配置
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

def check_table_collations():
    """检查表的字符集和排序规则"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 检查数据库默认字符集
            cursor.execute(f"SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = '{DB_CONFIG['database']}'")
            db_info = cursor.fetchone()
            print(f"数据库字符集: {db_info['DEFAULT_CHARACTER_SET_NAME']}")
            print(f"数据库排序规则: {db_info['DEFAULT_COLLATION_NAME']}")
            
            # 检查各表的字符集
            tables = ['users', 'readings', 'tarot_cards']
            for table in tables:
                cursor.execute(f"""
                    SELECT TABLE_COLLATION 
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = '{DB_CONFIG['database']}' AND TABLE_NAME = '{table}'
                """)
                table_info = cursor.fetchone()
                if table_info:
                    print(f"{table}表排序规则: {table_info['TABLE_COLLATION']}")
                
                # 检查字符串列的排序规则
                cursor.execute(f"""
                    SELECT COLUMN_NAME, COLLATION_NAME 
                    FROM information_schema.COLUMNS 
                    WHERE TABLE_SCHEMA = '{DB_CONFIG['database']}' 
                    AND TABLE_NAME = '{table}' 
                    AND COLLATION_NAME IS NOT NULL
                """)
                columns = cursor.fetchall()
                for col in columns:
                    print(f"  {table}.{col['COLUMN_NAME']}: {col['COLLATION_NAME']}")
            
    finally:
        conn.close()

def fix_collations():
    """统一字符集排序规则"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            print("开始修复字符集排序规则...")
            
            # 设置统一的排序规则 utf8mb4_unicode_ci
            target_collation = 'utf8mb4_unicode_ci'
            
            # 修复users表
            print("\n修复users表...")
            cursor.execute(f"ALTER TABLE users CONVERT TO CHARACTER SET utf8mb4 COLLATE {target_collation}")
            
            # 修复readings表
            print("修复readings表...")
            cursor.execute(f"ALTER TABLE readings CONVERT TO CHARACTER SET utf8mb4 COLLATE {target_collation}")
            
            # 修复tarot_cards表
            print("修复tarot_cards表...")
            cursor.execute(f"ALTER TABLE tarot_cards CONVERT TO CHARACTER SET utf8mb4 COLLATE {target_collation}")
            
            # 特别处理可能有问题的列
            print("\n特别处理关键字段...")
            
            # users表的id列
            cursor.execute(f"ALTER TABLE users MODIFY COLUMN id VARCHAR(36) CHARACTER SET utf8mb4 COLLATE {target_collation} NOT NULL")
            
            # readings表的user_id列
            cursor.execute(f"ALTER TABLE readings MODIFY COLUMN user_id VARCHAR(36) CHARACTER SET utf8mb4 COLLATE {target_collation} NOT NULL")
            
            conn.commit()
            print("✅ 字符集修复完成")
            
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
    
    return True

def verify_fix():
    """验证修复结果"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            print("\n验证修复结果...")
            
            # 重新测试数据一致性检查
            cursor.execute("""
                SELECT COUNT(*) as orphaned 
                FROM readings r 
                LEFT JOIN users u ON r.user_id = u.id 
                WHERE u.id IS NULL
            """)
            orphaned = cursor.fetchone()
            
            if orphaned['count'] > 0:
                print(f"⚠️ 仍有 {orphaned['count']} 条孤儿记录")
                
                # 查看具体的孤儿记录
                cursor.execute("""
                    SELECT r.user_id, COUNT(*) as count
                    FROM readings r 
                    LEFT JOIN users u ON r.user_id = u.id 
                    WHERE u.id IS NULL
                    GROUP BY r.user_id
                """)
                orphans = cursor.fetchall()
                print("孤儿记录详情:")
                for orphan in orphans:
                    print(f"  user_id: '{orphan['user_id']}', 记录数: {orphan['count']}")
                    
                return False
            else:
                print("✅ 数据一致性检查通过")
                
            # 测试基本查询
            cursor.execute("SELECT COUNT(*) as user_count FROM users")
            user_count = cursor.fetchone()
            
            cursor.execute("SELECT COUNT(*) as reading_count FROM readings")
            reading_count = cursor.fetchone()
            
            print(f"用户数: {user_count['user_count']}")
            print(f"记录数: {reading_count['reading_count']}")
            
            # 测试关联查询
            cursor.execute("""
                SELECT u.id, COUNT(r.id) as reading_count 
                FROM users u 
                LEFT JOIN readings r ON u.id = r.user_id 
                GROUP BY u.id
            """)
            user_readings = cursor.fetchall()
            
            print("用户记录统计:")
            for ur in user_readings:
                print(f"  用户 {ur['id'][:8]}...: {ur['reading_count']} 条记录")
                
            return True
            
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False
    finally:
        conn.close()

def main():
    """主流程"""
    print("=" * 50)
    print("字符集排序规则修复脚本")
    print("=" * 50)
    
    # 1. 检查当前状态
    print("\n1. 检查当前字符集状态...")
    check_table_collations()
    
    # 2. 修复排序规则
    print("\n2. 修复排序规则...")
    if not fix_collations():
        return
    
    # 3. 重新检查
    print("\n3. 检查修复后状态...")
    check_table_collations()
    
    # 4. 验证功能
    print("\n4. 验证数据库功能...")
    if verify_fix():
        print("\n" + "=" * 50)
        print("🎉 字符集修复成功！数据库现在完全正常！")
        print("=" * 50)
    else:
        print("\n⚠️ 修复后仍有一些问题，可能需要进一步检查")

if __name__ == "__main__":
    confirm = input("确定要修复字符集排序规则吗？(yes/no): ")
    if confirm.lower() in ['yes', 'y']:
        main()
    else:
        print("修复已取消")