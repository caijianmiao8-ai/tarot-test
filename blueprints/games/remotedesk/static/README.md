# RemoteDesk Static Assets

## Required Icon Files

Please add the following icon files to this directory for the website to be production-ready:

### Favicon Files
- `favicon.ico` - 16x16, 32x32, 48x48 (multi-size ICO file)
- `favicon-16x16.png` - 16x16 PNG
- `favicon-32x32.png` - 32x32 PNG
- `apple-touch-icon.png` - 180x180 PNG (for iOS devices)

### Web App Icons
- `icon-72x72.png` - 72x72 PNG
- `icon-96x96.png` - 96x96 PNG
- `icon-128x128.png` - 128x128 PNG
- `icon-144x144.png` - 144x144 PNG
- `icon-152x152.png` - 152x152 PNG
- `icon-192x192.png` - 192x192 PNG
- `icon-384x384.png` - 384x384 PNG
- `icon-512x512.png` - 512x512 PNG (maskable)

### Social Media Images
- `og-image.png` - 1200x630 PNG (Open Graph image for Facebook, LinkedIn, etc.)
- `twitter-card.png` - 1200x600 PNG (Twitter card image)
- `logo.png` - Company logo (SVG or high-res PNG recommended)

### Screenshots
- `screenshot-mobile.png` - 540x720 PNG (mobile screenshot)
- `screenshot-desktop.png` - 1280x720 PNG (desktop screenshot)

## Icon Design Guidelines

- **Brand Color**: Use #0071e3 (blue) as the primary color
- **Background**: Light background (#fafbfc) or transparent
- **Style**: Modern, clean, minimalist design matching the Apple-style aesthetic
- **Logo**: Should represent "RemoteDesk" - consider using a monitor/phone combination icon

## Tools for Icon Generation

- [Favicon Generator](https://realfavicongenerator.net/)
- [PWA Asset Generator](https://github.com/onderceylan/pwa-asset-generator)
- [Figma](https://www.figma.com/) - For designing custom icons

## Quick Setup

You can use the following command to generate all required icons from a single source image:

```bash
# Using PWA Asset Generator (requires Node.js)
npx pwa-asset-generator source-logo.png static/games/remotedesk/ --favicon --manifest manifest.json
```
