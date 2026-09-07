/**
 * Blog renderer: blog_posts (editorial) + recipes_v2 (teaser join at display time).
 * No local JSON fallback. Ayurveda omitted on blog (Phase 1).
 */
(async function () {
  const Fs = window.SattvaFs;
  const TEASER = window.SATTVA_TEASER || {};
  const Teaser = window.SattvaTeaserDisplay || {};
  const APP_BASE = "https://sattvasrsti.com/recipe";
  const CUSTOMIZE_FALLBACK = {
    title: "Cook the full recipe on SattvaSrsti",
    body: "When you are ready for every step, open the full recipe on SattvaSrsti — adjust ingredients, spice, and servings to match your kitchen.",
    cta_label: "Open full recipe on SattvaSrsti",
  };

  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const slug = params.get("slug") || "why-is-my-mysore-masala-dosa-not-crispy";

  function appUrl(recipeSlug, campaign, content) {
    const u = new URL(`${APP_BASE}/${recipeSlug}`);
    u.searchParams.set("utm_source", "blog");
    u.searchParams.set("utm_medium", "cta");
    u.searchParams.set("utm_campaign", campaign || slug);
    u.searchParams.set("utm_content", content);
    return u.toString();
  }

  function setMeta(sel, attr, value) {
    const el = document.querySelector(sel);
    if (el && value) el.setAttribute(attr, value);
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  const ROLE_LABELS = {
    base: "Base",
    protein: "Protein",
    spice: "Spices",
    aromatic: "Aromatics",
    fat: "Fats & oils",
    liquid: "Liquids",
    acid: "Acids",
    garnish: "Garnish",
  };
  const ROLE_ORDER = ["base", "protein", "spice", "aromatic", "fat", "liquid", "acid", "garnish"];

  function roleLabel(role) {
    const key = String(role || "").toLowerCase();
    if (ROLE_LABELS[key]) return ROLE_LABELS[key];
    if (!key) return "Other";
    return key.charAt(0).toUpperCase() + key.slice(1);
  }

  function groupIngredients(ings) {
    const groups = {};
    (ings || []).forEach((it) => {
      const name = it.display_name || it.name || "Ingredient";
      const notes = [];
      if (it.preparation_state && it.preparation_state !== "raw") notes.push(it.preparation_state);
      if ((it.requirement_level || "").toLowerCase() === "optional") notes.push("optional");
      const row = {
        amount: it.amount,
        unit: it.unit,
        canonical_amount: it.canonical_amount,
        canonical_unit: it.canonical_unit,
        name,
        note: notes.length ? notes.join(", ") : null,
      };
      const roleKey = String(it.ingredient_role || "other").toLowerCase();
      if (!groups[roleKey]) groups[roleKey] = [];
      groups[roleKey].push(row);
    });
    const orderedKeys = [
      ...ROLE_ORDER.filter((k) => groups[k] && groups[k].length),
      ...Object.keys(groups).filter((k) => !ROLE_ORDER.includes(k)),
    ];
    return orderedKeys.map((key) => ({ name: roleLabel(key), items: groups[key] }));
  }

  function formatAmount(item, mode) {
    if (mode === "grams") {
      const amt = item.canonical_amount;
      const unit = item.canonical_unit || "g";
      if (amt === null || amt === undefined || amt === "") {
        return [item.amount, item.unit].filter((x) => x !== null && x !== undefined && x !== "").join(" ");
      }
      return `${amt} ${unit}`;
    }
    return [item.amount, item.unit].filter((x) => x !== null && x !== undefined && x !== "").join(" ");
  }

  function previewSteps(steps) {
    return (steps || []).map((s, i) => {
      const text = s.instruction_text || s.text || "";
      const low = text.toLowerCase();
      let label = `Step ${i + 1}`;
      if (low.startsWith("rinse") || low.startsWith("soak")) label = "Prep";
      else if (low.startsWith("boil")) label = "Boil";
      else if (low.includes("grind")) label = "Grind";
      else if (low.includes("mash") || low.includes("filling")) label = "Fill";
      else if (low.includes("dough") || low.includes("knead")) label = "Dough";
      else if (low.includes("roll")) label = "Roll";
      else if (low.includes("cook") || low.includes("pan") || low.includes("tawa")) label = "Cook";
      return { label, text };
    });
  }

  function hashtagsFromRecipe(root, title) {
    const tags = ["#SattvaSrsti", "#SattvaSrstiRecipes", "#CookWithSattva"];
    const clean = String(title || "")
      .replace(/[^a-zA-Z0-9 ]/g, "")
      .replace(/\s+/g, "");
    if (clean) tags.push("#" + clean);
    (root.search_tags || []).slice(0, 3).forEach((t) => {
      const p = String(t)
        .replace(/[^a-zA-Z0-9 ]/g, "")
        .replace(/\s+/g, "");
      if (p) tags.push("#" + p);
    });
    return [...new Set(tags)];
  }

  function normalizeStory(story) {
    if (Array.isArray(story)) return story.map((t) => String(t || "").trim()).filter(Boolean);
    if (typeof story === "string" && story.trim()) return [story.trim()];
    return [];
  }

  function normalizeQa(item) {
    if (!item || typeof item !== "object") return null;
    const q = item.q || item.question;
    const a = item.a || item.answer;
    if (!q || !a) return null;
    return { q: String(q).trim(), a: String(a).trim() };
  }

  function buildFaqList(blog, H) {
    const relatedRaw = H.related_problems || H.common_questions || [];
    const related = relatedRaw.map(normalizeQa).filter(Boolean);
    const primaryQ = blog.primary_question || H.primary_question || "";
    let useful = H.useful_answer || "";
    if (useful && typeof useful === "object") {
      useful = useful.text || useful.answer || useful.useful_answer || "";
    }
    const faqs = [];
    const pqKey = String(primaryQ).toLowerCase().replace(/[^a-z0-9\s]/g, "").trim();
    if (primaryQ && useful) {
      faqs.push({ q: String(primaryQ).trim(), a: String(useful).trim() });
    }
    for (const qa of related) {
      const key = qa.q.toLowerCase().replace(/[^a-z0-9\s]/g, "").trim();
      if (pqKey && key === pqKey) continue;
      faqs.push(qa);
      if (faqs.length >= 5) break;
    }
    return faqs;
  }

  function notFoundPage() {
    document.body.innerHTML = `<main style="padding:2rem;font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto">
      <p><a href="./index.html">← SattvaSrsti Blog</a></p>
      <h1>Post not found</h1>
      <p>No blog post matches <code>${escapeHtml(slug)}</code>.</p>
      <p><a href="./index.html#posts">Browse all posts</a></p>
    </main>`;
  }

  let blog;
  try {
    blog = await Fs.getBlogPostBySlug(slug);
  } catch (_) {
    notFoundPage();
    return;
  }

  if (!blog || !blog.recipe_id) {
    document.body.innerHTML = `<main style="padding:2rem"><h1>Blog missing recipe_id</h1></main>`;
    return;
  }

  const H = blog.humanized || {};
  const recipeId = blog.recipe_id;

  let root;
  let ingDoc;
  let instDoc;
  try {
    root = await Fs.getRecipeRoot(recipeId);
    ingDoc = await Fs.getDocSoft(`recipes_v2/${recipeId}/ingredients/details`);
    instDoc = await Fs.getDocSoft(`recipes_v2/${recipeId}/instructions/details`);
  } catch (_) {
    document.body.innerHTML = `<main style="padding:2rem"><h1>Could not load recipe data</h1><p><a href="./index.html">Back to blog</a></p></main>`;
    return;
  }

  const ingredients = (ingDoc && ingDoc.ingredients) || [];
  const steps = (instDoc && instDoc.steps) || [];
  const storage = (instDoc && instDoc.leftover_storage) || {};

  const related = [];
  try {
    const allPosts = await Fs.listReadyBlogPosts();
    const candidates = allPosts.filter((p) => p.recipe_id !== recipeId && p.slug !== slug);
    const enriched = await Promise.all(candidates.slice(0, 8).map((p) => Fs.enrichCard(p)));
    related.push(...enriched.slice(0, 4));
  } catch (_) {
    /* related optional */
  }

  const title = root.title || "Recipe";
  const recipeSlug = root.slug || title.toLowerCase().replace(/\s+/g, "-");
  const diet = root.diet_tags || [];
  const veg = diet.some((d) => String(d).toLowerCase().includes("vegetarian")) ? "Vegetarian" : "";
  const eyebrow = [root.cuisine, root.meal_type, veg].filter(Boolean).join(" · ");
  const total =
    root.total_time_minutes ||
    (root.prep_time_minutes || 0) + (root.cook_time_minutes || 0) ||
    null;
  const servings =
    (root.base_yield && root.base_yield.servings) ||
    (ingDoc && ingDoc.base_yield && ingDoc.base_yield.servings) ||
    1;
  const metaPills = [
    total ? `${total} min` : null,
    root.difficulty || null,
    root.spice_tolerance_level ? `Spice: ${root.spice_tolerance_level}` : null,
    servings ? `${servings} serving` : null,
  ].filter(Boolean);

  const seoTitle = blog.seo_title || `${blog.primary_question} | SattvaSrsti`;
  const metaDesc = blog.meta_description || H.meta_description || blog.primary_question;
  const canonical = blog.blog_public_url || "";
  const imageUrl = root.image_primary_url || "";
  const cf = blog.customize_fixed || CUSTOMIZE_FALLBACK;
  const faqs = buildFaqList(blog, H);
  const storyParas = normalizeStory(H.story);
  const relatedFaqs = faqs.length > 1 ? faqs.slice(1) : faqs;
  const hashtags = hashtagsFromRecipe(root, title);
  const shareUrl = canonical || (typeof location !== "undefined" ? location.href : "");

  document.title = seoTitle;
  setMeta('meta[name="description"]', "content", metaDesc);
  setMeta('link[rel="canonical"]', "href", canonical);
  setMeta('meta[property="og:title"]', "content", seoTitle);
  setMeta('meta[property="og:description"]', "content", metaDesc);
  setMeta('meta[property="og:image"]', "content", imageUrl);
  setMeta('meta[property="og:url"]', "content", canonical);
  setMeta('meta[name="twitter:title"]', "content", seoTitle);
  setMeta('meta[name="twitter:description"]', "content", metaDesc);
  setMeta('meta[name="twitter:image"]', "content", imageUrl);

  $("jsonld-article").textContent = JSON.stringify({
    "@context": "https://schema.org",
    "@type": "Article",
    headline: blog.primary_question,
    description: metaDesc,
    image: imageUrl ? [imageUrl] : [],
  });
  if (faqs.length) {
    $("jsonld-faq").textContent = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: faqs.map((qa) => ({
        "@type": "Question",
        name: qa.q,
        acceptedAnswer: { "@type": "Answer", text: qa.a },
      })),
    });
  }

  $("breadcrumbs").innerHTML = [
    `<a href="./index.html">Home</a><span class="sep">/</span>`,
    `<a href="./index.html#posts">Blog</a><span class="sep">/</span>`,
    `<span aria-current="page">${escapeHtml(title)}</span>`,
  ].join("");

  $("hero-eyebrow").textContent = eyebrow;
  $("hero-title").textContent = blog.primary_question;
  $("hero-hook").textContent = H.hook || "";
  $("hero-image").src = imageUrl;
  $("hero-image").alt = `${title} from SattvaSrsti`;
  $("meta-pills").innerHTML = metaPills.map((p) => `<span>${escapeHtml(p)}</span>`).join("");

  ["cta-hero", "cta-preview", "cta-final", "nav-app", "cta-customize", "cta-sticky"].forEach((id) => {
    const el = $(id);
    if (el) el.href = appUrl(recipeSlug, slug, id);
  });
  $("cta-hero").textContent = "Cook & customize on SattvaSrsti";
  $("cta-preview").textContent = "Continue in SattvaSrsti";
  const stickyCta = $("cta-sticky");
  if (stickyCta) stickyCta.textContent = "Cook & customize on SattvaSrsti";
  $("cta-final").textContent = "Open full recipe & customize";

  $("story").innerHTML = `<p class="type-kicker">Story</p><h2 class="type-display">The scene</h2>${storyParas.map((t) => `<p class="type-prose">${escapeHtml(t)}</p>`).join("")}`;
  {
    let usefulText = H.useful_answer || "";
    if (usefulText && typeof usefulText === "object") {
      usefulText = usefulText.text || usefulText.answer || usefulText.useful_answer || "";
    }
    $("useful-answer").innerHTML = `<p class="type-kicker type-kicker-gold">Fix</p><h2 class="type-display">The short answer</h2><p class="type-prose type-prose-emphasis">${escapeHtml(usefulText)}</p>`;
  }
  $("about").innerHTML = `<p class="type-kicker">Context</p><h2 class="type-display">Why this dish is cooked this way</h2><p class="type-prose">${escapeHtml(root.about_recipe || "")}</p>`;

  const groupedFull = groupIngredients(ingredients);
  const capped = Teaser.capIngredientGroups
    ? Teaser.capIngredientGroups(groupedFull, TEASER.ingredientShowRatio)
    : { groups: groupedFull, total: ingredients.length, shown: ingredients.length, hidden: 0 };
  const grouped = capped.groups;
  let unitMode = "recipe";

  function renderIngredientGroups() {
    const groupsEl = $("ingredient-groups");
    groupsEl.innerHTML = "";
    grouped.forEach((g, idx) => {
      const wrap = document.createElement("details");
      wrap.className = "ingredient-group";
      wrap.open = idx === 0;
      wrap.innerHTML = `<summary>${escapeHtml(g.name)}</summary>`;
      const ul = document.createElement("ul");
      ul.className = "ingredient-list";
      g.items.forEach((item) => {
        const li = document.createElement("li");
        const amt = formatAmount(item, unitMode);
        li.innerHTML = `<span>${escapeHtml(amt)}</span><span>${escapeHtml(item.name)}${item.note ? ` <em>(${escapeHtml(item.note)})</em>` : ""}</span>`;
        ul.appendChild(li);
      });
      wrap.appendChild(ul);
      groupsEl.appendChild(wrap);
    });
    if (capped.hidden > 0) {
      const note = document.createElement("p");
      note.className = "fine ing-lock-note";
      note.textContent = `${capped.hidden} more ingredient${capped.hidden === 1 ? "" : "s"} in the full SattvaSrsti recipe.`;
      groupsEl.appendChild(note);
    }
  }

  $("ing-servings").textContent = `For ${servings} serving · amounts from the SattvaSrsti recipe`;
  document.querySelectorAll("[data-unit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      unitMode = btn.getAttribute("data-unit") === "grams" ? "grams" : "recipe";
      document.querySelectorAll("[data-unit]").forEach((b) => {
        b.classList.toggle("is-active", b === btn);
        b.setAttribute("aria-pressed", b === btn ? "true" : "false");
      });
      renderIngredientGroups();
    });
  });
  renderIngredientGroups();

  const maxSteps = TEASER.maxPreviewSteps || 4;
  const previewed = Teaser.previewStepsLimited
    ? Teaser.previewStepsLimited(steps, maxSteps, previewSteps)
    : previewSteps((steps || []).slice(0, maxSteps));
  $("step-list").innerHTML = previewed
    .map((s) => `<li><strong>${escapeHtml(s.label)}</strong><p>${escapeHtml(s.text)}</p></li>`)
    .join("");

  const hiddenSteps = Math.max(0, (steps || []).length - maxSteps);
  const lockParts = [];
  if (hiddenSteps > 0) {
    lockParts.push(`${hiddenSteps} more step${hiddenSteps === 1 ? "" : "s"}`);
  }
  lockParts.push("the full customized recipe");
  $("lock-note").textContent = `Open SattvaSrsti for ${lockParts.join(" and ")} when you are ready to cook through.`;

  $("related-problems").innerHTML = `<p class="type-kicker">FAQ</p><h2 class="type-display">Related problems</h2>
    <p class="type-info-sub faq-intro">Real questions people ask — answered the SattvaSrsti way.</p>
    <div class="faq-list">${relatedFaqs
      .map(
        (qa) =>
          `<details class="faq-item"><summary>${escapeHtml(qa.q)}</summary><p>${escapeHtml(qa.a)}</p></details>`
      )
      .join("")}</div>`;

  $("customize-title").textContent = cf.title;
  $("customize-body").textContent = cf.body;
  $("cta-customize").textContent = cf.cta_label || "Customize & cook on SattvaSrsti";

  $("nutrition").innerHTML = "";
  $("nutrition").hidden = true;

  $("ayurveda").innerHTML = "";
  $("ayurveda").hidden = true;

  if (TEASER.showPairings !== false) {
    const pairings = root.pairing_recommendations || [];
    $("pairings").innerHTML = `<p class="type-kicker">Serve with</p><h2 class="type-info-title">What goes well with it</h2><ul class="pairing-list">${pairings
      .map((i) => `<li>${escapeHtml(String(i).replace(/_/g, " "))}</li>`)
      .join("")}</ul>`;
  } else {
    $("pairings").hidden = true;
  }

  if (TEASER.showStorage !== false) {
    $("storage").innerHTML = `<p class="type-kicker">Keep</p><h2 class="type-info-title">Storage</h2><ul class="plain-list">
      <li>${escapeHtml(storage.refrigeration || storage.fridge || "Store in an airtight container in the fridge.")}</li>
      <li>${escapeHtml(storage.reheat || "Reheat on a pan or microwave until warm.")}</li>
      <li>${escapeHtml(storage.shelf_life || storage.duration || "Consume within 2 days.")}</li>
    </ul>`;
  } else {
    $("storage").hidden = true;
  }

  $("emotional-ending").textContent = H.emotional_ending || "";

  if (related.length) {
    $("related").hidden = false;
    $("related-grid").innerHTML = related
      .slice(0, 4)
      .map(
        (r) => `<a class="related-card" href="./post.html?slug=${encodeURIComponent(r.slug)}">
          <img src="${escapeHtml(r.image_url || "")}" alt="" loading="lazy" />
          <div><strong>${escapeHtml(r.title)}</strong><span>${escapeHtml([r.cuisine, r.meal].filter(Boolean).join(" · ") || "Blog post")}</span></div></a>`
      )
      .join("");
  }

  const sharePayload = `${blog.primary_question} — ${shareUrl}`;
  const shareText = encodeURIComponent(sharePayload);
  const waApi = `https://api.whatsapp.com/send?text=${shareText}`;
  const waWeb = `https://web.whatsapp.com/send?text=${shareText}`;
  const fb = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`;
  const tw = `https://twitter.com/intent/tweet?text=${shareText}`;
  $("share-row").innerHTML = `
    <a class="share-btn" href="${waApi}" id="share-whatsapp" rel="noopener">WhatsApp</a>
    <a class="share-btn" href="${fb}" target="_blank" rel="noopener">Facebook</a>
    <a class="share-btn" href="${tw}" target="_blank" rel="noopener">X</a>
    <button type="button" class="share-btn share-copy" id="share-copy">Copy link</button>
  `;
  $("hashtags").textContent = hashtags.join(" ");
  $("social-note").textContent = "Share this post URL. Tags are only a caption helper.";

  const waBtn = $("share-whatsapp");
  if (waBtn) {
    waBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      // Native share sheet (mobile) — avoids WhatsApp Web login dead-ends
      if (typeof navigator.share === "function") {
        try {
          await navigator.share({
            title: document.title || "SattvaSrsti Blog",
            text: blog.primary_question || "SattvaSrsti Blog",
            url: shareUrl,
          });
          return;
        } catch (err) {
          if (err && err.name === "AbortError") return;
        }
      }
      const mobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || "");
      // Desktop: open WhatsApp Web send URL in THIS tab so an existing web.whatsapp.com
      // login is reused and the text= param is not lost after a new-tab QR login.
      // Mobile: api.whatsapp.com hands off to the app (contact picker).
      const href = mobile ? waApi : waWeb;
      window.location.assign(href);
    });
  }

  const copyBtn = $("share-copy");
  if (copyBtn) {
    copyBtn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(shareUrl);
        copyBtn.textContent = "Copied";
        setTimeout(() => {
          copyBtn.textContent = "Copy link";
        }, 1600);
      } catch (_) {}
    };
  }
})();
