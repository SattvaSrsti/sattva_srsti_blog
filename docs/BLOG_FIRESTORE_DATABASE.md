# Blog Firestore database (`blog`)

Public blog content lives in a **named Firestore database** `blog` in project `sattva-srsti`. The app catalog stays in `(default)` with no public read.

| Database | Collections | Who reads |
|----------|-------------|-----------|
| `(default)` | `recipes_v2`, users, admin, … | App (auth rules) + pipeline (Admin SDK) |
| `blog` | `blog_posts` only | Website (anonymous) + pipeline writes |

## One-time setup

1. Create the database (if missing):

   ```bash
   firebase firestore:databases:create blog --location=nam5 --project sattva-srsti
   ```

   (Already created for this project.)

2. Copy existing posts from `(default)` → `blog`:

   ```bash
   node scripts/migrate_blog_posts_to_blog_db.js
   ```

3. Deploy blog DB rules + hosting:

   ```bash
   python scripts/build_deploy.py
   firebase deploy --only firestore:blog,hosting:blog --project sattva-srsti
   ```

4. Redeploy blog Cloud Functions (writes target `blog` DB):

   ```bash
   cd functions && npm run deploy
   ```

## Optional cleanup

After the site works, you may delete `blog_posts` from `(default)` in Console (Admin SDK / Console only). Keep a backup export first.

## Override database id

Set `FIRESTORE_BLOG_DATABASE` (Node functions + Python scripts) if you use a name other than `blog`.
