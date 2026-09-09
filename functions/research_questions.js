/**
 * Live web research: prefer real Quora links for recipe questions.
 * No vote/format standards — any Quora cooking question URL is eligible.
 */
const fs = require('fs');
const path = require('path');
const { logger } = require('firebase-functions');

const OPENAI_RESPONSES_URL = 'https://api.openai.com/v1/responses';
const RESEARCH_MODEL = process.env.OPENAI_RESEARCH_MODEL || 'gpt-4o-mini';

const GENERIC_PRIMARY = [
  'not turning out right',
  'not turn out right',
  'common mistakes when making',
  'fix common mistakes',
];

function isGenericQuestion(q, dish) {
  const low = String(q || '').toLowerCase();
  if (GENERIC_PRIMARY.some((p) => low.includes(p))) return true;
  const d = String(dish || '').toLowerCase();
  if (d && low === `why is my ${d} not turning out right?`) return true;
  return false;
}

function isQuoraQuestionUrl(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, '').toLowerCase();
    if (host !== 'quora.com') return false;
    const parts = u.pathname.split('/').filter(Boolean);
    if (!parts.length) return false;
    const first = parts[0].toLowerCase();
    const blocked = new Set([
      'profile', 'topic', 'search', 'about', 'login', 'webnode', 'careers',
      'q', 'spaces', 'answer', 'share', 'widgets', 'challenges',
    ]);
    if (blocked.has(first)) return false;
    const slug = first === 'unanswered' ? (parts[1] || '') : parts[0];
    if (!slug || /^\d+$/.test(slug)) return false;
    return slug.includes('-') && slug.replace(/[-_]/g, '').length >= 10;
  } catch {
    return false;
  }
}

function isRedditThreadUrl(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, '').toLowerCase();
    if (!/(^|\.)reddit\.com$/.test(host)) return false;
    return /^\/r\/[^/]+\/comments\/[a-z0-9]+(\/|$)/i.test(u.pathname);
  } catch {
    return false;
  }
}

const COOKING_SUBS = new Set([
  'indianfood', 'cooking', 'recipes', 'askculinary', 'vegetarian', 'vegan',
  'mealprepsunday', 'indiancelebration', 'food', 'seriouseats', 'eatcheapandhealthy',
]);
const BLOCKED_SUBS = new Set([
  'nofap', 'sex', 'nsfw', 'relationship_advice', 'abusiverelationships',
  'askreddit', 'trackandfield',
]);

function redditSubreddit(url) {
  try {
    const m = new URL(url).pathname.match(/^\/r\/([^/]+)/i);
    return m ? m[1].toLowerCase() : '';
  } catch {
    return '';
  }
}

const WEAK_DISH_TOKENS = new Set([
  'roast', 'roasted', 'chicken', 'rice', 'curry', 'fried', 'sauce', 'gravy',
  'dish', 'recipe', 'with', 'and', 'the', 'for', 'from', 'style', 'home',
  'special', 'masala', 'ghee', 'oil', 'dry', 'wet', 'hot', 'sweet',
]);

