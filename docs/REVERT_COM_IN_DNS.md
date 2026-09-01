# Revert sattvasrsti.com and sattvasrsti.in (do this in Hostinger + Firebase)

**Only `sattvasrsti.blog` may stay connected to this blog.**

## A) Firebase Console (required)

1. Open: https://console.firebase.google.com/project/sattva-srsti/hosting/sites/sattva-srsti  
2. Scroll to **Custom domains**  
3. For **`sattvasrsti.com`** → ⋮ / Remove → confirm  
4. For **`sattvasrsti.in`** → ⋮ / Remove → confirm  
5. Keep **`sattvasrsti.blog`** only (add it if missing; finish its DNS)

Until you remove `.com` / `.in` here, those domains can keep showing this blog even after DNS tweaks.

## B) Hostinger DNS — restore .com and .in

For **each** domain (`sattvasrsti.com`, then `sattvasrsti.in`):

1. Domains → domain → **Edit DNS zone** → **DNS records**  
2. **Delete** Firebase-related records you added (A / AAAA / CNAME / TXT that matched Firebase’s table)  
3. **Restore** the previous records for that domain’s real site/app (whatever was there before)

If you don’t remember old records: Hostinger support / prior screenshots / whoever managed the main site.

## C) Confirm

| URL | Expected |
|-----|----------|
| https://sattvasrsti.blog/ | This blog (after `.blog` DNS + SSL) |
| https://sattvasrsti.com/ | Old site / app — **not** this blog |
| https://sattvasrsti.in/ | Old site — **not** this blog |
| https://sattva-srsti.web.app/ | This blog (always) |
