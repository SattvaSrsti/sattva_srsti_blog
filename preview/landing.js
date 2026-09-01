/**
 * Blog landing: hero carousel + searchable post grid from Firestore blog_posts.
 * One card per recipe (duplicates hidden until Firestore cleanup runs).
 */
(async function () {
  const grid = document.getElementById("post-grid");
  const hero = document.getElementById("hero-visual");
  const searchInput = document.getElementById("post-search");
  const headerSearch = document.getElementById("header-search");
  const searchMeta = document.getElementById("search-meta");
  const Fs = window.SattvaFs;
  let allPosts = [];

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function highlightMatch(text, query) {
    const raw = String(text || "");
    const q = String(query || "").trim();
    if (!q || q.length < 2) return escapeHtml(raw);
    const norm = q.toLowerCase();
    const low = raw.toLowerCase();
    const idx = low.indexOf(norm);
    if (idx === -1) return escapeHtml(raw);
    return (
      escapeHtml(raw.slice(0, idx)) +
      `<mark class="search-hit">${escapeHtml(raw.slice(idx, idx + q.length))}</mark>` +
      escapeHtml(raw.slice(idx + q.length))
    );
  }

  function startHeroCarousel(images) {
    const urls = (images || []).filter(Boolean);
    if (!urls.length || !hero) return;
    let idx = 0;
    hero.style.backgroundImage = `linear-gradient(145deg, rgba(42,64,51,0.15), rgba(184,107,69,0.18)), url("${urls[0]}")`;
    hero.style.backgroundSize = "cover";
    hero.style.backgroundPosition = "center";
    if (urls.length === 1) return;
    setInterval(() => {
      idx = (idx + 1) % urls.length;
      hero.style.backgroundImage = `linear-gradient(145deg, rgba(42,64,51,0.15), rgba(184,107,69,0.18)), url("${urls[idx]}")`;
    }, 4500);
  }

  function getQuery() {
    const el = searchInput || headerSearch;
    return (el && el.value || "").trim();
  }

  function syncSearchInputs(from) {
    const q = from ? from.value : getQuery();
    if (searchInput && searchInput !== from) searchInput.value = q;
    if (headerSearch && headerSearch !== from) headerSearch.value = q;
  }

  function renderPosts(posts, query) {
    if (!posts.length) {
      grid.innerHTML = `<p class="fine">No posts match “${escapeHtml(query)}”. Try a recipe name like <em>Idli</em> or a problem like <em>soggy</em> or <em>not crispy</em>.</p>`;
      return;
    }
    grid.innerHTML = posts
      .map(
        (p) => `<a class="post-card" href="./post.html?slug=${encodeURIComponent(p.slug)}">
          <img src="${escapeHtml(p.image_url)}" alt="" loading="lazy" width="640" height="420" />
          <div class="post-card-body">
            <span class="post-meta">${[p.cuisine, p.meal].filter(Boolean).map(escapeHtml).join(" · ")}</span>
            ${p.recipe_title ? `<span class="post-recipe">${highlightMatch(p.recipe_title, query)}</span>` : ""}
            <strong>${highlightMatch(p.title, query)}</strong>
            <span>${escapeHtml(p.hook || "")}</span>
          </div>
        </a>`
      )
      .join("");
  }

  function applySearch(from) {
    syncSearchInputs(from);
    const q = getQuery();
    const filtered = !q ? allPosts : allPosts.filter((p) => Fs.matchesSearch(p, q));
    if (searchMeta) {
      searchMeta.textContent = q
        ? `${filtered.length} of ${allPosts.length} posts`
        : `${allPosts.length} posts`;
    }
    renderPosts(filtered, q);
    if (q && location.hash !== "#posts") {
      history.replaceState(null, "", "#posts");
    }
  }

  function bindSearch(el) {
    if (!el) return;
    el.addEventListener("input", () => applySearch(el));
    el.addEventListener("search", () => applySearch(el));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        document.getElementById("posts")?.scrollIntoView({ behavior: "smooth", block: "start" });
        applySearch(el);
      }
    });
  }

  bindSearch(searchInput);
  bindSearch(headerSearch);

  try {
    allPosts = await Fs.listReadyBlogPosts();
    allPosts = await Promise.all(allPosts.map((p) => Fs.enrichCard(p)));
    allPosts.sort((a, b) => String(a.recipe_title || a.title).localeCompare(String(b.recipe_title || b.title)));

    const urlQ = new URLSearchParams(location.search).get("q");
    if (urlQ) {
      if (searchInput) searchInput.value = urlQ;
      if (headerSearch) headerSearch.value = urlQ;
    }

    startHeroCarousel(allPosts.map((p) => p.image_url));

    if (!allPosts.length) {
      grid.innerHTML = `<p class="fine">No posts yet.</p>`;
      return;
    }
    applySearch();

    if (urlQ || location.hash === "#posts") {
      document.getElementById("posts")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (err) {
    grid.innerHTML = `<p>Could not load posts. <code>${escapeHtml(String(err))}</code></p>`;
  }
})();
