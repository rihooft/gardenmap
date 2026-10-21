import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';
import { toast } from './lib/store.svelte.js';

// Erreurs JavaScript affichées à l'écran : sans console sur le téléphone, c'est le seul moyen de les voir.
function report(msg) {
  console.error(msg);
  toast(`Erreur interne : ${String(msg).slice(0, 160)}`, 'error');
}
window.addEventListener('error', (e) => report(e.error?.message || e.message));
window.addEventListener('unhandledrejection', (e) => report(e.reason?.message || e.reason));

export default mount(App, { target: document.getElementById('app') });
