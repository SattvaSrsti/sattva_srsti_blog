# Connect sattvasrsti.blog → Firebase Hosting

## Site is already live (works now)

- Landing: https://sattva-srsti.web.app/
- Example post: https://sattva-srsti.web.app/post.html?slug=aloo-paratha-dough-kept-tearing
- 10 posts confirmed on Hosting

## Add your domain (gives exact DNS values)

Firebase must generate the DNS rows (they are unique per domain). Do this once:

1. Open: https://console.firebase.google.com/project/sattva-srsti/hosting/sites/sattva-srsti  
2. Click **Add custom domain**
3. Enter: `sattvasrsti.blog` (and optionally add `www.sattvasrsti.blog` if asked)
4. Firebase will show a table: **Type / Host / Value**
5. Copy that table into Hostinger → **Domains** → **sattvasrsti.blog** → **Edit DNS zone** → **DNS records** → **Add record**

### Typical pattern (use Firebase’s values, not these guesses)

| Type | Name | Value |
|------|------|--------|
| TXT | (as Firebase shows) | ownership string |
| A | `@` | Firebase IP(s) |
| CNAME | `www` | (as Firebase shows) |

Delete or replace old **parked-domain** A/CNAME records that conflict.

6. Click **Verify** / wait in Firebase until status is **Connected**
7. SSL is automatic on Firebase (no Hostinger SSL needed)

## After DNS is connected

Your blog will be at: **https://sattvasrsti.blog/**
