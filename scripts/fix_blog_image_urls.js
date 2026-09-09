#!/usr/bin/env node
/**
 * Replace stale Storage generation URLs on blog_posts with live download-token URLs.
 * Does not print credentials.
 */
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { UserRefreshClient } = require("../functions/node_modules/google-auth-library");

const PROJECT_ID = "sattva-srsti";
const BUCKET = "sattva-srsti.appspot.com";
const FS_BASE = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents`;
const CLIENT_ID =
  process.env.FIREBASE_CLIENT_ID ||
  "563584335869-fgrhgmd47bqnekij5i8b5pr03hoak96q.apps.googleusercontent.com";
const CLIENT_SECRET = process.env.FIREBASE_CLIENT_SECRET || "9teEEZZmn42zvqiAbKdWjriV";

function loadCliTokens() {
  const configPath = path.join(os.homedir(), ".config", "configstore", "firebase-tools.json");
  const raw = JSON.parse(fs.readFileSync(configPath, "utf8"));
  const tokens = raw && raw.tokens;
  if (!tokens || !tokens.access_token) throw new Error("Firebase CLI is not logged in");
  return tokens;
}

async function accessToken() {
  const tokens = loadCliTokens();
  if (Number(tokens.expires_at || 0) > Date.now() + 60 * 1000) return tokens.access_token;
  const oauth = new UserRefreshClient(CLIENT_ID, CLIENT_SECRET, tokens.refresh_token);
  const got = await oauth.getAccessToken();
  const token = typeof got === "string" ? got : got && got.token;
  if (!token) throw new Error("Could not refresh Google access token");
  return token;
}

function toFs(v) {
  return { stringValue: String(v) };
}

function fromFs(v) {
  if (v == null) return null;
  if ("stringValue" in v) return v.stringValue;
  if ("mapValue" in v) {
    const out = {};
    const f = (v.mapValue && v.mapValue.fields) || {};
    for (const k of Object.keys(f)) out[k] = fromFs(f[k]);
    return out;
  }
  return null;
}

function docFields(doc) {
  const f = doc.fields || {};
  const out = {};
  for (const k of Object.keys(f)) out[k] = fromFs(f[k]);
  return out;
}

async function jsonReq(token, method, url, body) {
  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${res.status}: ${text.slice(0, 400)}`);
  return text ? JSON.parse(text) : {};
}

async function urlLoads(url) {
  if (!url) return false;
  try {
    const res = await fetch(url, { method: "HEAD" });
    const ct = res.headers.get("content-type") || "";
    return res.ok && (ct.includes("image") || ct.includes("octet-stream") || !ct);
  } catch (_) {
    return false;
  }
}

function tokenUrl(objectPath, downloadToken) {
  const encoded = encodeURIComponent(objectPath);
  return `https://firebasestorage.googleapis.com/v0/b/${BUCKET}/o/${encoded}?alt=media&token=${downloadToken}`;
}

async function tokenUrlForRecipe(token, recipeId) {
  const objectPath = `recipe_v1_image/${recipeId}.jpg`;
  const metaUrl = `https://storage.googleapis.com/storage/v1/b/${BUCKET}/o/${encodeURIComponent(objectPath)}`;
  const meta = await jsonReq(token, "GET", metaUrl);
  let download =
    (meta.metadata && (meta.metadata.firebaseStorageDownloadTokens || meta.metadata.firebaseStorageDownloadToken)) ||
    "";
  let first = String(download).split(",")[0].trim();
  if (!first) {
    first = crypto.randomUUID();
    const nextMeta = { ...(meta.metadata || {}), firebaseStorageDownloadTokens: first };
    await jsonReq(token, "PATCH", `${metaUrl}?fields=metadata`, { metadata: nextMeta });
  }
  return tokenUrl(objectPath, first);
}

async function listPosts(token) {
  const out = [];
  let url = `${FS_BASE}/blog_posts?pageSize=100`;
  while (url) {
    const raw = await jsonReq(token, "GET", url);
    for (const doc of raw.documents || []) {
      out.push({ id: doc.name.split("/").pop(), fields: docFields(doc) });
    }
    if (!raw.nextPageToken) break;
    url = `${FS_BASE}/blog_posts?pageSize=100&pageToken=${encodeURIComponent(raw.nextPageToken)}`;
  }
  return out;
}

async function main() {
  const token = await accessToken();
  const posts = await listPosts(token);
  let fixed = 0;
  let skipped = 0;
  const failed = [];
  for (const post of posts) {
    const rid = post.fields.recipe_id;
    const current = post.fields.image_url || (post.fields.display && post.fields.display.image_url) || "";
    const stale = !current || current.includes("generation=") || !(await urlLoads(current));
    if (!rid) {
      skipped += 1;
      continue;
    }
    if (!stale) {
      skipped += 1;
      continue;
    }
    try {
      const next = await tokenUrlForRecipe(token, rid);
      if (!(await urlLoads(next))) throw new Error(`token url still fails: ${next}`);
      const mask = ["image_url", "display.image_url"].map((f) => `updateMask.fieldPaths=${encodeURIComponent(f)}`).join("&");
      await jsonReq(token, "PATCH", `${FS_BASE}/blog_posts/${post.id}?${mask}`, {
        fields: {
          image_url: toFs(next),
          display: { mapValue: { fields: { image_url: toFs(next) } } },
        },
      });
      const recipeUrl = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents/recipes_v2/${rid}?updateMask.fieldPaths=image_primary_url`;
      try {
        await jsonReq(token, "PATCH", recipeUrl, {
          fields: { image_primary_url: toFs(next) },
        });
      } catch (err) {
        console.log(`warn recipe ${rid}: ${err.message}`);
      }
      fixed += 1;
      console.log(`OK ${post.fields.slug || post.id}`);
    } catch (err) {
      failed.push({ id: post.id, rid, error: String(err.message || err) });
      console.log(`FAIL ${post.fields.slug || post.id}: ${err.message}`);
    }
  }
  console.log(JSON.stringify({ fixed, skipped, failed }, null, 2));
}

main().catch((err) => {
  console.error(String(err && err.message ? err.message : err));
  process.exit(1);
});
