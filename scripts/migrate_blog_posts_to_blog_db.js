#!/usr/bin/env node
/**
 * One-time: copy blog_posts (default) → blog database using Firebase CLI login.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { UserRefreshClient } = require("../functions/node_modules/google-auth-library");

const PROJECT_ID = "sattva-srsti";
const BLOG_DATABASE_ID = process.env.FIRESTORE_BLOG_DATABASE || "blog";
const SRC_BASE = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/(default)/documents`;
const DST_BASE = `https://firestore.googleapis.com/v1/projects/${PROJECT_ID}/databases/${BLOG_DATABASE_ID}/documents`;
const CLIENT_ID =
  process.env.FIREBASE_CLIENT_ID ||
  "563584335869-fgrhgmd47bqnekij5i8b5pr03hoak96q.apps.googleusercontent.com";
const CLIENT_SECRET = process.env.FIREBASE_CLIENT_SECRET || "9teEEZZmn42zvqiAbKdWjriV";

function loadCliTokens() {
  const configPath = path.join(os.homedir(), ".config", "configstore", "firebase-tools.json");
  const raw = JSON.parse(fs.readFileSync(configPath, "utf8"));
  const tokens = raw && raw.tokens;
  if (!tokens || !tokens.refresh_token) throw new Error("Firebase CLI is not logged in");
  return tokens;
}

async function accessToken(tokens) {
  if (tokens.access_token && Number(tokens.expires_at || 0) > Date.now() + 60_000) {
    return tokens.access_token;
  }
  const oauth = new UserRefreshClient(CLIENT_ID, CLIENT_SECRET, tokens.refresh_token);
  const got = await oauth.getAccessToken();
  return typeof got === "string" ? got : got && got.token;
}

async function fsJson(token, method, url, body) {
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

async function listAll(token, base, collection) {
  const out = [];
  let url = `${base}/${collection}?pageSize=100`;
  while (url) {
    const raw = await fsJson(token, "GET", url);
    for (const doc of raw.documents || []) {
      out.push(doc);
    }
    if (!raw.nextPageToken) break;
    url = `${base}/${collection}?pageSize=100&pageToken=${encodeURIComponent(raw.nextPageToken)}`;
  }
  return out;
}

async function main() {
  const token = await accessToken(loadCliTokens());
  const srcDocs = await listAll(token, SRC_BASE, "blog_posts");
  let copied = 0;
  let skipped = 0;
  for (const doc of srcDocs) {
    const id = doc.name.split("/").pop();
    const dstUrl = `${DST_BASE}/blog_posts/${id}`;
    try {
      await fsJson(token, "GET", dstUrl);
      skipped += 1;
      continue;
    } catch (_) {
      /* not found — copy */
    }
    await fsJson(token, "PATCH", dstUrl, { fields: doc.fields || {} });
    copied += 1;
    console.log(`  copied ${id}`);
  }
  console.log(`Done: copied=${copied} skipped=${skipped} target=${BLOG_DATABASE_ID}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
