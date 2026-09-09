#!/usr/bin/env node
/**
 * Copy 70% ingredient / 4-step teasers onto blog_posts using the logged-in Firebase CLI user.
 * Full recipes stay in recipes_v2. Does not print credentials.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { UserRefreshClient } = require("../functions/node_modules/google-auth-library");
const { displayTeaserFromParts } = require("../functions/blog_reconcile");

const PROJECT_ID = "sattva-srsti";
const FN_URL = "https://us-central1-sattva-srsti.cloudfunctions.net/blogAttachTeasersManual";
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

function tokenStillValid(tokens) {
  const exp = Number(tokens.expires_at || 0);
  return exp > Date.now() + 60 * 1000;
}

function toFs(v) {
  if (v === null || v === undefined) return { nullValue: null };
  if (typeof v === "string") return { stringValue: v };
  if (typeof v === "boolean") return { booleanValue: v };
  if (typeof v === "number") {
    return Number.isInteger(v) ? { integerValue: String(v) } : { doubleValue: v };
  }
  if (Array.isArray(v)) return { arrayValue: { values: v.map(toFs) } };
  if (typeof v === "object") {
    const fields = {};
    for (const [k, val] of Object.entries(v)) fields[k] = toFs(val);
    return { mapValue: { fields } };
  }
  return { stringValue: String(v) };
}

function fromFs(v) {
  if (v == null) return null;
  if ("stringValue" in v) return v.stringValue;
  if ("integerValue" in v) return Number(v.integerValue);
  if ("doubleValue" in v) return Number(v.doubleValue);
  if ("booleanValue" in v) return v.booleanValue;
  if ("nullValue" in v) return null;
  if ("arrayValue" in v) return (v.arrayValue.values || []).map(fromFs);
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

async function listCollection(token, collection) {
  const out = [];
  let url = `${FS_BASE}/${collection}?pageSize=100`;
  while (url) {
    const raw = await fsJson(token, "GET", url);
    for (const doc of raw.documents || []) {
      out.push({ id: doc.name.split("/").pop(), fields: docFields(doc) });
    }
    if (!raw.nextPageToken) break;
    url = `${FS_BASE}/${collection}?pageSize=100&pageToken=${encodeURIComponent(raw.nextPageToken)}`;
  }
  return out;
}

async function getDocSoft(token, docPath) {
  try {
    return docFields(await fsJson(token, "GET", `${FS_BASE}/${docPath}`));
  } catch (_) {
    return null;
  }
}

async function main() {
  const tokens = loadCliTokens();
  let token = tokenStillValid(tokens) ? tokens.access_token : null;
  if (!token) {
    const oauth = new UserRefreshClient(CLIENT_ID, CLIENT_SECRET, tokens.refresh_token);
    const got = await oauth.getAccessToken();
    token = typeof got === "string" ? got : got && got.token;
  }
  if (!token) throw new Error("Could not refresh Google access token");

  const authHeaders = [tokens.id_token, token].filter(Boolean);
  let fnText = "";
  let fnOk = false;
  for (const hdr of authHeaders) {
    const fnRes = await fetch(FN_URL, {
      method: "POST",
      headers: { Authorization: `Bearer ${hdr}` },
    });
    fnText = await fnRes.text();
    if (fnRes.ok) {
      fnOk = true;
      break;
    }
    console.log(`Function ${fnRes.status}`);
  }
  if (fnOk) {
    console.log(fnText);
    return;
  }
  console.log("Writing teasers via Firestore REST");

  const posts = await listCollection(token, "blog_posts");
  let updated = 0;
  let skipped = 0;
  const failed = [];
  for (const post of posts) {
    const rid = post.fields.recipe_id;
    if (!rid) {
      skipped += 1;
      continue;
    }
    try {
      const recipe = await getDocSoft(token, `recipes_v2/${rid}`);
      if (!recipe) {
        skipped += 1;
        continue;
      }
      recipe.id = rid;
      let ings = Array.isArray(recipe.ingredients) ? recipe.ingredients : [];
      let steps = [];
      let storage = {};
      const ingDoc = await getDocSoft(token, `recipes_v2/${rid}/ingredients/details`);
      if (ingDoc) ings = ingDoc.ingredients || ingDoc.items || ings;
      const instDoc = await getDocSoft(token, `recipes_v2/${rid}/instructions/details`);
      if (instDoc) {
        steps = instDoc.steps || [];
        storage = instDoc.leftover_storage || {};
      }
      const display = displayTeaserFromParts(recipe, ings, steps, storage);
      const mask = ["display", "recipe_title", "image_url", "cuisine", "meal_type"]
        .map((f) => `updateMask.fieldPaths=${encodeURIComponent(f)}`)
        .join("&");
      await fsJson(token, "PATCH", `${FS_BASE}/blog_posts/${post.id}?${mask}`, {
        fields: {
          display: toFs(display),
          recipe_title: toFs(display.recipe_title),
          image_url: toFs(display.image_url || post.fields.image_url || ""),
          cuisine: toFs(display.cuisine || post.fields.cuisine || ""),
          meal_type: toFs(display.meal_type || post.fields.meal_type || ""),
        },
      });
      updated += 1;
      process.stdout.write(".");
    } catch (err) {
      failed.push({ id: post.id, error: String(err.message || err) });
    }
  }
  console.log("");
  console.log(JSON.stringify({ updated, skipped, failed }, null, 2));
}

main().catch((err) => {
  console.error(String(err && err.message ? err.message : err));
  process.exit(1);
});
