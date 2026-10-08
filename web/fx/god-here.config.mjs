/** Artwork-specific source/region configuration, separate from primitive graph validation. */
export const GOD_HERE_SOURCE = Object.freeze({
  id: 'god-here-second-draft',
  sha256: 'bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225',
  offset: 95,
  duration: 12.166666667,
});

export const GOD_HERE_REGIONS = Object.freeze([
  'striped-shirt', 'patterned-shirt', 'dark-gray-shirt', 'light-gray-shirt', 'black-shirt-cap',
]);

export const GOD_HERE_WORD_MATERIAL = Object.freeze([
  {id: 'out', text: 'OUT', start: 2.88, end: 3.12, provenance: 'provisional ASR interval', listeningAccepted: false},
  {id: 'how', text: 'HOW', start: 6.14, end: 6.52, provenance: 'provisional ASR interval', listeningAccepted: false},
  {id: 'what', text: 'WHAT', start: 9.94, end: 10.08, provenance: 'provisional ASR interval', listeningAccepted: false},
  {id: 'why', text: 'WHY', provenance: 'authored screenplay word; not performed in this excerpt', listeningAccepted: false},
]);

export const GOD_HERE_DEMO_MODULES = Object.freeze({
  freeze: {region: 'light-gray-shirt', targets: ['voice', 'body']},
  reverse: {region: 'light-gray-shirt', targets: ['voice', 'body']},
});

export const GOD_HERE_OPTIONS = Object.freeze({
  source: GOD_HERE_SOURCE,
  regions: GOD_HERE_REGIONS,
  metadata: {
    project: 'god-here',
    originalPictureInterval: [95, 107.166666667],
    identityPolicy: 'Appearance labels, not certified performer names.',
    dialogueReference: {sha256: '24817c4f076a1c9fca43ebcf9825964610fc2956c1755501547de7477d173254', method: 'Inherited DeepFilterNet v0.5.6 candidate; shared stereo recording; artist/listening acceptance remains pending.'},
    wordMaterial: GOD_HERE_WORD_MATERIAL,
    layerStatus: 'Guided classical segmentation workprint; fine roto is not accepted.',
    roomStatus: 'Hybrid generated hidden-room fill; source-shot registration remains approximate.',
    objectStatus: 'Authored object regions, not segmented object tracks.',
  },
});
