# Google OAuth 登录集成指南

## 功能说明

本项目已集成 Google OAuth 登录功能，用户可以：
- 使用 Google 账号快速登录
- 将 Google 账号关联到现有账号
- 创建新的 Google 账号

## 部署前准备

### 1. 运行数据库迁移

首先需要为数据库添加 OAuth 支持字段：

```bash
# 设置环境变量
export DATABASE_URL="your-supabase-postgresql-url"

# 运行迁移脚本
python add_oauth_fields.py
```

### 2. 配置 Google Cloud Console

访问 [Google Cloud Console](https://console.cloud.google.com/)：

#### 已获授权的 JavaScript 来源
```
https://your-domain.vercel.app
```

本地测试还需要添加：
```
http://localhost:5000
http://127.0.0.1:5000
```

#### 已获授权的重定向 URI
```
https://your-domain.vercel.app/auth/google/callback
```

本地测试还需要添加：
```
http://localhost:5000/auth/google/callback
http://127.0.0.1:5000/auth/google/callback
```

### 3. 配置环境变量

在 Vercel 项目设置中添加以下环境变量：

```
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
SERVER_URL=https://your-domain.vercel.app
```

**注意：** 请使用你从 Google Cloud Console 获取的真实 Client ID 和 Client Secret。

其他已有的环境变量：
- `FLASK_SECRET_KEY`
- `DATABASE_URL`
- `DIFY_API_KEY`
- `WORKFLOW_ID`

## 本地测试

1. 复制 `.env.example` 为 `.env`
2. 填写环境变量
3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
4. 运行应用：
   ```bash
   python app.py
   ```
5. 访问 http://localhost:5000

## 工作流程

### 新用户 Google 登录
1. 用户点击"使用 Google 账号登录"
2. 跳转到 Google 授权页面
3. 用户授权后返回应用
4. 系统创建新账号并自动登录

### 已有邮箱的 Google 登录
1. 用户使用 Google 登录
2. 系统检测到邮箱已存在
3. 显示账号关联页面，用户可选择：
   - **关联到现有账号**：绑定 Google 登录到现有账号
   - **创建新账号**：创建独立的新账号

### 数据库字段说明

新增字段：
- `oauth_provider`: OAuth 提供商（'google' 或 'local'）
- `oauth_id`: Google 用户 ID
- `email`: 用户邮箱
- `avatar_url`: Google 头像 URL
- `username`: 用户名（Google 登录时使用 Google 名称）
- `password_hash`: 密码哈希（仅本地注册用户）

## 文件清单

- `app.py`: 添加了 Google OAuth 路由和处理逻辑
- `requirements.txt`: 添加了 `Authlib==1.3.0`
- `add_oauth_fields.py`: 数据库迁移脚本
- `templates/login.html`: 添加了 Google 登录按钮
- `templates/link_account.html`: 账号关联页面
- `.env.example`: 环境变量示例

## 安全说明

- 客户端密钥已通过环境变量配置，不会暴露在代码中
- OAuth 回调 URL 仅限授权域名
- 会话使用 Flask secret_key 加密
- 数据库连接使用 SSL

## 常见问题

### 1. 回调 URL 报错 redirect_uri_mismatch
检查 Google Cloud Console 中配置的重定向 URI 是否与实际域名一致。

### 2. 本地测试无法登录
确保在 Google Cloud Console 中添加了 `http://localhost:5000` 相关的 URI。

### 3. 数据库迁移失败
检查 `DATABASE_URL` 环境变量是否正确，确保有数据库写入权限。

## 技术栈

- **Flask**: Web 框架
- **Authlib**: OAuth 客户端库
- **PostgreSQL**: 数据库（Supabase）
- **Vercel**: 部署平台
