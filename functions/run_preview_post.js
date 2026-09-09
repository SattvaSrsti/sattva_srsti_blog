/**
 * Generate one researched post (replaces generic title) for local/live preview.
 * Usage: node run_preview_post.js rec_gobi_manchuri
 */
const path = require("path");
const admin = require("firebase-admin");

const TOOLS = path.join(process.env.APPDATA || "", "npm", "node_modules", "firebase-tools");
const recipeId = process.argv[2] || "rec_gobi_manchuri";

async function main() {
  const { getGlobalDefaultAccount } = require(path.join(TOOLS, "lib", "auth.js"));
  const { getCredentialPathAsync } = require(path.join(TOOLS, "lib", "defaultCredentials.js"));
  const account = getGlobalDefaultAccount();
  if (!account) throw new Error("Not logged into Firebase CLI");
  const credPath = await getCredentialPathAsync(account);
  process.env.GOOGLE_APPLICATION_CREDENTIALS = credPath;
  process.env.GCLOUD_PROJECT = "sattva-srsti";
  process.env.GOOGLE_CLOUD_PROJECT = "sattva-srsti";
  if (!admin.apps.length) {
    admin.initializeApp({
      credential: admin.credential.applicationDefault(),
      projectId: "sattva-srsti",
    });
  }

  const { getOpenAiApiKeyFromFirestore } = require("./crypto");
  const { researchRealQuestions, lockHumanizedToResearch, isGenericQuestion } = require("./research_questions");
  const { openaiHumanize, writeBlogPost } = require("./blog_reconcile");

  const snap = await admin.firestore().collection("recipes_v2").doc(recipeId).get();
  if (!snap.exists) throw new Error("recipe not found: " + recipeId);
  const recipe = { id: recipeId, ...snap.data() };
  const apiKey = await getOpenAiApiKeyFromFirestore();
  const pack = await researchRealQuestions(apiKey, recipe);
  const primaryQuestion = pack.primary_question.question;
  if (isGenericQuestion(primaryQuestion, recipe.title)) {
    throw new Error("research still returned a generic primary: " + primaryQuestion);
  }
  const ctx = {
    recipe: { title: recipe.title, cuisine: recipe.cuisine || "" },
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
      id: "guided_recipe_customization",
      label: "Guided recipe customization",
    },
  };
  let humanized = await openaiHumanize(apiKey, ctx);
  humanized = lockHumanizedToResearch(humanized, pack);
  const blogId = await writeBlogPost(recipe, primaryQuestion, humanized, pack);

  const old = await admin.firestore().collection("blog_posts").where("recipe_id", "==", recipeId).get();
  const deleted = [];
  for (const doc of old.docs) {
    if (doc.id === blogId) continue;
    // Drop older posts for this recipe when regenerating (wrong dish Qs, generics).
    await doc.ref.delete();
    deleted.push(doc.id);
  }

  console.log(
    JSON.stringify(
      {
        recipeId,
        blogId,
        slug: blogId.replace(/^blog_/, ""),
        primary: primaryQuestion,
        source: pack.primary_question.source,
        related: pack.related_questions.map((q) => q.question),
        community: (pack.questions || []).map((q) => ({ q: q.question, source: q.source, url: q.source_url })),
        deleted,
      },
      null,
      2
    )
  );
}

main().catch((err) => {
  console.error(String(err && err.stack ? err.stack : err));
  process.exit(1);
});