function dishAliasTokens(dish) {
  const title = String(dish || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ');
  const tokens = title.split(/\s+/).filter((t) => t.length > 2);
  const aliases = new Set(tokens);
  if (/gobi|cauliflower/.test(title) && /manchur/.test(title)) {
    ['gobi', 'manchurian', 'cauliflower'].forEach((t) => aliases.add(t));
  }
  if (/paneer/.test(title)) aliases.add('paneer');
  if (/dosa/.test(title)) aliases.add('dosa');
  if (/idli/.test(title)) aliases.add('idli');
  if (/biryani/.test(title)) aliases.add('biryani');
  if (/gulab|jamun/.test(title)) {
    aliases.add('gulab');
    aliases.add('jamun');
  }
  return [...aliases];
}

/** Question/URL must clearly refer to THIS dish — never another recipe. */
function mentionsDish(text, dish) {
  const hay = String(text || '').toLowerCase();
  if (!hay.trim()) return false;
  const tokens = dishAliasTokens(dish);
  const strong = tokens.filter((t) => t.length > 3 && !WEAK_DISH_TOKENS.has(t));
  const weak = tokens.filter((t) => WEAK_DISH_TOKENS.has(t) || t.length <= 3);
  const wordHit = (t) => new RegExp(`(?:^|[^a-z0-9])${t}s?(?:[^a-z0-9]|$)`, 'i').test(hay);
  const strongHits = strong.filter(wordHit);
  if (strongHits.length >= 1) return true;
  // Full dish phrase (e.g. "paneer ghee roast")
  const phrase = String(dish || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (phrase.length >= 8 && hay.includes(phrase)) return true;
  // Weak-only titles need 2 weak hits (rare)
  return weak.filter(wordHit).length >= 2 && strong.length === 0;
}

function isCookingRedditUrl(url, dish) {
  if (!isRedditThreadUrl(url)) return false;
  const sub = redditSubreddit(url);
  if (BLOCKED_SUBS.has(sub)) return false;
  const hay = `${url} ${questionFromUrl(url) || ''}`;
  if (!mentionsDish(hay, dish)) return false;
  if (COOKING_SUBS.has(sub)) return true;
  return /recipe|cook|fry|batter|soggy|crispy|curry/.test(hay.toLowerCase());
}

function classifyUrl(url) {
  if (!url) return { source: 'generated_intent', evidenceType: 'generated' };
  const u = String(url).toLowerCase();
  if (u.includes('quora.com')) {
    if (!isQuoraQuestionUrl(url)) return { source: 'generated_intent', evidenceType: 'generated' };
    return { source: 'quora', evidenceType: 'community' };
  }
  if (u.includes('reddit.com')) {
    if (!isRedditThreadUrl(url)) return { source: 'generated_intent', evidenceType: 'generated' };
    return { source: 'reddit', evidenceType: 'community' };
  }
  return { source: 'food_site', evidenceType: 'food_site' };
}

function cleanUrl(url) {
  try {
    const u = new URL(url);
    u.hash = '';
    u.search = '';
    u.hostname = u.hostname.replace(/^www\./, '');
    if (u.hostname === 'dd.reddit.com') u.hostname = 'reddit.com';
    return u.toString().replace(/\/+$/, '');
  } catch {
    return String(url || '').split('?')[0];
  }
}

function extractOutputText(data) {
  if (data && typeof data.output_text === 'string' && data.output_text.trim()) {
    return data.output_text;
  }
  const parts = [];
  for (const item of (data && data.output) || []) {
    if (item.type !== 'message') continue;
    for (const c of item.content || []) {
      if ((c.type === 'output_text' || c.type === 'text') && c.text) parts.push(c.text);
    }
  }
  return parts.join('\n');
}

function parseJsonObject(text) {
  const raw = String(text || '').trim();
  const fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const body = fence ? fence[1] : raw;
  const start = body.indexOf('{');
  const end = body.lastIndexOf('}');
  if (start < 0 || end <= start) return null;
  try {
    return JSON.parse(body.slice(start, end + 1));
  } catch {
    return null;
  }
}

function collectSearchSources(data) {
  const urls = [];
  for (const item of (data && data.output) || []) {
    if (item.type !== 'web_search_call') continue;
    const sources = (item.action && item.action.sources) || item.sources || [];
    for (const s of sources) {
      const u = typeof s === 'string' ? s : s && s.url;
      if (u) urls.push(String(u));
    }
  }
  return urls;
}

function questionFromUrl(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, '').toLowerCase();
    const parts = u.pathname.split('/').filter(Boolean);
    const skip = new Set(['profile', 'topic', 'search', 'about', 'login', 'webnode']);
    if (parts[0] && skip.has(parts[0].toLowerCase())) return null;
    let slug = '';
    if (host.endsWith('reddit.com')) {
      const m = u.pathname.match(/\/comments\/[a-z0-9]+\/([^/]+)/i);
      slug = m ? m[1] : '';
    } else {
      let slugPart = parts[parts.length - 1] || '';
      if (!slugPart || slugPart === 'answers' || /^\d+$/.test(slugPart)) {
        slugPart = parts[parts.length - 2] || '';
      }
      slug = slugPart.replace(/^\d+-/, '');
    }
    const words = decodeURIComponent(slug).replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim();
    if (words.length < 8) return null;
    let q = words.charAt(0).toUpperCase() + words.slice(1);
    if (!/[?]$/.test(q)) q += '?';
    return q;
  } catch {
    return null;
  }
}

