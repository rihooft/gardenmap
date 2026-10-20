import { test } from 'node:test';
import assert from 'node:assert/strict';

// geomap.js importe Leaflet (navigateur) : on teste ici les fonctions pures en les isolant.
const src = (await import('node:fs')).readFileSync(new URL('./geomap.js', import.meta.url), 'utf8');
const pure = src.slice(src.indexOf('/** Surface (m²)'));
const mod = await import('data:text/javascript,' + encodeURIComponent(pure.replace(/^export /gm, 'export ')));
const { measureGeometry, fmtMeasure, parseLatLon } = mod;

const lat0 = 48.835, lon0 = 2.52;
const off = (n, e) => [lon0 + e / (111195 * Math.cos((lat0 * Math.PI) / 180)), lat0 + n / 111195];

test('surface d\'un carré de 10 m', () => {
  const ring = [off(0, 0), off(0, 10), off(10, 10), off(10, 0), off(0, 0)];
  const m = measureGeometry({ type: 'Polygon', coordinates: [ring] });
  assert.ok(Math.abs(m.area_m2 - 100) < 0.2);
  assert.equal(fmtMeasure(m), '100 m²');
});

test('longueur d\'une ligne 3-4-5', () => {
  const m = measureGeometry({ type: 'LineString', coordinates: [off(0, 0), off(30, 40)] });
  assert.ok(Math.abs(m.length_m - 50) < 0.05);
  assert.equal(fmtMeasure({ length_m: 12.34 }), '12,3 m');
  assert.equal(fmtMeasure({ area_m2: 25000 }), '2,50 ha');
});

test('analyse des coordonnées collées', () => {
  assert.deepEqual(parseLatLon('48.8350, 2.5200'), { lat: 48.835, lon: 2.52 });
  assert.deepEqual(parseLatLon('48,8350 2,5200'), { lat: 48.835, lon: 2.52 });
  assert.deepEqual(parseLatLon('https://www.google.com/maps/@48.8361,2.5187,19z'), { lat: 48.8361, lon: 2.5187 });
  assert.equal(parseLatLon('bonjour'), null);
});
