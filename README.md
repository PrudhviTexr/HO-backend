# Home & Own — Python API (backend)

This folder is the backend source. For **Git / Render (HO-backend repo)**, do not push `python_api` as a subfolder.

## Export for Git copy-paste

From project root (`24-03-2026`):

```powershell
powershell -ExecutionPolicy Bypass -File python_api\scripts\export-for-git-backend.ps1
```

This creates **`HO-backend-copy/`** at the project root. Copy **everything inside** that folder into your Git repo root (`HO-backend`), then commit and push.

Expected Git repo layout:

```
HO-backend/          ← your Git repo root
  app/
  run_render.py
  requirements.txt
  render.yaml
  ...
```

## Run locally

```powershell
cd python_api
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python run_render.py
```

## Deploy

- **Render:** push exported contents to `HO-backend` on GitHub.
- **Zip (GoDaddy):** `powershell -File scripts\package-for-godaddy.ps1` → `app.zip`

See `RENDER_DEPLOY.md` and `DEPLOY_WITHOUT_GIT.md`.
