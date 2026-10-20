export const MONTHS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
export const MONTHS_SHORT = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

export const CATEGORY_ICON = {
  arbre: '🌳', fruitier: '🍎', arbuste: '🌿', haie: '🌲', grimpante: '🍃', vivace: '🌸', annuelle: '🌼',
  bulbe: '🌷', aromatique: '🌱', potager: '🥕', aquatique: '🪷', graminee: '🌾', autre: '🪴',
};

export const STATUS_COLOR = {
  en_place: 'var(--leaf)', malade: 'var(--warn)', mort: 'var(--dead)', arrache: 'var(--dead)', deplace: 'var(--dead)',
};

export const ACTIVE_STATUSES = new Set(['en_place', 'malade']);

export function fmtDate(iso, withTime = false) {
  if (!iso) return '';
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  const opts = { day: 'numeric', month: 'long', year: 'numeric' };
  if (withTime) Object.assign(opts, { hour: '2-digit', minute: '2-digit' });
  return d.toLocaleDateString('fr-FR', opts);
}

export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Âge en années : depuis la plantation, ou âge estimé + temps écoulé depuis l'estimation. */
export function ageYears(sp, now = new Date()) {
  const years = (from) => (now - new Date(`${from}T12:00:00`)) / (365.25 * 864e5);
  if (sp.planted_on) return { value: years(sp.planted_on), exact: true };
  if (sp.age_years != null) {
    const extra = sp.age_estimated_on ? years(sp.age_estimated_on) : 0;
    return { value: sp.age_years + Math.max(0, extra), exact: false };
  }
  return null;
}

export function fmtAge(age) {
  if (!age) return '';
  const v = age.value;
  let txt;
  if (v < 1 / 12) {
    const days = Math.max(0, Math.round(v * 365.25));
    txt = days <= 1 ? (days === 0 ? "aujourd'hui" : '1 jour') : `${days} jours`;
  } else if (v < 1) txt = `${Math.round(v * 12)} mois`;
  else txt = `${Math.floor(v)} an${Math.floor(v) >= 2 ? 's' : ''}`;
  return age.exact ? txt : `≈ ${txt}`;
}

export function fmtMonths(list) {
  if (!list?.length) return '';
  const s = [...list].sort((a, b) => a - b);
  // regroupe les mois consécutifs : « mars → mai, sept. »
  const runs = [];
  for (const m of s) {
    const last = runs.at(-1);
    if (last && m === last[1] + 1) last[1] = m;
    else runs.push([m, m]);
  }
  return runs.map(([a, b]) => (a === b ? MONTHS.at(a - 1) : `${MONTHS.at(a - 1)} → ${MONTHS.at(b - 1)}`)).join(', ');
}

export function displayName(sp) {
  return sp.nickname || sp.common_name || sp.species?.common_name || 'Sans nom';
}

export function fmtMeters(m) {
  if (m == null) return '';
  return m < 10 ? `${m.toFixed(1).replace('.', ',')} m` : `${Math.round(m)} m`;
}
