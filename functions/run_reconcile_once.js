/**
 * One-shot local run of the production blog reconcile.
 * Uses Firebase CLI login (not env secrets). Does not print the OpenAI key.
 */
const path = require("path");
const admin = require("firebase-admin");

const TOOLS = path.join(
  process.env.APPDATA || "",
  "npm",
  "node_modules",
  "firebase-tools"
);

async function main() {
  const { getGlobalDefaultAccount } = require(path.join(TOOLS, "lib", "auth.js"));
  const { getCredentialPathAsync } = require(path.join(TOOLS, "lib", "defaultCredentials.js"));
  const account = getGlobalDefaultAccount();
  if (!account) {
    throw new Error("Not logged into Firebase CLI. Run: npx firebase-tools login");
  }
  const credPath = await getCredentialPathAsync(account);
  if (!credPath) {
    throw new Error("Could not materialize Firebase CLI credentials");
  }
  process.env.GOOGLE_APPLICATION_CREDENTIALS = credPath;
  process.env.GCLOUD_PROJECT = "sattva-srsti";
  process.env.GOOGLE_CLOUD_PROJECT = "sattva-srsti";

  if (!admin.apps.length) {
    admin.initializeApp({
      credential: admin.credential.applicationDefault(),
      projectId: "sattva-srsti",
    });
  }

  const { runBlogReconcile } = require("./blog_reconcile");
  const result = await runBlogReconcile();
  console.log(JSON.stringify(result, null, 2));
}

main().catch((err) => {
  console.error(String(err && err.stack ? err.stack : err));
  process.exit(1);
});
