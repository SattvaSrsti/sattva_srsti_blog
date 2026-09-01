/** Firestore REST client for public blog (read-only). */
(function () {
  const FS =
    "https://firestore.googleapis.com/v1/projects/sattva-srsti/databases/(default)/documents";
  const docCache = Object.create(null);
  const listCache = Object.create(null);

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
    if (docCache[path]) return docCache[path];
    const res = await fetch(`${FS}/${path}`);
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
    const key = `${collection}:${pageSize || 100}`;
    if (listCache[key]) return listCache[key];
    const out = [];
    let url = `${FS}/${collection}?pageSize=${pageSize || 100}`;
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
      url = `${FS}/${collection}?pageSize=${pageSize || 100}&pageToken=${encodeURIComponent(token)}`;
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
    const related_questions = relatedQuestionTexts(fields);
    const card = {
      slug: fields.slug,
      title: fields.primary_question || H.primary_question || fields.slug,
      hook: H.hook || "",
      recipe_id: fields.recipe_id,
      recipe_title: (extra && extra.recipe_title) || fields.recipe_title || "",
      image_url: fields.image_url || "",
      cuisine: fields.cuisine || "",
      meal: fields.meal_type || fields.meal || "",
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

  async function getBlogPostBySlug(slug) {
    try {
      return await getDoc(`blog_posts/blog_${slug}`);
    } catch (_) {
      const docs = await listCollection("blog_posts");
      for (const d of docs) {
        if (d.fields.slug === slug) return d.fields;
      }
      throw new Error("not_found");
    }
  }

  async function getRecipeRoot(recipeId) {
    return getDoc(`recipes_v2/${recipeId}`);
  }

  async function enrichCard(card) {
    if (card.image_url && card.cuisine && card.recipe_title) {
      card._searchText = buildSearchText(card);
      return card;
    }
    if (!card.recipe_id) return card;
    const root = await getDocSoft(`recipes_v2/${card.recipe_id}`);
    if (!root) return card;
    const enriched = {
      ...card,
      recipe_title: card.recipe_title || root.title || "",
      image_url: card.image_url || root.image_primary_url || "",
      cuisine: card.cuisine || root.cuisine || "",
      meal: card.meal || root.meal_type || "",
    };
    enriched._searchText = buildSearchText(enriched);
    return enriched;
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
    getRecipeRoot,
    enrichCard,
    clearCache() {
      Object.keys(docCache).forEach((k) => delete docCache[k]);
      Object.keys(listCache).forEach((k) => delete listCache[k]);
    },
  };
})();
