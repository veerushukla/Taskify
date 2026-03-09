# Daily Task Tracker

## Run locally

```powershell
py -m pip install -r requirements.txt
py first.py
```

Open `http://127.0.0.1:5000`.

## Deploy on Vercel

1. Push this folder to GitHub.
2. In Vercel, import the GitHub repo.
3. Framework preset: `Other`.
4. Deploy.

`vercel.json` is already configured to serve `first.py` as a Python serverless function.

## Important database note

On Vercel, this app uses `/tmp/tasks.db`. `/tmp` is ephemeral in serverless functions, so data can reset.

For permanent production data, use a hosted database (for example Vercel Postgres, Neon, Supabase, or Railway Postgres).
