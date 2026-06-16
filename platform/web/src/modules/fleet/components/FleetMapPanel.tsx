import { useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { FallbackTileLayer, type TileDef } from "./FallbackTileLayer";
import "./fleet-map.css";

export type LiveVehicle = {
  vehicle_id: number;
  plate_no?: string;
  lat?: number | null;
  lng?: number | null;
  last_lat?: number | null;
  last_lng?: number | null;
  status?: string;
  online?: boolean;
};

export type MapConfig = {
  provider?: string;
  tileProvider?: string;
  amapKey?: string;
};

function vehicleLat(v: LiveVehicle): number | null {
  const lat = v.lat ?? v.last_lat;
  return lat != null ? Number(lat) : null;
}

function vehicleLng(v: LiveVehicle): number | null {
  const lng = v.lng ?? v.last_lng;
  return lng != null ? Number(lng) : null;
}

function resolveTiles(cfg: MapConfig): TileDef {
  const p = (cfg.tileProvider || cfg.provider || "gaode").toLowerCase();
  if (p === "gaode") {
    const base =
      "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}";
    const url = cfg.amapKey ? `${base}&key=${cfg.amapKey}` : base;
    return { id: "gaode", url, subdomains: ["1", "2", "3", "4"], attribution: "&copy; 高德" };
  }
  return {
    id: "osm",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    subdomains: ["a", "b", "c"],
    attribution: "&copy; OpenStreetMap",
  };
}

function MapResizeFix() {
  const map = useMap();
  useEffect(() => {
    const fix = () => map.invalidateSize();
    fix();
    const t1 = window.setTimeout(fix, 100);
    const t2 = window.setTimeout(fix, 400);
    const ro = new ResizeObserver(fix);
    const el = map.getContainer().parentElement;
    if (el) ro.observe(el);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      ro.disconnect();
    };
  }, [map]);
  return null;
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length < 1) return;
    if (points.length === 1) {
      map.setView(points[0], 14);
      return;
    }
    map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 15 });
  }, [map, points]);
  return null;
}

type Props = {
  mapConfig: MapConfig | null;
  vehicles: LiveVehicle[];
  className?: string;
};

export function FleetMapPanel({ mapConfig, vehicles, className }: Props) {
  const tiles = useMemo(() => resolveTiles(mapConfig || {}), [mapConfig]);

  const points = useMemo(() => {
    const pts: [number, number][] = [];
    for (const v of vehicles) {
      const lat = vehicleLat(v);
      const lng = vehicleLng(v);
      if (lat != null && lng != null) pts.push([lat, lng]);
    }
    return pts;
  }, [vehicles]);

  const center: [number, number] = points[0] || [28.2, 112.98];

  return (
    <div
      className={`fleet-map-shell rounded-lg border border-gray-200 overflow-hidden min-h-[420px] ${className || ""}`}
      style={{ height: 420 }}
    >
      <MapContainer
        center={center}
        zoom={12}
        className="h-full w-full"
        style={{ height: "100%", minHeight: 420, width: "100%" }}
        scrollWheelZoom
      >
        <FallbackTileLayer primary={tiles} />
        <MapResizeFix />
        <FitBounds points={points} />
        {vehicles.map((v) => {
          const lat = vehicleLat(v);
          const lng = vehicleLng(v);
          if (lat == null || lng == null) return null;
          return (
            <CircleMarker
              key={v.vehicle_id}
              center={[lat, lng]}
              radius={8}
              pathOptions={{ color: "#2563eb", fillColor: "#3b82f6", fillOpacity: 0.9 }}
            >
              <Popup>
                {v.plate_no || v.vehicle_id} · {v.online ? "在线" : v.status || "—"}
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
