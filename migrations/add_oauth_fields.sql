-- ========================================
-- Google OAuth 字段迁移脚本
-- 用途：为 users 表添加 OAuth 登录支持
-- 执行方式：在 Supabase SQL 编辑器中直接运行
-- ========================================

-- 1. 添加 oauth_provider 字段（OAuth 提供商）
ALTER TABLE users
ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(50) DEFAULT 'local';

-- 2. 添加 oauth_id 字段（Google 用户 ID）
ALTER TABLE users
ADD COLUMN IF NOT EXISTS oauth_id VARCHAR(255);

-- 3. 添加 email 字段（用户邮箱）
ALTER TABLE users
ADD COLUMN IF NOT EXISTS email VARCHAR(255);

-- 4. 添加 avatar_url 字段（Google 头像）
ALTER TABLE users
ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- 5. 添加 username 字段（如果不存在）
ALTER TABLE users
ADD COLUMN IF NOT EXISTS username VARCHAR(255);

-- 6. 添加 password_hash 字段（如果不存在）
ALTER TABLE users
ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- 7. 更新现有用户的 oauth_provider 为 'local'
UPDATE users
SET oauth_provider = 'local'
WHERE oauth_provider IS NULL;

-- 8. 创建唯一索引：确保同一个 OAuth 提供商的用户 ID 唯一
CREATE UNIQUE INDEX IF NOT EXISTS idx_oauth_provider_id
ON users(oauth_provider, oauth_id)
WHERE oauth_id IS NOT NULL;

-- 9. 创建邮箱索引（提升查询性能）
CREATE INDEX IF NOT EXISTS idx_email
ON users(email)
WHERE email IS NOT NULL;

-- 10. 验证迁移结果
SELECT
    column_name,
    data_type,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;

-- 完成！现在 users 表已支持 Google OAuth 登录
