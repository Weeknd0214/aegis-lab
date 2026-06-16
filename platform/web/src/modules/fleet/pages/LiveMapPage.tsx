import React, { useCallback, useEffect, useMemo, useState } from "react";
import { hsapApi } from "@/app/hsap-api";
import { PageQueryState } from "@/components/PageQueryState";
import { Badge } from "@/components/ui/Badge";
import { FleetMapPanel, type LiveVehicle } from "../components/FleetMapPanel";

type LiveResponse = {
  vehicles?: LiveVehicle[];
  stats?: Record<string, unknown>;
};

export const LiveMapPage: React.FC = () => {
  const [live, setLive] = useState<LiveResponse | null>(null);
  const [mapConfig, setMapConfig] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [l, m] = await Promise.all([hsapApi.fleetLive(), hsapApi.fleetMapConfig()]);
      setLive(l as LiveResponse);
      setMapConfig(m);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const pollSec = Number(mapConfig?.pollIntervalSec ?? 5);
    const ms = Math.max(3, pollSec) * 1000;
    const timer = window.setInterval(load, ms);
    return () => window.clearInterval(timer);
  }, [load, mapConfig?.pollIntervalSec]);

  const vehicles = useMemo(
    () =>
      ((live?.vehicles || []) as Record<string, unknown>[]).map((v) => ({
        vehicle_id: Number(v.vehicle_id ?? v.id ?? 0),
        plate_no: String(v.plate_no ?? ""),
        lat: (v.lat ?? v.last_lat) as number | null | undefined,
        lng: (v.lng ?? v.last_lng) as number | null | undefined,
        last_lat: v.last_lat as number | null | undefined,
        last_lng: v.last_lng as number | null | undefined,
        speed_kmh: (v.speed_kmh ?? v.last_speed_kmh) as number | null | undefined,
        online: Boolean(v.online),
        status: String(v.status ?? ""),
      })),
    [live?.vehicles],
  );

  const tileLabel = String(mapConfig?.tileProvider ?? mapConfig?.provider ?? "gaode");

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>实时地图</h1>
        <p>车辆 GPS 实时位置追踪 · 底图 {tileLabel}</p>
      </div>

      <PageQueryState loading={loading} error={error}>
        <FleetMapPanel
          mapConfig={mapConfig as { provider?: string; tileProvider?: string; amapKey?: string } | null}
          vehicles={vehicles}
          className="mb-4"
        />

        <div className="card">
          <div className="card-header">在线车辆 ({vehicles.length})</div>
          {vehicles.length === 0 ? (
            <p className="text-sm text-gray-400">暂无在线车辆</p>
          ) : (
            <table className="table-auto">
              <thead>
                <tr>
                  <th>车牌号</th>
                  <th>经纬度</th>
                  <th>速度</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {vehicles.map((v) => {
                  const lat = v.lat ?? v.last_lat;
                  const lng = v.lng ?? v.last_lng;
                  return (
                    <tr key={v.vehicle_id}>
                      <td className="font-medium">{v.plate_no || "—"}</td>
                      <td className="font-mono text-xs">
                        {lat != null && lng != null ? `${lat.toFixed(5)}, ${lng.toFixed(5)}` : "—, —"}
                      </td>
                      <td>{v.speed_kmh != null ? `${v.speed_kmh} km/h` : "—"}</td>
                      <td>
                        <Badge variant={v.online ? "success" : "default"}>
                          {v.online ? "在线" : "离线"}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          <button type="button" onClick={load} className="mt-3 text-sm text-blue-600 hover:underline">
            刷新
          </button>
        </div>
      </PageQueryState>
    </div>
  );
};
