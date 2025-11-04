# Code Playground Deployment Instructions

To integrate the live code playground mini-game into your working tree, make sure you have fetched the latest changes for the `work` branch and pulled them into your local checkout:

```bash
git fetch origin
git checkout work
git pull --ff-only origin work
```

If you prefer to cherry-pick the feature onto another branch, you can pull just the relevant commits and reapply them:

```bash
git fetch origin work
# Replace <commit_sha> with the actual commit identifier you want.
git cherry-pick <commit_sha>
```

Alternatively, you can copy the files listed below if you are working without Git remotes:

- `blueprints/games/code_playground/plugin.py`
- `blueprints/games/code_playground/static/main.js`
- `blueprints/games/code_playground/templates/games/code_playground/index.html`
- `static/images/covers/code_playground.svg`
- `static/projects.json`
- `config.py`

These paths contain everything required to run the mini-game with the live preview/editor layout.
