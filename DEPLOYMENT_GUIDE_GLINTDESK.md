# Glintdesk Marketing Page Deployment Guide

## Entry File
- `blueprints/games/remotedesk/templates/games/remotedesk/index.html`

This template is rendered at `/g/remotedesk/` via the remotedesk blueprint.

## Static Assets
- Favicon and PWA assets: `static/games/remotedesk/`
- Manifest: `static/games/remotedesk/manifest.json`
- Fonts: Google Fonts `Inter` (loaded via CDN in the template)

## External Links
- Privacy Policy: https://www.glintdesk.com/privacy
- Terms of Service: https://www.glintdesk.com/terms

## Download URLs (Replace Before Launch)
The download links are placeholders and must be updated by operations:
- Windows: `https://download.glintdesk.com/windows`
- Android: `https://download.glintdesk.com/android`

Search for the following HTML comments to locate the placeholders:
- `<!-- Ops: replace with final Windows download URL -->`
- `<!-- Ops: replace with final Android download URL -->`

## Notes
- The page is static HTML/CSS and does not require backend changes.
- No additional JavaScript dependencies are needed.
