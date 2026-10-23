const admin = require('firebase-admin');
const { getFirestore } = require('firebase-admin/firestore');

/** Isolated public blog data (browser reads this DB only). */
const BLOG_DATABASE_ID = process.env.FIRESTORE_BLOG_DATABASE || 'blog';

function ensureAdmin() {
  if (!admin.apps.length) {
    admin.initializeApp();
  }
}

function defaultDb() {
  ensureAdmin();
  return getFirestore();
}

function blogDb() {
  ensureAdmin();
  return getFirestore(admin.app(), BLOG_DATABASE_ID);
}

module.exports = { defaultDb, blogDb, BLOG_DATABASE_ID };
