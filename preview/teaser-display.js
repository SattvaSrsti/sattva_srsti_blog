/** Apply teaser caps to recipe data before render (display layer only). */
(function () {
  function capIngredientGroups(grouped, ratio) {
    const total = (grouped || []).reduce((n, g) => n + (g.items || []).length, 0);
    if (!total) return { groups: [], total: 0, shown: 0, hidden: 0 };
    const maxShow = Math.max(1, Math.ceil(total * (ratio || 0.7)));
    let shown = 0;
    const out = [];
    for (const g of grouped) {
      if (shown >= maxShow) break;
      const items = [];
      for (const item of g.items || []) {
        if (shown >= maxShow) break;
        items.push(item);
        shown += 1;
      }
      if (items.length) out.push({ name: g.name, items });
    }
    return { groups: out, total, shown, hidden: total - shown };
  }

  function previewStepsLimited(steps, maxSteps, previewFn) {
    const cap = maxSteps || 4;
    const slice = (steps || []).slice(0, cap);
    if (typeof previewFn === "function") return previewFn(slice);
    return slice.map((s, i) => ({
      label: `Step ${i + 1}`,
      text: s.instruction_text || s.text || "",
    }));
  }

  window.SattvaTeaserDisplay = {
    capIngredientGroups,
    previewStepsLimited,
  };
})();
