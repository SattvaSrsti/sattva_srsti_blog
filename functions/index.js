const { onSchedule } = require('firebase-functions/v2/scheduler');
const { onRequest } = require('firebase-functions/v2/https');
const { logger } = require('firebase-functions');

/** 12:00 AM IST = 18:30 UTC — decrypt oKey from admin/dummy, reconcile blogs. */
exports.blogReconcileScheduled = onSchedule(
  {
    schedule: '30 18 * * *',
    timeZone: 'Etc/UTC',
    region: 'us-central1',
  },
  async () => {
    const { runBlogReconcile } = require('./blog_reconcile');
    const result = await runBlogReconcile();
    logger.info('blogReconcileScheduled done', result);
  }
);

/** Manual trigger for testing (private — project members only). */
exports.blogReconcileManual = onRequest(
  { region: 'us-central1', invoker: 'private' },
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
