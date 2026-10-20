// Appels à l'API. URL relatives : elles fonctionnent sous le chemin d'ingress de Home Assistant.

async function request(method, path, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.body = JSON.stringify(body);
    opts.headers['content-type'] = 'application/json';
  }
  const r = await fetch(`api/${path}`, opts);
  if (r.status === 204) return null;
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new Error(data?.detail || `Erreur ${r.status}`);
  return data;
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b ?? {}),
  put: (p, b) => request('PUT', p, b),
  del: (p) => request('DELETE', p),
};

export const photoUrl = (id, size = 'md') => `api/photos/${id}/${size}`;

/** Date locale ISO sans fuseau (AAAA-MM-JJTHH:MM:SS) à partir d'un horodatage en ms. */
export function localIso(ms) {
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export async function uploadPhotos(specimenId, files, caption = '') {
  const fd = new FormData();
  const dates = [];
  for (const f of files) {
    fd.append('files', f, f.name);
    dates.push(f.lastModified ? localIso(f.lastModified) : null);
  }
  fd.append('fallback_dates', JSON.stringify(dates));
  if (caption) fd.append('caption', caption);
  return api.post(`specimens/${specimenId}/photos`, fd);
}
