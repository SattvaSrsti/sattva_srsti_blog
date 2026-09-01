# Hostinger — make sattvasrsti.blog serve the blog (no WordPress)

## Current status

- Domain **sattvasrsti.blog** = active, but shows **Parked Domain** page
- Blog files are ready in `deploy/public/`
- We do **not** need WordPress or the ₹199/month WordPress plans
- Deploy needs a place to put HTML files = Hostinger **website hosting** (PHP/HTML), then FTP or File Manager

## Do this in Hostinger (step by step)

### 1) Add an HTML website (not WordPress)

1. hPanel → **Websites** → **Add website**
2. Choose **PHP or HTML** (or “Empty” / “Upload website”) — **not** WordPress, not Horizons, not Website Builder
3. Select domain: **sattvasrsti.blog**
4. If it asks for a plan:
   - Pick the **cheapest hosting** that includes a website (not “WordPress only” marketing)
   - Domain-only does **not** give File Manager / FTP

### 2) Open File Manager (proof hosting works)

When hosting is attached you should see:
- **File Manager**, or
- **FTP Accounts**

If you still only see DNS / Contact / Grant access → hosting is not attached yet.

### 3) Upload the blog

**A — You upload (fastest today)**

1. File Manager → open `public_html`
2. Delete parked placeholder files (`index.html` / default parked page)
3. Upload **all files and folders** from:

`C:\Users\ubhar\Documents\GitHub\Sattva_Srsti_blogpost\deploy\public\`

Including: `index.html`, `post.html`, `styles.css`, `render.js`, `landing.js`, `data/`, etc.

4. Visit https://sattvasrsti.blog/

**B — I deploy for you**

1. hPanel → **FTP Accounts** → create/copy:
   - FTP host
   - username
   - password
2. Create project file `.env` with:

```env
BLOG_PUBLIC_BASE=https://sattvasrsti.blog
FTP_HOST=...
FTP_USER=...
FTP_PASSWORD=...
FTP_REMOTE_DIR=/public_html
```

3. Tell me: **FTP is in .env — deploy**

## Why Firebase is not enough here

Firebase already holds recipe + blog **data**.  
Hostinger must serve the **website files**. That’s why the parked page is still showing.

## After it is live

You should see 10 cards on the home page; clicking one opens that recipe’s blog post (data from Firebase).
