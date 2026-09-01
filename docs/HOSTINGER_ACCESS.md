# How to host SattvaSrsti Blog on Hostinger

## Domain status (checked)

| Domain | Status |
|--------|--------|
| `sattvasrsti.blog` | **Only** domain for this blog (Firebase Hosting) |
| `sattvasrsti.com` / `.in` | Must **not** point at this blog — see `docs/REVERT_COM_IN_DNS.md` |

Use **`sattvasrsti.blog`** unless you change DNS.

---

## Fastest path — static site (matches local preview)

We already built the site as static HTML/JS that reads Firebase live.

### You do in Hostinger hPanel

1. **Websites → Add website** (or open the existing site for `sattvasrsti.blog`)
2. Choose **Empty** / PHP hosting (not WordPress) — or use File Manager on `public_html`
3. Clear the parked placeholder files in `public_html`
4. Upload **everything inside** `deploy/public/` into `public_html`

### Or give me FTP (preferred for me to deploy)

Create a local file `.env` (never commit it):

```env
BLOG_PUBLIC_BASE=https://sattvasrsti.blog
FTP_HOST=ftp.YOUR_HOSTINGER_HOST.com
FTP_USER=your_ftp_user
FTP_PASSWORD=your_ftp_password
FTP_REMOTE_DIR=/public_html
```

Then tell me “deploy” — I will run:

```bash
python scripts/build_deploy.py
python scripts/deploy_ftp.py
```

Find FTP in hPanel: **Files → FTP Accounts**.

---

## WordPress path (optional later)

If you prefer WordPress:

1. Install WordPress on the domain in hPanel
2. Create **Application Password** (Users → Profile)
3. Put in `.env`:

```env
WP_SITE_URL=https://sattvasrsti.blog
WP_USERNAME=...
WP_APP_PASSWORD=xxxx xxxx ...
```

---

## Checklist for you

- [ ] Confirm domain: `sattvasrsti.blog`
- [ ] Attach hosting (un-park the domain)
- [ ] Send FTP details in `.env` **or** upload `deploy/public/` yourself
- [ ] Optional: `OPENAI_API_KEY` for LLM humanize on new recipes
