# seunghan.xyz

개인 포트폴리오 웹사이트 (Hugo + PaperMod theme)

## Project Information

- **URL**: https://seunghan.xyz/
- **Repository**: https://github.com/seunghan91/seunghan-xyz.git
- **Project Path**: `~/seunghan/domain/seunghan-xyz`
- **Framework**: Hugo Static Site Generator
- **Theme**: PaperMod (Git submodule)

## Project Structure

```
seunghan-xyz/
├── archetypes/       # Content templates
├── content/          # Site content (posts, pages)
├── layouts/          # Custom layouts
├── static/           # Static assets
├── themes/           # Hugo themes (PaperMod)
├── public/           # Built site (generated)
└── hugo.toml         # Hugo configuration
```

## Development

### Prerequisites
- Hugo extended version

### Local Development
```bash
# Serve locally
hugo server -D

# Build for production
hugo --minify
```

## Deployment

The site is deployed to https://seunghan.xyz/ using the built files in the `public/` directory.

**Note**: Deployment configuration should be added here (e.g., Netlify, GitHub Pages, etc.)

## Migration Note

This project was migrated from `~/seunghan-xyz` to `~/seunghan/domain/seunghan-xyz` on 2026-02-15.
Git history has been preserved.
