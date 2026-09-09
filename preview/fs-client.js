/** Firestore REST client for public blog (read-only). */
(function () {
  const FS =
    "https://firestore.googleapis.com/v1/projects/sattva-srsti/databases/(default)/documents";
  const docCache = Object.create(null);
  const listCache = Object.create(null);
  const POST_FIELDS = [
    "status",
    "slug",
    "primary_question",
    "seo_title",
    "meta_description",
    "blog_public_url",
    "humanized",
    "customize_fixed",
    "recipe_id",
    "recipe_title",
    "image_url",
    "cuisine",
    "meal_type",
    "meal",
    "display",
    "community_questions",
    "research",
  ];
  const CARD_FIELDS = [
    "status",
    "slug",
    "primary_question",
    "humanized",
    "capability_id",
    "recipe_id",
    "recipe_title",
    "image_url",
    "cuisine",
    "meal_type",
    "meal",
  ];

  function withFieldMask(url, fieldPaths) {
    if (!fieldPaths || !fieldPaths.length) return url;
    const extra = fieldPaths.map((p) => `mask.fieldPaths=${encodeURIComponent(p)}`).join("&");
    return `${url}${url.includes("?") ? "&" : "?"}${extra}`;
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
      const f = v.mapValue.fields || {};
      Object.keys(f).forEach((k) => (out[k] = fromFs(f[k])));
      return out;
    }
    return null;
  }

  function docFields(doc) {
    const f = doc.fields || {};
    const out = {};
    Object.keys(f).forEach((k) => (out[k] = fromFs(f[k])));
    return out;
  }

  async function getDoc(path) {
    if (!String(path).startsWith("blog_posts/")) {
      throw new Error("public blog may only read blog_posts");
    }
    if (docCache[path]) return docCache[path];
    const res = await fetch(withFieldMask(`${FS}/${path}`, POST_FIELDS));
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    const fields = docFields(await res.json());
    docCache[path] = fields;
    return fields;
  }

  async function getDocSoft(path) {
    try {
      return await getDoc(path);
    } catch (_) {
      return null;
    }
  }

  async function listCollection(collection, pageSize) {
    if (collection !== "blog_posts") {
      throw new Error("public blog may only list blog_posts");
    }
    const key = `${collection}:${pageSize || 100}:cards`;
    if (listCache[key]) return listCache[key];
    const out = [];
    let url = withFieldMask(`${FS}/${collection}?pageSize=${pageSize || 100}`, CARD_FIELDS);
    while (url) {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${collection} list ${res.status}`);
      const raw = await res.json();
      for (const doc of raw.documents || []) {
        const id = doc.name.split("/").pop();
        out.push({ id, fields: docFields(doc), updateTime: doc.updateTime || "" });
      }
      const token = raw.nextPageToken;
      if (!token) break;
      url = withFieldMask(
        `${FS}/${collection}?pageSize=${pageSize || 100}&pageToken=${encodeURIComponent(token)}`,
        CARD_FIELDS
      );
    }
    listCache[key] = out;
    return out;
  }

  function isReadyPost(fields) {
    const st = (fields.status || "").toLowerCase();
    return st === "ready" || st === "published";
  }

  function blogQualityScore(fields) {
    const slug = String(fields.slug || "").toLowerCase();
    const pq = String(fields.primary_question || "").toLowerCase();
    let score = 0;
    if (fields.capability_id) score += 1000;
    const H = fields.humanized || {};
    if (H.related_problems && H.related_problems.length) score += 500;
    if (fields.research && fields.research.length) score += 200;
    if (slug.includes("-common-mistakes") || pq.includes("common mistakes")) score -= 1e6;
    if (slug.includes("not-turn-out-right") || pq.includes("not turn out right")) score -= 1e5;
    return score;
  }

  function relatedQuestionTexts(fields) {
    const H = fields.humanized || {};
    return (H.related_problems || [])
      .map((x) => (x && (x.q || x.question)) || "")
      .filter(Boolean);
  }

  function normalizeSearchText(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function buildSearchText(card) {
    return normalizeSearchText(
      [
        card.title,
        card.hook,
        card.recipe_title,
        card.cuisine,
        card.meal,
        card.slug,
        ...(card.related_questions || []),
      ].join(" ")
    );
  }

  function cardFromBlog(fields, extra) {
    const H = fields.humanized || {};
    const D = fields.display || {};
    const related_questions = relatedQuestionTexts(fields);
    const card = {
      slug: fields.slug,
      title: fields.primary_question || H.primary_question || fields.slug,
      hook: H.hook || "",
      recipe_id: fields.recipe_id,
      recipe_title: (extra && extra.recipe_title) || fields.recipe_title || D.recipe_title || "",
      image_url: fields.image_url || D.image_url || "",
      cuisine: fields.cuisine || D.cuisine || "",
      meal: fields.meal_type || fields.meal || D.meal_type || "",
      related_questions,
      _score: blogQualityScore(fields),
      _updateTime: (extra && extra.updateTime) || "",
    };
    card._searchText = buildSearchText(card);
    return card;
  }

  function dedupePostsByRecipe(docs) {
    const byRecipe = Object.create(null);
    for (const d of docs) {
      const rid = d.fields.recipe_id;
      if (!rid) continue;
      if (!byRecipe[rid]) byRecipe[rid] = [];
      byRecipe[rid].push(d);
    }
    const out = [];
    Object.keys(byRecipe).forEach((rid) => {
      const group = byRecipe[rid];
      group.sort((a, b) => {
        const sa = blogQualityScore(a.fields);
        const sb = blogQualityScore(b.fields);
        if (sb !== sa) return sb - sa;
        return String(b.updateTime).localeCompare(String(a.updateTime));
      });
      const best = group[0];
      out.push(cardFromBlog(best.fields, { updateTime: best.updateTime }));
    });
    return out;
  }

  async function listReadyBlogPosts() {
    const docs = await listCollection("blog_posts");
    const ready = docs.filter((d) => isReadyPost(d.fields));
    return dedupePostsByRecipe(ready);
  }

  const ASSET_NAME = /\.(html|js|css|xml|txt|png|jpe?g|webp|svg|json|ico|map)$/i;
  const RESERVED_PATHS = new Set(["", "index.html", "post.html", "robots.txt", "sitemap.xml"]);

  function publicPostUrl(slug) {
    const s = String(slug || "").replace(/^\/+/, "");
    return `https://sattvasrsti.blog/${encodeURIComponent(s)}`;
  }

  function isHostedBlog() {
    const h = typeof location === "undefined" ? "" : location.hostname;
    return (
      h === "sattvasrsti.blog" ||
      h === "www.sattvasrsti.blog" ||
      h.endsWith(".web.app") ||
      h.endsWith(".firebaseapp.com")
    );
  }

  function postHref(slug) {
    const s = String(slug || "").replace(/^\/+/, "");
    if (isHostedBlog()) return `/${encodeURIComponent(s)}`;
    return `./post.html?slug=${encodeURIComponent(s)}`;
  }

  function slugFromLocation() {
    const q = new URLSearchParams(location.search).get("slug");
    if (q && q.trim()) return q.trim();
    const parts = location.pathname.split("/").filter(Boolean);
    const last = decodeURIComponent(parts[parts.length - 1] || "");
    if (!last || RESERVED_PATHS.has(last.toLowerCase()) || ASSET_NAME.test(last)) return "";
    return last;
  }

  async function getBlogPostBySlug(slug) {
    try {
      return await getDoc(`blog_posts/blog_${slug}`);
    } catch (_) {
      const docs = await listCollection("blog_posts");
      for (const d of docs) {
        if (d.fields.slug === slug) return await getDoc(`blog_posts/${d.id}`);
      }
      throw new Error("not_found");
    }
  }

  function enrichCard(card) {
    card._searchText = buildSearchText(card);
    return card;
  }

  function matchesSearch(card, query) {
    const q = normalizeSearchText(query);
    if (!q) return true;
    const hay = card._searchText || buildSearchText(card);
    if (hay.includes(q)) return true;
    const tokens = q.split(" ").filter((t) => t.length > 0);
    return tokens.every((t) => hay.includes(t));
  }

  function searchHaystack(card) {
    return card._searchText || buildSearchText(card);
  }

  window.SattvaFs = {
    getDoc,
    getDocSoft,
    listCollection,
    listReadyBlogPosts,
    dedupePostsByRecipe,
    matchesSearch,
    getBlogPostBySlug,
    slugFromLocation,
    postHref,
    publicPostUrl,
    isHostedBlog,
    enrichCard,
    clearCache() {
      Object.keys(docCache).forEach((k) => delete docCache[k]);
      Object.keys(listCache).forEach((k) => delete listCache[k]);
    },
  };
})();
