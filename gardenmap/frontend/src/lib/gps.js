// Mesure GPS moyennée : on collecte les positions pendant quelques secondes
// et on fait une moyenne pondérée par 1/précision².

export const inIframe = (() => {
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
})();

export function geolocationAvailable() {
  return 'geolocation' in navigator && window.isSecureContext;
}

export function explainGeoError(err) {
  if (!window.isSecureContext) return "Le GPS n'est disponible que sur une page HTTPS.";
  if (err?.code === 1)
    return inIframe
      ? "Le GPS est bloqué dans cette vue. Ouvrez GardenMap en plein écran, ou utilisez la position de l'app Home Assistant."
      : "Autorisez la localisation pour ce site dans les réglages du navigateur.";
  if (err?.code === 2) return 'Position indisponible : vérifiez que la localisation du téléphone est activée.';
  if (err?.code === 3) return "Le GPS n'a pas répondu à temps.";
  return err?.message || 'Erreur de géolocalisation.';
}

function weightedMean(samples) {
  let wsum = 0, lat = 0, lon = 0;
  for (const s of samples) {
    const w = 1 / Math.max(s.accuracy, 1) ** 2;
    wsum += w; lat += s.lat * w; lon += s.lon * w;
  }
  const best = Math.min(...samples.map((s) => s.accuracy));
  // précision estimée : meilleure mesure, améliorée par le nombre de mesures (borne basse 1 m)
  const accuracy = Math.max(1, best / Math.sqrt(Math.min(samples.length, 10)));
  return { lat: lat / wsum, lon: lon / wsum, accuracy, count: samples.length };
}

/**
 * Démarre une mesure. onUpdate reçoit { lat, lon, accuracy, count, elapsed, last } à chaque position.
 * Renvoie { stop(), result() }.
 */
export function startAveraging({ onUpdate, onError, maxAccuracy = 50 }) {
  const samples = [];
  const t0 = Date.now();
  const id = navigator.geolocation.watchPosition(
    (pos) => {
      const s = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy };
      // les premières mesures très imprécises (réseau) sont écartées dès qu'on a mieux
      if (s.accuracy <= maxAccuracy || samples.length === 0) samples.push(s);
      const good = samples.filter((x) => x.accuracy <= Math.max(maxAccuracy, Math.min(...samples.map((y) => y.accuracy)) * 3));
      onUpdate?.({ ...weightedMean(good), elapsed: (Date.now() - t0) / 1000, last: s });
    },
    (err) => onError?.(err),
    { enableHighAccuracy: true, maximumAge: 0, timeout: 30000 },
  );
  return {
    stop: () => navigator.geolocation.clearWatch(id),
    result: () => (samples.length ? weightedMean(samples) : null),
  };
}

/** Suivi continu de la position (point bleu sur la carte). */
export function watchLive(onPos, onError) {
  const id = navigator.geolocation.watchPosition(
    (pos) => onPos({ lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy }),
    onError,
    { enableHighAccuracy: true, maximumAge: 2000 },
  );
  return () => navigator.geolocation.clearWatch(id);
}
