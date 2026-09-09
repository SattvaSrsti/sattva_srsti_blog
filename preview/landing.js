/**
 * Blog landing: full-bleed hero, featured story, filters, searchable grid.
 * One card per recipe (duplicates hidden until Firestore cleanup runs).
 */
(async function () {
  const grid = document.getElementById("post-grid");
  const hero = document.getElementById("hero-visual");
  const headerSearch = document.getElementById("header-search");
  const searchMeta = document.getElementById("search-meta");
  const featuredBlock = document.getElementById("featured");
  const featuredSlot = document.getElementById("featured-slot");
  const filterChips = document.getElementById("filter-chips");
  const Fs = window.SattvaFs;
  let allPosts = [];
  let featuredSlug = "";
  let activeFilter = "all";

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
    const paint = (url) => {
      hero.style.backgroundImage = `url("${url}")`;
      hero.style.backgroundSize = "cover";
      hero.style.backgroundPosition = "center";
    };
    paint(urls[0]);
    hero.classList.add("is-ready");
    if (urls.length === 1) return;
    setInterval(() => {
      idx = (idx + 1) % urls.length;
      hero.classList.remove("is-ready");
      requestAnimationFrame(() => {
        paint(urls[idx]);
        hero.classList.add("is-ready");
      });
    }, 4500);
  }

  function getQuery() {
    return (headerSearch && headerSearch.value || "").trim();
  }

  function pickFeatured(posts) {
    if (!posts.length) return null;
    const ranked = [...posts].sort((a, b) => {
      const sa = Number(a._score) || 0;
      const sb = Number(b._score) || 0;
      if (sb !== sa) return sb - sa;
      return String(b._updateTime || "").localeCompare(String(a._updateTime || ""));
    });
    return ranked[0];
  }

  function renderFeatured(post) {
    if (!featuredBlock || !featuredSlot || !post) return;
    featuredSlug = post.slug;
    featuredSlot.innerHTML = `<a class="featured-card reveal" href="${Fs.postHref ? Fs.postHref(post.slug) : "./post.html?slug=" + encodeURIComponent(post.slug)}">
      <div class="featured-media">
        <img src="${escapeHtml(post.image_url)}" alt="" width="960" height="640" />
      </div>
      <div class="featured-copy">
        <span class="post-meta">${[post.cuisine, post.meal].filter(Boolean).map(escapeHtml).join(" · ")}</span>
        ${post.recipe_title ? `<span class="post-recipe">${escapeHtml(post.recipe_title)}</span>` : ""}
        <strong>${escapeHtml(post.title)}</strong>
        <span class="featured-hook">${escapeHtml(post.hook || "")}</span>
        <span class="featured-cta">Read the answer</span>
      </div>
    </a>`;
    featuredBlock.hidden = false;
  }

  function uniqueFilters(posts) {
    const cuisines = new Set();
    const meals = new Set();
    posts.forEach((p) => {
      String(p.cuisine || "")
        .split(/[,/]/)
        .map((s) => s.trim())
        .filter(Boolean)
        .forEach((c) => cuisines.add(c));
      if (p.meal) meals.add(String(p.meal).trim());
    });
    return {
      cuisines: [...cuisines].sort((a, b) => a.localeCompare(b)).slice(0, 8),
      meals: [...meals].sort((a, b) => a.localeCompare(b)).slice(0, 6),
    };
  }

  function renderFilterChips(posts) {
    if (!filterChips) return;
    const { cuisines, meals } = uniqueFilters(posts);
    const items = [
      { id: "all", label: "All" },
      ...cuisines.map((c) => ({ id: `cuisine:${c}`, label: c })),
      ...meals.map((m) => ({ id: `meal:${m}`, label: m })),
    ];
    filterChips.innerHTML = items
      .map(
        (item) =>
          `<button type="button" class="filter-chip${item.id === activeFilter ? " is-active" : ""}" data-filter="${escapeHtml(item.id)}">${escapeHtml(item.label)}</button>`
      )
      .join("");
    filterChips.querySelectorAll(".filter-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeFilter = btn.getAttribute("data-filter") || "all";
        filterChips.querySelectorAll(".filter-chip").forEach((b) => b.classList.toggle("is-active", b === btn));
        applyFilters();
      });
    });
  }

  function matchesFilter(post) {
    if (activeFilter === "all") return true;
    if (activeFilter.startsWith("cuisine:")) {
      const want = activeFilter.slice(8).toLowerCase();
      return String(post.cuisine || "").toLowerCase().includes(want);
    }
    if (activeFilter.startsWith("meal:")) {
      const want = activeFilter.slice(5).toLowerCase();
      return String(post.meal || "").toLowerCase() === want;
    }
    return true;
  }

  function renderPosts(posts, query) {
    if (!posts.length) {
      grid.innerHTML = `<p class="fine">No posts match “${escapeHtml(query || activeFilter)}”. Try a recipe name like <em>Idli</em> or a problem like <em>soggy</em>.</p>`;
      return;
    }
    grid.innerHTML = posts
      .map((p, i) => {
        const lead = i < 3 ? " post-card--lead" : "";
        return `<a class="post-card${lead} reveal" style="--reveal-delay:${Math.min(i, 8) * 40}ms" href="${Fs.postHref ? Fs.postHref(p.slug) : "./post.html?slug=" + encodeURIComponent(p.slug)}">
          <img src="${escapeHtml(p.image_url)}" alt="" loading="lazy" width="640" height="420" />
          <div class="post-card-body">
            <span class="post-meta">${[p.cuisine, p.meal].filter(Boolean).map(escapeHtml).join(" · ")}</span>
            ${p.recipe_title ? `<span class="post-recipe">${highlightMatch(p.recipe_title, query)}</span>` : ""}
            <strong>${highlightMatch(p.title, query)}</strong>
            <span class="post-hook">${escapeHtml(p.hook || "")}</span>
          </div>
        </a>`;
      })
      .join("");
  }

  function applyFilters(from) {
    if (from && headerSearch && from !== headerSearch) headerSearch.value = from.value;
    const q = getQuery();
    let filtered = !q ? allPosts : allPosts.filter((p) => Fs.matchesSearch(p, q));
    filtered = filtered.filter(matchesFilter);
    // Keep featured out of the grid when not searching/filtering
    const gridPosts =
      q || activeFilter !== "all"
        ? filtered
        : filtered.filter((p) => p.slug !== featuredSlug);

    if (searchMeta) {
      searchMeta.textContent = q || activeFilter !== "all"
        ? `${gridPosts.length} of ${allPosts.length} posts`
        : `${allPosts.length} posts`;
    }
    renderPosts(gridPosts, q);
    if (q && location.hash !== "#posts") {
      history.replaceState(null, "", "#posts");
    }
  }

  function bindSearch(el) {
    if (!el) return;
    el.addEventListener("input", () => applyFilters(el));
    el.addEventListener("search", () => applyFilters(el));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        document.getElementById("posts")?.scrollIntoView({ behavior: "smooth", block: "start" });
        applyFilters(el);
      }
    });
  }

  bindSearch(headerSearch);

  try {
    allPosts = await Fs.listReadyBlogPosts();
    allPosts = await Promise.all(allPosts.map((p) => Fs.enrichCard(p)));
    allPosts.sort((a, b) => String(a.recipe_title || a.title).localeCompare(String(b.recipe_title || b.title)));

    const urlQ = new URLSearchParams(location.search).get("q");
    if (urlQ && headerSearch) headerSearch.value = urlQ;

    startHeroCarousel(allPosts.map((p) => p.image_url));

    if (!allPosts.length) {
      grid.innerHTML = `<p class="fine">No posts yet.</p>`;
      return;
    }

    const featured = pickFeatured(allPosts);
    renderFeatured(featured);
    renderFilterChips(allPosts);
    applyFilters();

    if (urlQ || location.hash === "#posts") {
      document.getElementById("posts")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (err) {
    grid.innerHTML = `<p>Could not load posts. <code>${escapeHtml(String(err))}</code></p>`;
  }
})();
