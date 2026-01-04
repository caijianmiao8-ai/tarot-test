# Glintdesk 官网部署指南

## 文件结构

部署时，运维人员需要将以下文件部署到 Web 服务器根目录：

```
glintdesk.com/
├── index.html              # 主页面（从 templates/games/remotedesk/index.html 复制）
├── manifest.json           # PWA 清单（从 static/manifest.json 复制）
├── favicon.ico             # 网站图标（需准备）
├── favicon-16x16.png       # 16x16 图标（需准备）
├── favicon-32x32.png       # 32x32 图标（需准备）
├── apple-touch-icon.png    # iOS 图标 180x180（需准备）
├── icon-72x72.png          # PWA 图标（需准备）
├── icon-96x96.png          # PWA 图标（需准备）
├── icon-128x128.png        # PWA 图标（需准备）
├── icon-144x144.png        # PWA 图标（需准备）
├── icon-152x152.png        # PWA 图标（需准备）
├── icon-192x192.png        # PWA 图标（需准备）
├── icon-384x384.png        # PWA 图标（需准备）
├── icon-512x512.png        # PWA 图标（需准备）
├── robots.txt              # 搜索引擎爬虫配置（建议创建）
├── sitemap.xml             # 网站地图（建议创建）
└── images/
    ├── og-image.png        # Open Graph 分享图片 1200x630（需准备）
    ├── twitter-card.png    # Twitter 分享图片 1200x628（需准备）
    ├── logo.png            # Logo 图片（需准备）
    ├── screenshot-mobile.png   # 移动端截图（需准备）
    └── screenshot-desktop.png  # 桌面端截图（需准备）
```

## 部署步骤

### 1. 准备文件

1. 将 `templates/games/remotedesk/index.html` 复制为 `index.html` 到根目录
2. 将 `static/manifest.json` 复制到根目录
3. 根据 Logo 图片（蓝色背景 + G字母 + 纸飞机）生成各种尺寸的图标

### 2. 生成图标

使用 Logo 图片生成以下尺寸的图标：
- favicon.ico (16x16, 32x32, 48x48 多尺寸)
- favicon-16x16.png
- favicon-32x32.png
- apple-touch-icon.png (180x180)
- icon-72x72.png ~ icon-512x512.png (各种 PWA 尺寸)

推荐工具：
- https://realfavicongenerator.net/
- https://favicon.io/

### 3. 创建 robots.txt

```
User-agent: *
Allow: /
Sitemap: https://glintdesk.com/sitemap.xml
```

### 4. 创建 sitemap.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://glintdesk.com/</loc>
    <lastmod>2025-01-04</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
```

### 5. 服务器配置

#### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name glintdesk.com www.glintdesk.com;
    return 301 https://glintdesk.com$request_uri;
}

server {
    listen 443 ssl http2;
    server_name glintdesk.com;

    ssl_certificate /path/to/ssl/certificate.crt;
    ssl_certificate_key /path/to/ssl/private.key;

    root /var/www/glintdesk;
    index index.html;

    # GZIP 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    # 缓存静态资源
    location ~* \.(ico|css|js|gif|jpeg|jpg|png|woff|woff2|ttf|svg|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

#### Apache 配置示例 (.htaccess)

```apache
RewriteEngine On
RewriteCond %{HTTPS} off
RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]

# GZIP 压缩
<IfModule mod_deflate.c>
    AddOutputFilterByType DEFLATE text/html text/plain text/css application/json application/javascript
</IfModule>

# 缓存
<IfModule mod_expires.c>
    ExpiresActive On
    ExpiresByType image/png "access plus 30 days"
    ExpiresByType image/jpeg "access plus 30 days"
    ExpiresByType image/gif "access plus 30 days"
    ExpiresByType image/svg+xml "access plus 30 days"
    ExpiresByType text/css "access plus 7 days"
    ExpiresByType application/javascript "access plus 7 days"
</IfModule>

# 安全头
Header set X-Frame-Options "SAMEORIGIN"
Header set X-Content-Type-Options "nosniff"
Header set X-XSS-Protection "1; mode=block"
```

## 需要准备的下载链接

在 index.html 中搜索 `href="#"`，替换为实际的下载链接：

1. **iOS App Store**: 替换 App Store 链接
2. **Android Google Play**: 替换 Google Play 链接
3. **Windows 下载**: 替换 Windows 安装包链接
4. **macOS 下载**: 替换 macOS 安装包链接

## 公司信息

已在页面中配置：

- **公司名称**: 香港拓維智算科技有限公司 / Towardway Intelligence Computing
- **地址**: ROOM 1213, 12/F TOWER A, HUNGHOM COMMERCIAL CENTRE, 39 MA TAU WAI ROAD, HUNG HOM, HONG KONG
- **技术支持邮箱**: support@glintdesk.com

## SEO 检查清单

- [ ] 确保 HTTPS 已启用
- [ ] 提交 sitemap.xml 到 Google Search Console
- [ ] 提交 sitemap.xml 到 Bing Webmaster Tools
- [ ] 验证 Open Graph 图片显示正确
- [ ] 验证 Twitter Card 预览正确
- [ ] 使用 Lighthouse 检查性能分数

## Logo 说明

Logo 设计说明（基于用户提供的图片）：
- 蓝色背景 (#0099FF)
- 白色 G 字母（开口朝右）
- 白色纸飞机图标（从 G 字母开口处飞出）
- 纸飞机有浅蓝色阴影效果

Logo 已内嵌在 index.html 中作为 SVG，可直接使用。如需单独的 PNG 文件，可从 SVG 导出。
