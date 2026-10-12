/** Presentation only. Native controls and source records retain their identities. */
export const PHONE_QUERY = '(max-width: 700px)';
export const REVIEW_VIEWS = Object.freeze(['watch', 'timeline', 'notes', 'records']);
export function reviewView(value) { return REVIEW_VIEWS.includes(value) ? value : 'watch'; }

function disclosure(doc, title, elements, className = '') {
  const nodes = elements.filter(Boolean);
  if (!nodes.length) return null;
  const details = doc.createElement('details');
  details.className = 'studio-disclosure ' + className;
  details.open = !doc.defaultView.matchMedia(PHONE_QUERY).matches;
  const summary = doc.createElement('summary'); summary.textContent = title;
  nodes[0].before(details); details.append(summary, ...nodes);
  const query = doc.defaultView.matchMedia(PHONE_QUERY);
  query.addEventListener('change', event => { details.open = !event.matches; });
  return details;
}

export function installPresentation(doc, id) {
  if (doc.body.dataset.studioPresentation) return;
  doc.body.dataset.studioPresentation = id;
  doc.body.classList.add('studio-embedded');
  if (id === 'review') installReview(doc);
  else if (id === 'fx') {
    disclosure(doc, 'Processor library & demonstrations', [
      doc.querySelector('.module-heading'), doc.querySelector('.module-library'), doc.querySelector('.demo-bar')
    ]);
    disclosure(doc, 'Edit rack, connections & automation', [doc.querySelector('.rack-column')]);
  } else if (id === 'room') {
    disclosure(doc, 'Source pauses & earlier comparisons', [...doc.querySelectorAll('.support-section:not(.notes-section)')]);
  }
}

function installReview(doc) {
  const main = doc.querySelector('main');
  if (!main) return;
  const nav = doc.createElement('nav'); nav.className = 'studio-review-views';
  nav.setAttribute('aria-label', 'Source review views');
  const buttons = new Map();
  function select(value) {
    const view = reviewView(value); doc.body.dataset.reviewView = view;
    for (const [key, button] of buttons) button.setAttribute('aria-pressed', String(key === view));
    if (view === 'notes' || view === 'records') {
      const tab = doc.querySelector(view === 'notes' ? '[data-tab="notes"]' : '[data-tab="events"]');
      tab?.click();
    }
  }
  for (const value of REVIEW_VIEWS) {
    const button = doc.createElement('button'); button.type = 'button';
    button.textContent = value[0].toUpperCase() + value.slice(1);
    button.addEventListener('click', () => select(value));
    buttons.set(value, button); nav.append(button);
  }
  main.prepend(nav); select('watch');
  // Move existing nodes so their listeners, IDs, values and export behavior survive.
  const speed = doc.getElementById('rate')?.closest('label');
  disclosure(doc, 'Playback speed & sound', [speed, doc.getElementById('mute'), doc.getElementById('volume')], 'studio-playback-options');
  disclosure(doc, 'Picture references & passage loop', [doc.querySelector('.overlay-controls'), doc.querySelector('.rangebar')]);
  const files = disclosure(doc, 'Save, import & export', [doc.querySelector('.header-actions'), doc.querySelector('.bottom')], 'studio-file-options');
  if (files) main.append(files);
  const mq = doc.defaultView.matchMedia(PHONE_QUERY);
  const showNotes = () => { if (mq.matches) select('notes'); };
  doc.getElementById('new-at-time')?.addEventListener('click', showNotes);
  doc.getElementById('source-table')?.addEventListener('click', event => {
    if (event.target.closest('tbody tr') && mq.matches) select('notes');
  });
  doc.getElementById('notes-view')?.addEventListener('click', event => {
    if (event.target.closest('button') && mq.matches) select('notes');
  });
}

/** Measure content rather than scrollHeight: scrollHeight cannot shrink below an iframe's old viewport. */
export function contentHeight(doc) {
  let bottom = 0;
  for (const child of doc.body.children) {
    if (['SCRIPT', 'STYLE', 'DIALOG'].includes(child.tagName) || child.hidden) continue;
    const style = doc.defaultView.getComputedStyle(child);
    if (style.display === 'none' || style.position === 'fixed' || style.position === 'absolute') continue;
    const rect = child.getBoundingClientRect();
    bottom = Math.max(bottom, rect.bottom + doc.defaultView.scrollY + (parseFloat(style.marginBottom) || 0));
  }
  return Math.ceil(bottom + 24);
}

export function fitMobileFrame(frame) {
  const doc = frame.contentDocument;
  if (!doc?.body || frame.dataset.studioSizing) return;
  frame.dataset.studioSizing = 'ready';
  const query = window.matchMedia(PHONE_QUERY);
  let pending = false;
  const update = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      if (!frame.isConnected) { observer.disconnect(); query.removeEventListener('change', update); return; }
      if (!query.matches) { frame.style.removeProperty('height'); return; }
      if (frame.hidden) return;
      // The immersive room intentionally sizes its stage to the iframe viewport.
      // Feeding that height back into itself would grow the frame on every pass.
      const height = frame.dataset.tool === 'experience'
        ? Math.max(480, window.innerHeight - 160)
        : Math.max(260, contentHeight(doc));
      if (Math.abs(frame.getBoundingClientRect().height - height) > 2) frame.style.height = height + 'px';
    });
  };
  const observer = new ResizeObserver(update);
  observer.observe(doc.body);
  for (const child of doc.body.children) if (!['SCRIPT', 'STYLE'].includes(child.tagName)) observer.observe(child);
  query.addEventListener('change', update);
  frame.addEventListener('studio-visible', update);
  doc.addEventListener('click', update);
  doc.addEventListener('input', update);
  update();
}
