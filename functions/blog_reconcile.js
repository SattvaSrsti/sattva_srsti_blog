const fsNode = require('fs');
const path = require('path');
const { logger } = require('firebase-functions');
const admin = require('firebase-admin');
const { getOpenAiApiKeyFromFirestore } = require('./crypto');

const OPENAI_CHAT_URL = 'https://api.openai.com/v1/chat/completions';
const DEFAULT_MODEL = 'gpt-4o-mini';
const MAX_CREATE_PER_RUN = 5;
const INGREDIENT_SHOW_RATIO = 0.7;
const MAX_PREVIEW_STEPS = 4;
const ROLE_LABELS = {
  base: 'Base',
  protein: 'Protein',
  spice: 'Spices',
  aromatic: 'Aromatics',
  fat: 'Fats & oils',
  liquid: 'Liquids',
  acid: 'Acids',
  garnish: 'Garnish',
};
const ROLE_ORDER = ['base', 'protein', 'spice', 'aromatic', 'fat', 'liquid', 'acid', 'garnish'];

function ensureAdmin() {
  if (!admin.apps.length) {
    admin.initializeApp();
  }
}

function fs() {
  ensureAdmin();
  return admin.firestore();
}

async function listRecipeIds() {
  const snap = await fs().collection('recipes_v2').where('status', '==', 'published').select().get();
  return snap.docs.map((d) => d.id);
}

async function listBlogPostsByRecipe() {
  const snap = await fs().collection('blog_posts').get();
  const byRecipe = {};
  for (const doc of snap.docs) {
    const data = doc.data() || {};
    const rid = data.recipe_id;
    if (!rid) continue;
    if (!byRecipe[rid]) byRecipe[rid] = [];
    byRecipe[rid].push({ id: doc.id, ...data });
  }
  return byRecipe;
}

function hasReadyBlog(posts) {
  return (posts || []).some((p) => ['ready', 'published'].includes(String(p.status || '').toLowerCase()));
}

async function fetchRecipeRoot(recipeId) {
  const doc = await fs().collection('recipes_v2').doc(recipeId).get();
  if (!doc.exists) return null;
  return { id: recipeId, ...doc.data() };
}

function humanizeSystemPrompt() {
  const file = path.join(__dirname, 'HUMANIZE_SYSTEM.txt');
  return fsNode.readFileSync(file, 'utf8').trim();
}

