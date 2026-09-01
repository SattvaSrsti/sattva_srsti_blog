const crypto = require('crypto');
const admin = require('firebase-admin');

let cachedOpenAiKey = null;

function ensureAdmin() {
  if (!admin.apps.length) {
    admin.initializeApp();
  }
}

function firestore() {
  ensureAdmin();
  return admin.firestore();
}

/** Matches Flutter Encrypt + main app functions — AES-256-CBC, base64 key/iv/ciphertext. */
function decryptAes256Cbc(cipherBase64, base64Key, base64Iv) {
  if (!cipherBase64) {
    return '';
  }
  const key = Buffer.from(base64Key, 'base64');
  const iv = Buffer.from(base64Iv, 'base64');
  const decipher = crypto.createDecipheriv('aes-256-cbc', key, iv);
  let plain = decipher.update(cipherBase64, 'base64', 'utf8');
  plain += decipher.final('utf8');
  return plain;
}

/**
 * OpenAI API key from Firestore admin/dummy.oKey (encrypted with b + iv).
 * No environment secrets — same pattern as sattva/functions getOpenAiApiKey.
 */
async function getOpenAiApiKeyFromFirestore() {
  if (cachedOpenAiKey) {
    return cachedOpenAiKey;
  }

  const snapshot = await firestore().collection('admin').doc('dummy').get();
  if (!snapshot.exists) {
    throw new Error('admin/dummy document not found in Firestore');
  }

  const data = snapshot.data() || {};
  const baseKey = data.b;
  const ivKey = data.iv;
  const encryptedOpenAiKey = data.oKey;

  if (!baseKey || !ivKey || !encryptedOpenAiKey) {
    throw new Error('admin/dummy must contain b, iv, and oKey');
  }

  const apiKey = decryptAes256Cbc(encryptedOpenAiKey, baseKey, ivKey);
  if (!apiKey) {
    throw new Error('Could not decrypt oKey from admin/dummy');
  }

  cachedOpenAiKey = apiKey;
  return cachedOpenAiKey;
}

module.exports = {
  decryptAes256Cbc,
  getOpenAiApiKeyFromFirestore,
};
