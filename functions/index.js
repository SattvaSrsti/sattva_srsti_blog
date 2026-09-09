const { onRequest } = require('firebase-functions/v2/https');
const { logger } = require('firebase-functions');

/** Manual trigger for testing (private — project members only). */
exports.blogReconcileManual = onRequest(
  { region: 'us-central1', invoker: 'private', timeoutSeconds: 300, memory: '512MiB' },
  async (_req, res) => {
    try {
      const { runBlogReconcile } = require('./blog_reconcile');
      const result = await runBlogReconcile();
      res.status(200).json({ ok: true, ...result });
    } catch (err) {
      logger.error('blogReconcileManual failed', err);
      res.status(500).json({ ok: false, error: String(err.message || err) });
    }
  }
);

/** Copy 70% ingredient / 4-step teasers onto existing blog_posts (no OpenAI). */
exports.blogAttachTeasersManual = onRequest(
  { region: 'us-central1', invoker: 'private', timeoutSeconds: 120 },
  async (_req, res) => {
    try {
      const { attachDisplayTeasersToExistingPosts } = require('./blog_reconcile');
      const result = await attachDisplayTeasersToExistingPosts();
      res.status(200).json({ ok: true, ...result });
    } catch (err) {
      logger.error('blogAttachTeasersManual failed', err);
      res.status(500).json({ ok: false, error: String(err.message || err) });
    }
  }
);

/** Health check: verifies AES decrypt of oKey works (does not return the key). */
exports.blogOpenAiKeyHealth = onRequest(
  { region: 'us-central1', invoker: 'private' },
  async (_req, res) => {
    try {
      const { getOpenAiApiKeyFromFirestore } = require('./crypto');
      const key = await getOpenAiApiKeyFromFirestore();
      res.status(200).json({ ok: true, keyPresent: Boolean(key) });
    } catch (err) {
      res.status(500).json({ ok: false, error: String(err.message || err) });
    }
  }
);
