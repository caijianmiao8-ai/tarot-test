#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：添加 Google OAuth 支持字段
为 users 表添加: oauth_provider, oauth_id, email, avatar_url, username, password_hash
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

# 从环境变量获取数据库URL
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("❌ 错误：DATABASE_URL 环境变量未设置")
    print("请设置 DATABASE_URL 环境变量，例如：")
    print("export DATABASE_URL='postgresql://user:password@host:port/database'")
    exit(1)

def get_db():
    """获取数据库连接"""
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        sslmode="require"
    )

def check_column_exists(cursor, table_name, column_name):
    """检查列是否存在"""
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s
    """, (table_name, column_name))
    return cursor.fetchone() is not None

def add_oauth_fields():
    """添加OAuth相关字段到users表"""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            print("开始添加 OAuth 支持字段...")

            # 检查并添加 oauth_provider 字段
            if not check_column_exists(cursor, 'users', 'oauth_provider'):
                cursor.execute("""
                    ALTER TABLE users
                    ADD COLUMN oauth_provider VARCHAR(50) DEFAULT 'local'
                """)
                print("✅ 添加 oauth_provider 字段")
            else:
                print("⏭️  oauth_provider 字段已存在")

            # 检查并添加 oauth_id 字段
            if not check_column_exists(cursor, 'users', 'oauth_id'):
                cursor.execute("""
                    ALTER TABLE users
                    ADD COLUMN oauth_id VARCHAR(255)
                """)
                print("✅ 添加 oauth_id 字段")
            else:
                print("⏭️  oauth_id 字段已存在")

            # 检查并添加 email 字段
            if not check_column_exists(cursor, 'users', 'email'):
                cursor.execute("""
                    ALTER TABLE users
                    ADD COLUMN email VARCHAR(255)
                """)
                print("✅ 添加 email 字段")
            else:
                print("⏭️  email 字段已存在")

            # 检查并添加 avatar_url 字段
            if not check_column_exists(cursor, 'users', 'avatar_url'):
                cursor.execute("""
                    ALTER TABLE users
                    ADD COLUMN avatar_url TEXT
                """)
                print("✅ 添加 avatar_url 字段")
            else:
                print("⏭️  avatar_url 字段已存在")

            # 检查并添加 username 字段（如果不存在）
            if not check_column_exists(cursor, 'users', 'username'):
                cursor.execute("""
                    ALTER TABLE users
                    ADD COLUMN username VARCHAR(255)
                """)
                print("✅ 添加 username 字段")
            else:
                print("⏭️  username 字段已存在")

            # 检查并添加 password_hash 字段（如果不存在）
            if not check_column_exists(cursor, 'users', 'password_hash'):
                cursor.execute("""
                    ALTER TABLE users
                    ADD COLUMN password_hash TEXT
                """)
                print("✅ 添加 password_hash 字段")
            else:
                print("⏭️  password_hash 字段已存在")

            # 更新现有用户的 oauth_provider 为 'local'
            cursor.execute("""
                UPDATE users
                SET oauth_provider = 'local'
                WHERE oauth_provider IS NULL
            """)

            # 创建唯一索引：确保同一个 OAuth 提供商的用户 ID 唯一
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_oauth_provider_id
                ON users(oauth_provider, oauth_id)
                WHERE oauth_id IS NOT NULL
            """)
            print("✅ 创建 OAuth 唯一索引")

            # 创建邮箱索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_email
                ON users(email)
                WHERE email IS NOT NULL
            """)
            print("✅ 创建邮箱索引")

            conn.commit()
            print("\n🎉 数据库迁移成功完成！")
            print("users 表现已支持 Google OAuth 登录")

    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def verify_migration():
    """验证迁移结果"""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT column_name, data_type, column_default
                FROM information_schema.columns
                WHERE table_name = 'users'
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()

            print("\n📋 users 表当前结构：")
            for col in columns:
                default = col['column_default'] or 'NULL'
                print(f"  - {col['column_name']}: {col['data_type']} (默认值: {default})")

            # 检查索引
            cursor.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'users'
            """)
            indexes = cursor.fetchall()

            print("\n📑 users 表索引：")
            for idx in indexes:
                print(f"  - {idx['indexname']}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Google OAuth 数据库迁移脚本")
    print("=" * 60)
    print()

    confirm = input("确定要执行数据库迁移吗？(yes/no): ")
    if confirm.lower() in ['yes', 'y']:
        try:
            add_oauth_fields()
            verify_migration()
        except Exception as e:
            print(f"\n迁移过程出错: {e}")
            exit(1)
    else:
        print("迁移已取消")