async function openaiHumanize(apiKey, ctx) {
  const body = {
    model: DEFAULT_MODEL,
    temperature: 0.4,
    response_format: { type: 'json_object' },
    messages: [
      { role: 'system', content: humanizeSystemPrompt() },
      { role: 'user', content: JSON.stringify(ctx) },
    ],
  };
  const res = await fetch(OPENAI_CHAT_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  const raw = await res.json();
  if (!res.ok) {
    throw new Error(`OpenAI ${res.status}: ${JSON.stringify(raw).slice(0, 400)}`);
  }
  return JSON.parse(raw.choices[0].message.content);
}

function slugify(text) {
  return String(text || 'recipe')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'recipe';
}

function publicIngredient(it) {
  const notes = [];
  const prep = it.preparation_state;
  if (prep && prep !== 'raw') notes.push(String(prep));
  if (String(it.requirement_level || '').toLowerCase() === 'optional') notes.push('optional');
  return {
    amount: it.amount || '',
    unit: it.unit || '',
    canonical_amount: it.canonical_amount || '',
    canonical_unit: it.canonical_unit || '',
    name: it.display_name || it.name || 'Ingredient',
    note: notes.join(', '),
  };
}

function groupIngredients(ings) {
  const groups = {};
  for (const it of Array.isArray(ings) ? ings : []) {
    if (!it || typeof it !== 'object') continue;
    const role = String(it.ingredient_role || 'other').toLowerCase();
    if (!groups[role]) groups[role] = [];
    groups[role].push(publicIngredient(it));
  }
  const ordered = ROLE_ORDER.filter((k) => groups[k] && groups[k].length);
  ordered.push(...Object.keys(groups).filter((k) => !ROLE_ORDER.includes(k)));
  return ordered.map((k) => ({
    name: ROLE_LABELS[k] || (k ? k[0].toUpperCase() + k.slice(1) : 'Other'),
    items: groups[k],
  }));
}

function capIngredientGroups(groups, ratio) {
  const total = (groups || []).reduce((n, g) => n + (g.items || []).length, 0);
  if (!total) return { groups: [], hidden: 0 };
  const maxShow = Math.max(1, Math.ceil(total * (ratio || INGREDIENT_SHOW_RATIO)));
  let shown = 0;
  const out = [];
  for (const g of groups) {
    if (shown >= maxShow) break;
    const items = [];
    for (const item of g.items || []) {
      if (shown >= maxShow) break;
      items.push(item);
      shown += 1;
    }
    if (items.length) out.push({ name: g.name, items });
  }
  return { groups: out, hidden: Math.max(0, total - shown) };
}

function previewStepLabel(text, i) {
  const low = String(text || '').toLowerCase();
  if (low.startsWith('rinse') || low.startsWith('soak')) return 'Prep';
  if (low.startsWith('boil')) return 'Boil';
  if (low.includes('grind')) return 'Grind';
  if (low.includes('mash') || low.includes('filling')) return 'Fill';
  if (low.includes('dough') || low.includes('knead')) return 'Dough';
  if (low.includes('roll')) return 'Roll';
  if (low.includes('cook') || low.includes('pan') || low.includes('tawa')) return 'Cook';
  return `Step ${i + 1}`;
}

async function buildDisplayTeaser(recipe) {
  const rid = recipe.id;
  let ings = Array.isArray(recipe.ingredients) ? recipe.ingredients : [];
  let steps = [];
  let storage = {};
  try {
    const ingSnap = await fs().collection('recipes_v2').doc(rid).collection('ingredients').doc('details').get();
    if (ingSnap.exists) {
      const d = ingSnap.data() || {};
      ings = d.ingredients || d.items || ings;
    }
  } catch (_) {}
  try {
    const instSnap = await fs().collection('recipes_v2').doc(rid).collection('instructions').doc('details').get();
    if (instSnap.exists) {
      const d = instSnap.data() || {};
      steps = d.steps || [];
      storage = d.leftover_storage || {};
    }
  } catch (_) {}
  return displayTeaserFromParts(recipe, ings, steps, storage);
}

function displayTeaserFromParts(recipe, ings, steps, storage) {
  const capped = capIngredientGroups(groupIngredients(ings), INGREDIENT_SHOW_RATIO);
  const preview = (steps || []).slice(0, MAX_PREVIEW_STEPS).map((s, i) => {
    const text = (s && (s.instruction_text || s.text)) || '';
    return { label: previewStepLabel(text, i), text };
  });
  const pairings = Array.isArray(recipe.pairing_recommendations)
    ? recipe.pairing_recommendations.map((p) => String(p).replace(/_/g, ' '))
    : [];
  const title = recipe.title || 'Recipe';
  return {
    recipe_title: title,
    recipe_slug: recipe.slug || slugify(title),
    image_url: recipe.image_primary_url || '',
    cuisine: recipe.cuisine || '',
    meal_type: recipe.meal_type || '',
    diet_tags: recipe.diet_tags || [],
    total_time_minutes: recipe.total_time_minutes || 0,
    difficulty: recipe.difficulty || '',
    spice_tolerance_level: recipe.spice_tolerance_level || '',
    servings: (recipe.base_yield && recipe.base_yield.servings) || 1,
    about_recipe: recipe.about_recipe || '',
    pairing_recommendations: pairings,
    search_tags: (recipe.search_tags || []).slice(0, 3).map((t) => String(t)),
    ingredient_groups: capped.groups,
    ingredient_hidden: capped.hidden,
    steps: preview,
    step_hidden: Math.max(0, (steps || []).length - MAX_PREVIEW_STEPS),
    storage: {
      refrigeration: (storage && (storage.refrigeration || storage.fridge)) || '',
      reheat: (storage && storage.reheat) || '',
      shelf_life: (storage && (storage.shelf_life || storage.duration)) || '',
    },
  };
}

async function writeBlogPost(recipe, primaryQuestion, humanized, research) {
  const slug = slugify(primaryQuestion);
  const blogId = `blog_${slug}`;
  const display = await buildDisplayTeaser(recipe);
  const doc = {
    blog_id: blogId,
    recipe_id: recipe.id,
    slug,
    status: 'ready',
    primary_question: primaryQuestion,
    seo_title: `${primaryQuestion} | SattvaSrsti`,
    meta_description: humanized.meta_description || primaryQuestion,
    blog_public_url: `https://sattvasrsti.blog/${slug}`,
    capability_id: 'guided_recipe_customization',
    humanized: {
      hook: humanized.hook || '',
      story: humanized.story || '',
      useful_answer: humanized.useful_answer || '',
      related_problems: humanized.related_problems || [],
      emotional_ending: humanized.emotional_ending || '',
    },
    customize_fixed: {
      title: 'Cook the full recipe on SattvaSrsti',
      body: 'When you are ready for every step, open the full recipe on SattvaSrsti — adjust ingredients, spice, and servings to match your kitchen.',
      cta_label: 'Open full recipe on SattvaSrsti',
    },
    image_url: display.image_url,
    cuisine: display.cuisine,
    meal_type: display.meal_type,
    recipe_title: display.recipe_title,
    display,
  };
  const { communityQuestionsForStore, packQuestions } = require('./research_questions');
  const community = communityQuestionsForStore(research || {}, humanized);
  if (community.length) {
    doc.community_questions = community;
  }
  if (research && research.primary_question) {
    const qs = packQuestions(research);
    doc.research = {
      primary_source: research.primary_question.source || '',
      primary_url: research.primary_question.source_url || '',
      questions: qs.map((q) => ({
        q: q.question,
        source: q.source,
        url: q.source_url || '',
        votes: q.votes || 0,
      })),
      related: (research.related_questions || []).map((q) => ({
        q: q.question,
        source: q.source,
        url: q.source_url || '',
        votes: q.votes || 0,
      })),
    };
  }
  await fs().collection('blog_posts').doc(blogId).set(doc, { merge: true });
  return blogId;
}

/**
 * Copy a 70% ingredient / 4-step teaser onto existing blog_posts.
 * Full recipes stay in recipes_v2 (not public).
 */
async function attachDisplayTeasersToExistingPosts() {
  const snap = await fs().collection('blog_posts').get();
  let updated = 0;
  let skipped = 0;
  const failed = [];
  for (const doc of snap.docs) {
    const data = doc.data() || {};
    const rid = data.recipe_id;
    if (!rid) {
      skipped += 1;
      continue;
    }
    try {
      const recipe = await fetchRecipeRoot(rid);
      if (!recipe) {
        skipped += 1;
        continue;
      }
      const display = await buildDisplayTeaser(recipe);
      await doc.ref.set(
        {
          display,
          recipe_title: display.recipe_title,
          image_url: display.image_url || data.image_url || '',
          cuisine: display.cuisine || data.cuisine || '',
          meal_type: display.meal_type || data.meal_type || '',
        },
        { merge: true }
      );
      updated += 1;
    } catch (err) {
      failed.push({ id: doc.id, error: String(err.message || err) });
    }
  }
  logger.info('attached display teasers', { updated, skipped, failed: failed.length });
  return { updated, skipped, failed };
}

/**
 * Nightly reconcile: teasers on existing posts, then fill missing blogs via OpenAI.
 */
async function runBlogReconcile() {
  const teasers = await attachDisplayTeasersToExistingPosts();
  const apiKey = await getOpenAiApiKeyFromFirestore();
  const recipeIds = await listRecipeIds();
  const byRecipe = await listBlogPostsByRecipe();

  const missing = recipeIds.filter((rid) => !hasReadyBlog(byRecipe[rid]));
  logger.info('blog reconcile', {
    recipes: recipeIds.length,
    blogRecipeIds: Object.keys(byRecipe).length,
    missing: missing.length,
  });

  const created = [];
  const failed = [];

  const { researchRealQuestions, lockHumanizedToResearch, isGenericQuestion } = require('./research_questions');

  for (const rid of missing.slice(0, MAX_CREATE_PER_RUN)) {
    try {
      const recipe = await fetchRecipeRoot(rid);
      if (!recipe || !recipe.title) {
        failed.push({ rid, error: 'recipe_not_found' });
        continue;
      }
      const pack = await researchRealQuestions(apiKey, recipe);
      const primaryQuestion = pack.primary_question.question;
      if (isGenericQuestion(primaryQuestion, recipe.title)) {
        failed.push({ rid, error: 'generic_primary_blocked' });
        continue;
      }
      const ctx = {
        recipe: { title: recipe.title, cuisine: recipe.cuisine || '' },
        primary_question: {
          question: pack.primary_question.question,
          source: pack.primary_question.source,
          evidence_type: pack.primary_question.evidence_type,
          evidence: pack.primary_question.evidence,
        },
        related_questions: pack.related_questions.map((q) => ({
          question: q.question,
          source: q.source,
          evidence_type: q.evidence_type,
          evidence: q.evidence,
        })),
        capability: {
          id: 'guided_recipe_customization',
          label: 'Guided recipe customization',
        },
      };
      let humanized = await openaiHumanize(apiKey, ctx);
      humanized = lockHumanizedToResearch(humanized, pack);
  const blogId = await writeBlogPost(recipe, primaryQuestion, humanized, pack);
      created.push({
        rid,
        blogId,
        primary: primaryQuestion,
        source: pack.primary_question.source,
      });
      logger.info('created blog', { rid, blogId, source: pack.primary_question.source });
    } catch (err) {
      failed.push({ rid, error: String(err.message || err) });
      logger.error('create failed', { rid, err: String(err.message || err) });
    }
  }

  return {
    teasers,
    recipes: recipeIds.length,
    missing: missing.length,
    created,
    failed,
  };
}

module.exports = {
  runBlogReconcile,
  attachDisplayTeasersToExistingPosts,
  displayTeaserFromParts,
  writeBlogPost,
  openaiHumanize,
};