function toCandidate({ question, url, evidence, connector }) {
  const q = String(question || '').trim();
  const sourceUrl = cleanUrl(url);
  if (!q || !sourceUrl) return null;
  const { source, evidenceType } = classifyUrl(sourceUrl);
  if (source === 'generated_intent') return null;
  const ev = (Array.isArray(evidence) ? evidence : [])
    .map((e) => String(e || '').trim())
    .filter(Boolean)
    .slice(0, 5);
  if (!ev.length) ev.push(`Source: ${sourceUrl}`);
  const bonus = source === 'quora' ? 400 : source === 'reddit' ? 280 : 20;
  return {
    question: q,
    source,
    source_url: sourceUrl,
    evidence_type: evidenceType,
    evidence: ev,
    connector: connector || 'web_search',
    votes: 0,
    _score: bonus,
  };
}

function candidateFromLink(url, fallbackTitle) {
  const { source } = classifyUrl(url);
  const question = questionFromUrl(url) || fallbackTitle;
  if (!question) return null;
  return toCandidate({
    question,
    url,
    evidence: [`${source} link: ${cleanUrl(url)}`],
    connector: 'search_source_url',
  });
}

async function openaiWebSearch(apiKey, input) {
  const body = {
    model: RESEARCH_MODEL,
    tools: [
      {
        type: 'web_search',
        search_context_size: 'high',
        user_location: { type: 'approximate', country: 'IN' },
      },
    ],
    tool_choice: { type: 'web_search' },
    include: ['web_search_call.action.sources'],
    input,
  };
  const res = await fetch(OPENAI_RESPONSES_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(`OpenAI research ${res.status}: ${JSON.stringify(data).slice(0, 400)}`);
  }
  const parsed = parseJsonObject(extractOutputText(data));
  return {
    questions: Array.isArray(parsed && parsed.questions) ? parsed.questions : [],
    sources: collectSearchSources(data),
  };
}

function loadSeedCandidates(recipeId, dish) {
  // Recipe-specific seeds only. Shared pool is filtered by dish so dosa Qs
  // never land on Paneer / Gobi / other posts.
  const files = [
    path.join(__dirname, 'research_seeds', `${recipeId}.json`),
    path.join(__dirname, '..', 'preview', 'data', 'research_seeds', `${recipeId}.json`),
    path.join(__dirname, 'research_seeds', 'quora_recipe_questions.json'),
    path.join(__dirname, '..', 'preview', 'data', 'research_seeds', 'quora_recipe_questions.json'),
  ];
  const out = [];
  const seen = new Set();
  for (const file of files) {
    if (!fs.existsSync(file)) continue;
    try {
      const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
      const items = raw.research_questions
        || [raw.primary_question, ...(raw.related_questions || [])].filter(Boolean);
      for (const item of items) {
        if (!item || !(isQuoraQuestionUrl(item.source_url) || isRedditThreadUrl(item.source_url))) continue;
        const q = item.q || item.question || questionFromUrl(item.source_url);
        const hay = `${q || ''} ${item.source_url || ''}`;
        if (dish && !mentionsDish(hay, dish)) continue;
        const c = toCandidate({
          question: q,
          url: item.source_url,
          evidence: item.source_answers || item.evidence || [`Community seed: ${item.source_url}`],
          connector: 'seed',
        });
        if (!c || (c.source !== 'quora' && c.source !== 'reddit')) continue;
        const key = cleanUrl(c.source_url);
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(c);
      }
    } catch (err) {
      logger.warn('research seed unreadable', { file, err: String(err.message || err) });
    }
  }
  return out;
}

