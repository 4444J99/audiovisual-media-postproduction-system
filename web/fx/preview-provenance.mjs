/** Producing-code identity for previews paired with this editable engine.
 * Historical render receipts remain immutable. Update this map only when the
 * corresponding runtime files change; tests check it against the source bytes.
 */
export const ENGINE_CODE_SHA256 = Object.freeze({
  'core.mjs': '2127a48b62c507082ccf783937fc0ffb3222bab158d31d4768ea1d5439b9b0af',
  'catalog.mjs': '7f3659b58b446e9aae932b2fc9a2246524b67ec9d70f7730c37d409ab914adfd',
  'visual-engine.mjs': '42be9510643e71595a088faa1fe0ca616297b8a45f0723f19acd2abff75f34b1',
  'audio-engine.mjs': '84cdfdfc4cc25ac3f50402a165e79724fb4e076e40a940ab4f9506c3e2dbf47f',
  'preview-key.mjs': '6285b41c3f4af0afd5239aedc4c122279098a9c0b5b9cef4e8a63cf7d0b73979',
  'god-here.config.mjs': 'b47ae61497db053321f4ea3ce48667d5a1121200aa1b75637a895d370c0158f7',
});

export function compatiblePreviewEntries(manifest) {
  if (!manifest?.complete || !Array.isArray(manifest.entries)) return [];
  if (!Object.entries(ENGINE_CODE_SHA256).every(([name, sha256]) => manifest.codeHashes?.[name] === sha256)) return [];
  return manifest.entries.filter(entry => entry?.status === 'complete'
    && typeof entry.signalSignature === 'string'
    && typeof entry.video === 'string' && typeof entry.portrait === 'string');
}
