import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { RouteGeometry } from '../api';

// Vite fingerprints Leaflet's default marker image imports in a way its
// own CSS can't resolve; point the default icon at the same package
// version's files on a CDN instead of shipping broken image links.
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

interface RouteMapProps {
  from: { lat: number; lon: number };
  to: { lat: number; lon: number };
  geometry: RouteGeometry;
}

export default function RouteMap({ from, to, geometry }: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = L.map(containerRef.current);
    mapRef.current = map;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    const latlngs = geometry.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]);
    const line = L.polyline(latlngs, { color: '#d9a441', weight: 4, opacity: 0.85 });
    layer.addLayer(line);
    layer.addLayer(L.marker([from.lat, from.lon]).bindTooltip('You'));
    layer.addLayer(L.marker([to.lat, to.lon]).bindTooltip('Destination'));
    map.fitBounds(line.getBounds(), { padding: [24, 24] });
    return () => {
      layer.remove();
    };
  }, [from.lat, from.lon, to.lat, to.lon, geometry]);

  return <div ref={containerRef} className="route-map" role="img" aria-label="Route map" />;
}
