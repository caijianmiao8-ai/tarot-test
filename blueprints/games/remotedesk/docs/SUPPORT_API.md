# Glintdesk Support API 接口文档

## 接口信息

| 项目 | 值 |
|------|-----|
| **URL** | `POST /api/support` |
| **Content-Type** | `application/json` |
| **调用方** | 官网工单提交页面 `/support` |

---

## 请求参数

```json
{
  "email": "user@example.com",
  "category": "bug",
  "subject": "Connection failed",
  "message": "Detailed description of the issue...",
  "submitted_at": "2025-01-13T10:30:00.000Z",
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
  "language": "en-US"
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `email` | string | 是 | 用户邮箱，用于回复 |
| `category` | string | 是 | 问题分类，见下方可选值 |
| `subject` | string | 是 | 工单标题/主题 |
| `message` | string | 是 | 问题详细描述 |
| `submitted_at` | string | 是 | 提交时间，ISO 8601 格式 |
| `user_agent` | string | 否 | 浏览器 User-Agent |
| `language` | string | 否 | 浏览器语言设置 |

### category 可选值

| 值 | 显示名称 |
|-----|---------|
| `bug` | Bug Report |
| `feature` | Feature Request |
| `account` | Account Issue |
| `technical` | Technical Support |
| `billing` | Billing Question |
| `other` | Other |

---

## 响应格式

### 成功响应 (HTTP 200)

```json
{
  "success": true,
  "message": "Ticket created successfully"
}
```

### 失败响应 (HTTP 400/500)

```json
{
  "success": false,
  "message": "Invalid email format"
}
```

### 常见错误信息

| HTTP 状态码 | message | 说明 |
|------------|---------|------|
| 400 | Invalid email format | 邮箱格式不正确 |
| 400 | Missing required fields | 缺少必填字段 |
| 500 | Internal server error | 服务器内部错误 |

---

## 数据库表结构建议

```sql
CREATE TABLE support_tickets (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  category VARCHAR(50) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  user_agent TEXT,
  language VARCHAR(10),
  status VARCHAR(20) DEFAULT 'open',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_tickets_email ON support_tickets(email);
CREATE INDEX idx_tickets_status ON support_tickets(status);
CREATE INDEX idx_tickets_created_at ON support_tickets(created_at);
```

### status 状态值

| 值 | 说明 |
|----|------|
| `open` | 待处理 |
| `in_progress` | 处理中 |
| `resolved` | 已解决 |
| `closed` | 已关闭 |

---

## CORS 配置

如果 API 服务和官网不在同一域名下，需要配置 CORS：

```
Access-Control-Allow-Origin: https://www.glintdesk.com
Access-Control-Allow-Methods: POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

---

## 前端调用代码参考

```javascript
const response = await fetch('/api/support', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    email: 'user@example.com',
    category: 'bug',
    subject: 'Connection issue',
    message: 'Description...',
    submitted_at: new Date().toISOString(),
    user_agent: navigator.userAgent,
    language: navigator.language
  })
});

const result = await response.json();
if (result.success) {
  // 提交成功
} else {
  // 提交失败，显示 result.message
}
```

---

## 备注

- 前端页面位置：`/support`
- 提交成功后前端会显示成功提示并清空表单
- 建议后端收到工单后发送邮件通知管理员
