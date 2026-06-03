import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";

type SimJob = Record<string, unknown>;

const SCENES = [
  { key: "urban_highway", label: "城市快速路", icon: "🛣️" },
  { key: "urban_street", label: "城市街道", icon: "🏙️" },
  { key: "rural_road", label: "乡村道路", icon: "🌾" },
  { key: "tunnel", label: "隧道", icon: "🚇" },
  { key: "night_city", label: "夜间城市", icon: "🌃" },
  { key: "rain_highway", label: "雨天高速", icon: "🌧️" },
  { key: "fog_rural", label: "雾天乡村", icon: "🌫️" },
];

const CAMERAS = [
  { key: "truck_front", label: "卡车前视", icon: "🚛", height: "2.5m", fov: "75°" },
  { key: "truck_side", label: "卡车侧视", icon: "🚛", height: "2.5m", fov: "100°" },
  { key: "car_front", label: "轿车前视", icon: "🚗", height: "1.2m", fov: "60°" },
  { key: "car_wide", label: "轿车广角", icon: "🚗", height: "1.2m", fov: "120°" },
];

const WEATHERS = ["clear", "cloudy", "rain", "fog", "night"];
const WEATHER_LABELS: Record<string, string> = { clear: "晴天", cloudy: "多云", rain: "雨天", fog: "大雾", night: "夜间" };
const DENSITY_LABELS: Record<string, string> = { sparse: "稀疏 5-10", medium: "中等 10-30", dense: "密集 30+" };
const ALL_CLASSES = ["Pedestrain", "Car", "Truck", "Bus", "Motor-vehicles", "Tricycle", "cones"];

const JOBS_PAGE = 20;

