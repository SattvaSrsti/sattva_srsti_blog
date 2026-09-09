/**
 * One-shot: research real questions for a recipe (no Firestore write).
 * Usage: node run_research_once.js rec_gulab_jamun
 */
const path = require("path");
const admin = require("firebase-admin");

const TOOLS = path.join(process.env.APPDATA || "", "npm", "node_modules", "firebase-tools");
const recipeId = process.argv[2] || "rec_gulab_jamun";

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
  const { researchRealQuestions } = require("./research_questions");
  const snap = await admin.firestore().collection("recipes_v2").doc(recipeId).get();
  if (!snap.exists) throw new Error("recipe not found: " + recipeId);
  const recipe = { id: recipeId, ...snap.data() };
  const pack = await researchRealQuestions(await getOpenAiApiKeyFromFirestore(), recipe);
  console.log(JSON.stringify(pack, null, 2));
}

main().catch((err) => {
  console.error(String(err && err.stack ? err.stack : err));
  process.exit(1);
});