function unwrapSearchUrl(href) {
  try {
    const u = new URL(String(href).replace(/&amp;/g, '&'), 'https://www.bing.com');
    const uddg = u.searchParams.get('uddg');
    if (uddg) return decodeURIComponent(uddg);
    let raw = u.searchParams.get('u') || '';
    raw = raw.replace(/^a1/i, '');
    if (raw) {
      const decoded = Buffer.from(raw, 'base64').toString('utf8');
      if (/^https?:/i.test(decoded)) return decoded;
    }
  } catch {
    /* keep href */
  }
  return href;
}

function extractCommunityHits(html, limit = 15) {
  const hits = [];
  const seen = new Set();
  const push = (url, title) => {
    const href = unwrapSearchUrl(String(url || '').replace(/&amp;/g, '&'));
    if (!isQuoraQuestionUrl(href) && !isRedditThreadUrl(href)) return;
    const key = cleanUrl(href);
    if (seen.has(key)) return;
    seen.add(key);
    hits.push({
      title: String(title || questionFromUrl(href) || '').replace(/<[^>]+>/g, '').trim(),
      url: href,
    });
  };
  const re = /href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;
  let m;
  while ((m = re.exec(html)) && hits.length < limit) {
    push(m[1], m[2]);
  }
  const raw = html.match(/https?:\/\/(?:www\.)?(?:quora\.com|reddit\.com)\/[^\s"'<>]+/gi) || [];
  for (const url of raw) {
    if (hits.length >= limit) break;
    push(url, '');
  }
  return hits;
}

async function fetchSearchHtml(url) {
  const res = await fetch(url, {
    headers: {
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      Accept: 'text/html',
    },
  });
  return res.ok && res.status !== 202 ? res.text() : '';
}

async function ddgSearch(query, limit = 10) {
  try {
    const url = `https://html.duckduckgo.com/html/?${new URLSearchParams({ q: query }).toString()}`;
    return extractCommunityHits(await fetchSearchHtml(url), limit);
  } catch {
    return [];
  }
}

async function bingSearch(query, limit = 10) {
  try {
    const url = `https://www.bing.com/search?${new URLSearchParams({ q: query }).toString()}`;
    return extractCommunityHits(await fetchSearchHtml(url), limit);
  } catch {
    return [];
  }
}

function normalizeKey(q) {
  return String(q || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function pickCommunity(candidates, dish, cuisine) {
  const seenQ = new Set();
  const seenUrl = new Set();
  const uniq = [];
  const ranked = [...candidates].sort((a, b) => {
    const order = { quora: 0, reddit: 1, food_site: 9 };
    const da = order[a.source] ?? 9;
    const db = order[b.source] ?? 9;
    if (da !== db) return da - db;
    return (b._score || 0) - (a._score || 0);
  });
  for (const c of ranked) {
    if (c.source !== 'quora' && c.source !== 'reddit') continue;
    const hay = `${c.question} ${c.source_url}`;
    if (!mentionsDish(hay, dish)) continue;
    if (c.source === 'reddit' && !isCookingRedditUrl(c.source_url, dish)) continue;
    if (c.source === 'quora' && !isQuoraQuestionUrl(c.source_url)) continue;
    const qk = normalizeKey(c.question);
    const uk = cleanUrl(c.source_url);
    if (!qk || seenQ.has(qk) || seenUrl.has(uk)) continue;
    if (isGenericQuestion(c.question, dish)) continue;
    seenQ.add(qk);
    seenUrl.add(uk);
    uniq.push(c);
  }
  if (uniq.length < 3) {
    throw new Error(
      `Need at least 3 same-dish Quora/Reddit links for "${dish}", got ${uniq.length}`
    );
  }
  const strip = (c) => ({
    question: c.question,
    source: c.source,
    source_url: c.source_url,
    evidence_type: c.evidence_type,
    evidence: (c.evidence || []).slice(0, 5),
    connector: c.connector,
    votes: c.votes || 0,
  });
  const picked = uniq.slice(0, 6).map(strip);
  return {
    recipe: { title: dish, cuisine: cuisine || '' },
    questions: picked,
    primary_question: picked[0],
    related_questions: picked.slice(1),
  };
}

async function researchRealQuestions(apiKey, recipe) {
  const title = recipe.title || 'Recipe';
  const cuisine = recipe.cuisine || 'Indian';
  const candidates = loadSeedCandidates(recipe.id, title);
  logger.info('quora seeds', {
    recipeId: recipe.id,
    dish: title,
    quora: candidates.filter((c) => c.source === 'quora').length,
    reddit: candidates.filter((c) => c.source === 'reddit').length,
  });

  const quoraPrompt = `Find Quora question pages about cooking "${title}".
Search with: site:www.quora.com "${title}" recipe
Only keep URLs like https://www.quora.com/How-do-I-... or https://www.quora.com/What-is-...
Never use help.quora.com, profile, topic, about, or careers pages.
Any cooking/recipe question is fine — no vote or wording standards.
Return JSON: {"questions":[{"question":"...","source_url":"https://www.quora.com/..."}]}
Every source_url MUST be copied from the search results. Do not invent URLs.`;

  if (!candidates.filter((c) => c.source === 'quora').length) {
  try {
    const quora = await openaiWebSearch(apiKey, quoraPrompt);
    const quoraSources = (quora.sources || []).filter((u) => /quora\.com/i.test(u));
    logger.info('quora search', {
      sources: (quora.sources || []).length,
      quoraSources: quoraSources.length,
      questionPages: quoraSources.filter(isQuoraQuestionUrl).length,
      dropped: quoraSources.filter((u) => !isQuoraQuestionUrl(u)).slice(0, 8),
      questions: (quora.questions || []).length,
    });
    for (const url of quoraSources) {
      if (!isQuoraQuestionUrl(url)) continue;
      const c = candidateFromLink(url, `Cooking question about ${title}?`);
      if (c && c.source === 'quora') candidates.push(c);
    }
    for (const item of quora.questions || []) {
      if (!item || !isQuoraQuestionUrl(item.source_url)) continue;
      // Never accept invented Quora URLs — must appear in search sources when any exist.
      const wanted = quoraSources.some((s) => cleanUrl(s) === cleanUrl(item.source_url));
      if (quoraSources.length && !wanted) continue;
      if (!quoraSources.length) continue;
      const c = toCandidate({
        question: item.question || questionFromUrl(item.source_url),
        url: item.source_url,
        evidence: item.evidence || [`Quora: ${item.source_url}`],
        connector: 'openai_web_search',
      });
      if (c && c.source === 'quora') candidates.push(c);
    }
  } catch (err) {
    logger.warn('quora web search failed', { err: String(err.message || err) });
  }
  }

  const addHits = (hits, connector) => {
    for (const hit of hits || []) {
      if (!isQuoraQuestionUrl(hit.url) && !isCookingRedditUrl(hit.url, title)) continue;
      const c = toCandidate({
        question: hit.title.includes('?') ? hit.title : questionFromUrl(hit.url) || hit.title,
        url: hit.url,
        evidence: [hit.title || `Community: ${hit.url}`],
        connector,
      });
      if (c && (c.source === 'quora' || c.source === 'reddit')) candidates.push(c);
    }
  };

  const alias = /gobi/i.test(title) ? 'cauliflower manchurian' : '';
  const searchQueries = [
    `site:quora.com "${title}"`,
    `${title} site:quora.com`,
    `site:reddit.com "${title}" recipe`,
    `site:reddit.com/r/IndianFood ${title}`,
    alias ? `quora ${alias}` : '',
    alias ? `site:reddit.com ${alias}` : '',
  ].filter(Boolean);

  for (const q of searchQueries) {
    addHits(await ddgSearch(q, 12), 'duckduckgo');
    if (candidates.filter((c) => c.source === 'quora' || c.source === 'reddit').length >= 6) break;
    addHits(await bingSearch(q, 12), 'bing');
    if (candidates.filter((c) => c.source === 'quora' || c.source === 'reddit').length >= 6) break;
  }
  logger.info('community html search', {
    quora: candidates.filter((c) => c.source === 'quora').length,
    reddit: candidates.filter((c) => c.source === 'reddit').length,
  });

  if (candidates.filter((c) => c.source === 'reddit').length < 2) {
    try {
      const reddit = await openaiWebSearch(
        apiKey,
        `Search Reddit for cooking questions about "${title}".
Use queries like: site:reddit.com "${title}" recipe
Only keep thread URLs like https://www.reddit.com/r/.../comments/...
Return JSON: {"questions":[{"question":"...","source_url":"https://www.reddit.com/r/.../comments/..."}]}
Copy source_url from search results. Do not invent Reddit post IDs.`
      );
      const redditSources = (reddit.sources || []).filter((u) => isCookingRedditUrl(u, title));
      logger.info('reddit search', {
        sources: (reddit.sources || []).length,
        threads: redditSources.length,
        questions: (reddit.questions || []).length,
      });
      for (const url of redditSources) {
        const c = candidateFromLink(url, `Cooking question about ${title}?`);
        if (c && c.source === 'reddit') candidates.push(c);
      }
      for (const item of reddit.questions || []) {
        if (!isCookingRedditUrl(item.source_url, title)) continue;
        // Never accept model-invented Reddit IDs — URL must appear in search sources.
        if (!redditSources.some((s) => cleanUrl(s) === cleanUrl(item.source_url))) continue;
        const c = toCandidate({
          question: item.question || questionFromUrl(item.source_url),
          url: item.source_url,
          evidence: item.evidence || [`Reddit: ${item.source_url}`],
          connector: 'openai_web_search',
        });
        if (c && c.source === 'reddit') candidates.push(c);
      }
    } catch (err) {
      logger.warn('reddit web search failed', { err: String(err.message || err) });
    }
  }

  logger.info('research candidates', {
    total: candidates.length,
    quora: candidates.filter((c) => c.source === 'quora').length,
    reddit: candidates.filter((c) => c.source === 'reddit').length,
    food: candidates.filter((c) => c.source === 'food_site').length,
  });
  const pack = pickCommunity(candidates, title, cuisine);
  logger.info('research questions', {
    title,
    count: pack.questions.length,
    primary: pack.primary_question.question,
    primarySource: pack.primary_question.source,
    primaryUrl: pack.primary_question.source_url,
    sources: pack.questions.map((q) => q.source),
  });
  return pack;
}

function packQuestions(pack) {
  if (Array.isArray(pack && pack.questions) && pack.questions.length) return pack.questions;
  return [pack.primary_question, ...(pack.related_questions || [])].filter(Boolean);
}

function lockHumanizedToResearch(humanized, pack) {
  const out = { ...(humanized || {}) };
  const questions = packQuestions(pack);
  out.primary_question = questions[0].question;
  const answers = Array.isArray(humanized && humanized.related_problems)
    ? humanized.related_problems
    : [];
  out.related_problems = questions.slice(1).map((rq, i) => {
    const item = answers[i] || {};
    const a = item.a || item.answer || '';
    return { q: rq.question, a: String(a).trim() };
  });
  if (typeof out.useful_answer === 'object' && out.useful_answer) {
    out.useful_answer = out.useful_answer.text || out.useful_answer.answer || '';
  }
  return out;
}

function communityQuestionsForStore(pack, humanized) {
  const questions = packQuestions(pack);
  const locked = lockHumanizedToResearch(humanized, pack);
  return questions.slice(0, 6).map((q, i) => ({
    question: q.question,
    source: q.source,
    url: q.source_url || '',
    answer: i === 0
      ? String(locked.useful_answer || '')
      : String((locked.related_problems[i - 1] || {}).a || ''),
  }));
}

module.exports = {
  researchRealQuestions,
  lockHumanizedToResearch,
  communityQuestionsForStore,
  packQuestions,
  isGenericQuestion,
  isQuoraQuestionUrl,
  isRedditThreadUrl,
  unwrapSearchUrl,
  mentionsDish,
};