export const SimulationStudioPage: React.FC = () => {
  // Config form
  const [scene, setScene] = useState("urban_highway");
  const [camera, setCamera] = useState("truck_front");
  const [weather, setWeather] = useState("clear");
  const [objects, setObjects] = useState<string[]>(["Pedestrain", "Car", "Truck", "Bus"]);
  const [density, setDensity] = useState("medium");
  const [count, setCount] = useState(100);
  const [fovVariant, setFovVariant] = useState(false);
  const [note, setNote] = useState("");
  const [generating, setGenerating] = useState(false);
  const [info, setInfo] = useState<string | null>(null);

  // Jobs list
  const [jobs, setJobs] = useState<SimJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadJobs = async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`/api/v1/simulate/jobs?limit=50`, {
        headers: { Authorization: `Bearer ${hsapApi.getToken()}` }, cache: "no-store",
      }).then((r) => r.json());
      setJobs((res.items || []) as SimJob[]);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  };

  useEffect(() => { loadJobs(); }, []);

  const toggleObject = (obj: string) => {
    setObjects((prev) => prev.includes(obj) ? prev.filter((o) => o !== obj) : [...prev, obj]);
  };

  const handleGenerate = async () => {
    if (objects.length === 0) { setError("请至少选择一种目标类别"); return; }
    setGenerating(true); setError(null); setInfo(null);
    try {
      const res = await fetch("/api/v1/simulate/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${hsapApi.getToken()}` },
        body: JSON.stringify({ scene, camera, weather, objects, density, count, fov_variant: fovVariant, note }),
      }).then((r) => r.json());
      setInfo(`任务已提交: ${res.id}`);
      loadJobs();
    } catch (e) { setError(String(e)); }
    setGenerating(false);
  };

  const handleIngest = async (jobId: string) => {
    try {
      const res = await fetch(`/api/v1/simulate/jobs/${jobId}/ingest?task=adas`, {
        method: "POST",
        headers: { Authorization: `Bearer ${hsapApi.getToken()}` },
      }).then((r) => r.json());
      if (res.ok) setInfo(`已入库: ${res.batch}`);
      else setError(String(res.error));
      loadJobs();
    } catch (e) { setError(String(e)); }
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>仿真工坊</h1>
        <p>世界模型生成合成数据 — 自动标注，直接入库</p>
      </div>

      {info && <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4 text-sm text-green-700">{info}</div>}
      {error && <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-2 gap-6">
        {/* Left: Config panel */}
        <div>
          <div className="card mb-4">
            <div className="card-header">场景配置</div>

            {/* Scene */}
            <div className="mb-4">
              <label className="form-label">场景模板</label>
              <div className="grid grid-cols-4 gap-1.5">
                {SCENES.map((s) => (
                  <button key={s.key} onClick={() => setScene(s.key)}
                    className={`p-2 rounded-lg text-xs text-center transition-colors ${
                      scene === s.key ? "bg-blue-600 text-white" : "bg-gray-50 text-gray-600 hover:bg-gray-100"
                    }`}>
                    <div className="text-lg">{s.icon}</div>
                    <div>{s.label}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Camera */}
            <div className="mb-4">
              <label className="form-label">相机参数</label>
              <div className="grid grid-cols-2 gap-1.5">
                {CAMERAS.map((c) => (
                  <button key={c.key} onClick={() => setCamera(c.key)}
                    className={`p-2 rounded-lg text-xs transition-colors ${
                      camera === c.key ? "bg-blue-600 text-white" : "bg-gray-50 text-gray-600 hover:bg-gray-100"
                    }`}>
                    <div>{c.icon} {c.label}</div>
                    <div className="text-[10px] opacity-70">高度 {c.height} · FOV {c.fov}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Weather */}
            <div className="mb-4">
              <label className="form-label">天气/光照</label>
              <div className="flex gap-1.5">
                {WEATHERS.map((w) => (
                  <button key={w} onClick={() => setWeather(w)}
                    className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                      weather === w ? "bg-blue-600 text-white" : "bg-gray-50 text-gray-600 hover:bg-gray-100"
                    }`}>{WEATHER_LABELS[w] || w}</button>
                ))}
              </div>
            </div>

            {/* Objects */}
            <div className="mb-4">
              <label className="form-label">目标类别 ({objects.length}/7)</label>
              <div className="flex flex-wrap gap-1">
                {ALL_CLASSES.map((c) => (
                  <button key={c} onClick={() => toggleObject(c)}
                    className={`px-2.5 py-1 rounded-lg text-xs transition-colors ${
                      objects.includes(c) ? "bg-blue-600 text-white" : "bg-gray-50 text-gray-500"
                    }`}>{c}</button>
                ))}
              </div>
            </div>

            {/* Density + Count */}
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="form-label">目标密度</label>
                <select className="form-input" value={density} onChange={(e) => setDensity(e.target.value)}>
                  {Object.entries(DENSITY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div>
                <label className="form-label">生成数量</label>
                <select className="form-input" value={count} onChange={(e) => setCount(Number(e.target.value))}>
                  {[50, 100, 200, 500, 1000, 2000, 5000].map((n) => <option key={n} value={n}>{n} 张</option>)}
                </select>
              </div>
            </div>

            {/* Multi-FOV variant */}
            <div className="mb-4">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={fovVariant} onChange={(e) => setFovVariant(e.target.checked)} className="rounded" />
                <span>生成多FOV变体（卡车+轿车视角各一份）</span>
              </label>
            </div>

            {/* Note */}
            <div className="mb-4">
              <label className="form-label">备注</label>
              <input className="form-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="如：补卡车视角雨天行人数据" />
            </div>

            <Button variant="primary" onClick={handleGenerate} loading={generating} className="w-full">
              🚀 生成仿真数据
            </Button>
          </div>
        </div>

        {/* Right: Job history */}
        <div>
          <div className="card">
            <div className="card-header flex items-center justify-between">
              <span>生成历史</span>
              <Button size="small" variant="default" onClick={loadJobs}>刷新</Button>
            </div>

            <PageQueryState loading={loading} error={error} empty={jobs.length === 0} emptyMessage="暂无生成记录">
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {jobs.map((job) => {
                  const params = job.params as Record<string, unknown> | undefined;
                  return (
                    <div key={job.id as string} className="border border-gray-100 rounded-lg p-3 hover:bg-gray-50 transition-colors">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-mono text-gray-400">{(job.id as string).slice(0, 20)}...</span>
                        <StatusBadge status={(job.status as string) || "queued"} />
                      </div>
                      {params && (
                        <div className="text-xs text-gray-500 space-y-0.5">
                          <div>{String(params.scene_label ?? "")} · {String(params.camera_label ?? "")} · {WEATHER_LABELS[String(params.weather ?? "")] || String(params.weather ?? "")}</div>
                          <div className="flex gap-1">
                            {(params.objects as string[])?.map((o) => <Badge key={o} size="small" variant="default">{o}</Badge>)}
                          </div>
                          <div>{DENSITY_LABELS[params.density as string]} · {params.count as number} 张</div>
                          {params.note != null && String(params.note) && <div className="text-gray-400 italic">"{String(params.note)}"</div>}
                        </div>
                      )}
                      {job.status === "completed" && !Boolean(job.batch_registered) && (
                        <button onClick={() => handleIngest(job.id as string)}
                          className="mt-2 text-xs text-blue-600 hover:underline">入库到训练集 →</button>
                      )}
                      {Boolean(job.batch_registered) && (
                        <span className="mt-2 text-xs text-green-600 inline-block">✓ 已入库: {String(job.batch_name ?? "")}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </PageQueryState>
          </div>
        </div>
      </div>
    </div>
  );
};
