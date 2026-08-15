import { createRoot } from 'react-dom/client';
import { App } from './App.jsx';

// Entry: find [data-wl-vendor-root] nodes and hydrate each from its JSON payload.

/** Parse the Liquid JSON payload and mount <App> once per root. */
function mount(root) {
  if (root.dataset.mounted === 'true') return;
  let data;
  try {
    data = JSON.parse(root.querySelector('script[type="application/json"]').textContent);
  } catch (error) {
    console.error('Vendor collection: invalid payload', error);
    return;
  }
  if (!data || !data.collection) return;
  root.dataset.mounted = 'true';
  createRoot(root).render(<App data={data} />);
}

/** Mount every vendor-collection island on the page (PDP and homepage). */
function boot() {
  document.querySelectorAll('[data-wl-vendor-root]').forEach(mount);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot, { once: true });
} else {
  boot();
}

// Theme Editor re-injects the section without a full page reload.
document.addEventListener('shopify:section:load', (event) => {
  const root = event.target.querySelector('[data-wl-vendor-root]');
  if (root) mount(root);
});
