const { logger } = require('firebase-functions');
const admin = require('firebase-admin');
const { getOpenAiApiKeyFromFirestore } = require('./crypto');

const OPENAI_CHAT_URL = 'https://api.openai.com/v1/chat/completions';
const DEFAULT_MODEL = 'gpt-4o-mini';
const MAX_CREATE_PER_RUN = 5;

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
  const snap = await fs().collection('recipes_v2').select().get();
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

async function openaiHumanize(apiKey, ctx) {
  const body = {
    model: DEFAULT_MODEL,
    temperature: 0.4,
    response_format: { type: 'json_object' },
    messages: [
      {
        role: 'system',
        content:
          'You write problem-led blog copy for SattvaSrsti. Return JSON with hook, story, useful_answer, related_problems (array of 4 {q,a}), emotional_ending.',
      },
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

async function writeBlogPost(recipe, primaryQuestion, humanized) {
  const slug = slugify(primaryQuestion);
  const blogId = `blog_${slug}`;
  const doc = {
    blog_id: blogId,
    recipe_id: recipe.id,
    slug,
    status: 'ready',
    primary_question: primaryQuestion,
    seo_title: `${primaryQuestion} | SattvaSrsti`,
    meta_description: humanized.meta_description || primaryQuestion,
    blog_public_url: `https://sattvasrsti.blog/post.html?slug=${slug}`,
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
    image_url: recipe.image_primary_url || '',
    cuisine: recipe.cuisine || '',
    meal_type: recipe.meal_type || '',
  };
  await fs().collection('blog_posts').doc(blogId).set(doc, { merge: true });
  return blogId;
}

/**
 * Nightly reconcile: recipes_v2 vs blog_posts using decrypted oKey (no env secrets).
 */
async function runBlogReconcile() {
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

  for (const rid of missing.slice(0, MAX_CREATE_PER_RUN)) {
    try {
      const recipe = await fetchRecipeRoot(rid);
      if (!recipe || !recipe.title) {
        failed.push({ rid, error: 'recipe_not_found' });
        continue;
      }
      const primaryQuestion = `Why is my ${recipe.title} not turning out right?`;
      const ctx = {
        title: recipe.title,
        primary_question: primaryQuestion,
        about_recipe: recipe.about_recipe || '',
        cuisine: recipe.cuisine || '',
      };
      const humanized = await openaiHumanize(apiKey, ctx);
      const blogId = await writeBlogPost(recipe, primaryQuestion, humanized);
      created.push({ rid, blogId });
      logger.info('created blog', { rid, blogId });
    } catch (err) {
      failed.push({ rid, error: String(err.message || err) });
      logger.error('create failed', { rid, err: String(err.message || err) });
    }
  }

  return {
    recipes: recipeIds.length,
    missing: missing.length,
    created,
    failed,
  };
}

module.exports = { runBlogReconcile };
