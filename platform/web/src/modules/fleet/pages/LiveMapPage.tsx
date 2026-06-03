import React, { useEffect, useState } from "react";
import { hsapApi } from "@/app/hsap-api";
import { PageQueryState } from "@/components/PageQueryState";
import { Badge } from "@/components/ui/Badge";

export const LiveMapPage: React.FC = () => {
  const [live, setLive] = useState<Record<string, unknown> | null>(null);
  const [mapConfig, setMapConfig] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [l, m] = await Promise.all([hsapApi.fleetLive(), hsapApi.fleetMapConfig()]);
      setLive(l);
      setMapConfig(m);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const vehicles = (live?.vehicles || []) as Record<string, unknown>[];

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>实时地图</h1>
        <p>车辆 GPS 实时位置追踪</p>
      </div>

      <PageQueryState loading={loading} error={error}>
        {/* Map placeholder — Leaflet/AMap will be integrated */}
        <div className="card mb-4" style={{ height: "400px", background: "#e5e7eb" }}>
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center">
              <div className="text-4xl mb-2">🗺️</div>
              <p>地图组件 (Leaflet/高德)</p>
              <p className="text-xs mt-1">底图: {mapConfig?.tile_provider as string || "gaode"}</p>
            </div>
          </div>
        </div>

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
                {vehicles.map((v, i) => (
                  <tr key={i}>
                    <td className="font-medium">{v.plate_no as string || "—"}</td>
                    <td className="font-mono text-xs">
                      {String(v.lat ?? "—")}, {String(v.lng ?? "—")}
                    </td>
                    <td>{v.speed_kmh != null ? `${v.speed_kmh} km/h` : "—"}</td>
                    <td><Badge variant="success">在线</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button onClick={load} className="mt-3 text-sm text-blue-600 hover:underline">刷新</button>
        </div>
      </PageQueryState>
    </div>
  );
};
