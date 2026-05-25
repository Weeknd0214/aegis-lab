import { useEffect, useMemo, useState } from "react";
import { api, type CatalogReport, type InspectUploadResponse } from "../api/client";
import { LANE_DATA_VIZ_ENABLED } from "../config/featureFlags";

type CatalogVersion = {
  name: string;
  enabled: boolean;
  train_images?: number;
  val_images?: number;
  test_images?: number;
  class_counts?: Record<string, number>;
  path?: string;
  role?: string;
  frozen?: boolean;
  label_files?: number;
  total_boxes?: number;
  sampled?: boolean;
  bbox_points?: [number, number][];
  lane_quality?: {
    analyzed_frames?: number;
    lane_count_hist?: Record<string, number>;
    length_hist?: { left: number; right: number; count: number }[];
    curvature_hist?: { left: number; right: number; count: number }[];
  };
};

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg - 90) * (Math.PI / 180);
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
}

function radarPoints(values: number[], cx = 110, cy = 110, radius = 76): string {
  if (!values.length) return "";
  return values
    .map((v, i) => {
      const angle = (-90 + (360 / values.length) * i) * (Math.PI / 180);
      const r = Math.max(0, Math.min(1, v)) * radius;
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      return `${x},${y}`;
    })
    .join(" ");
}

export function CatalogPage() {
  const [cat, setCat] = useState<CatalogReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [cacheHint, setCacheHint] = useState("");
  const [project, setProject] = useState<"dms" | "lane">("dms");
  const [selectedTask, setSelectedTask] = useState<string>("");
  const [selectedVersion, setSelectedVersion] = useState<string>("");
  const [inspectProject, setInspectProject] = useState<"dms" | "lane">("dms");
  const [inspectTask, setInspectTask] = useState<string>("dam");
  const [inspectPath, setInspectPath] = useState<string>("");
  const [inspecting, setInspecting] = useState(false);
  const [inspectResult, setInspectResult] = useState<InspectUploadResponse["normalized"] | null>(null);
  const [inspectError, setInspectError] = useState<string>("");

  const load = async (refresh = false) => {
    setLoading(true);
    setLoadError("");
    try {
      const data = await api.catalog(refresh);
      setCat(data);
      const meta = data._cache;
      if (meta?.cached) {
        const src = meta.build_source === "reports" ? "报表缓存" : "扫描缓存";
        setCacheHint(`${src} · ${Math.round(meta.cache_age_sec || 0)}s 前更新`);
      } else if (refresh) {
        setCacheHint("已强制刷新");
      } else {
        setCacheHint("已重新扫描");
      }
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  const inspectSource = async () => {
    const sourcePath = inspectPath.trim();
    if (!sourcePath) {
      setInspectError("请先输入目录路径");
      return;
    }
    setInspecting(true);
    setInspectError("");
    try {
      const res = await api.inspectUploadPath(
        inspectProject,
        sourcePath,
        inspectProject === "dms" ? inspectTask : undefined
      );
      setInspectResult(res.normalized);
    } catch (e) {
      setInspectResult(null);
      setInspectError(e instanceof Error ? e.message : "目录分析失败");
    } finally {
      setInspecting(false);
    }
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!cat) return;
    const dmsTasks = Object.keys(cat.dms || {});
    const lanePacks = Object.keys(cat.lane || {});
    if (project === "dms") {
      const first = selectedTask || dmsTasks[0] || "";
      setSelectedTask(first);
      const firstPack = (cat.dms?.[first]?.packs?.[0]?.name) || "";
      setSelectedVersion(firstPack);
    } else {
      const first = selectedTask || lanePacks[0] || "";
      setSelectedTask(first);
      setSelectedVersion(first);
    }
  }, [cat, project]);

  const dmsVersions = useMemo<CatalogVersion[]>(() => {
    if (!cat || project !== "dms" || !selectedTask) return [];
    return cat.dms?.[selectedTask]?.packs || [];
  }, [cat, project, selectedTask]);

  const laneVersions = useMemo<CatalogVersion[]>(() => {
    if (!cat || project !== "lane") return [];
    return Object.entries(cat.lane || {}).map(([name, info]) => ({
      name,
      enabled: Boolean(info.enabled),
      train_images: info.train_lines || 0,
      val_images: info.val_lines || 0,
      test_images: info.test_lines || 0,
      class_counts: {},
      path: info.path,
      lane_quality: info.quality,
    }));
  }, [cat, project]);

  const versions: CatalogVersion[] = project === "dms" ? dmsVersions : laneVersions;
  const current = versions.find((v) => v.name === selectedVersion) || versions[0];
  const classPairs = Object.entries((current?.class_counts || {}) as Record<string, number>)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  const classMax = classPairs[0]?.[1] || 1;
  const classTotal = classPairs.reduce((acc, [, v]) => acc + v, 0);

  const versionFeatures = useMemo(() => {
    if (project !== "dms") return [] as Array<{
      name: string;
      samples: number;
      boxes: number;
      density: number;
      avg_area: number;
      small_ratio: number;
      bbox_points: [number, number][];
    }>;
    return dmsVersions.map((v) => {
      const samples = (v.train_images || 0) + (v.val_images || 0) + (v.test_images || 0);
      const boxes = v.total_boxes || 0;
      const points = (v.bbox_points || []).filter((p) => p.length >= 2) as [number, number][];
      const areas = points.map(([w, h]) => w * h);
      const avg_area = areas.length ? areas.reduce((a, b) => a + b, 0) / areas.length : 0;
      const small_ratio = areas.length ? areas.filter((a) => a < 0.02).length / areas.length : 0;
      return {
        name: v.name,
        samples,
        boxes,
        density: samples > 0 ? boxes / samples : 0,
        avg_area,
        small_ratio,
        bbox_points: points,
      };
    });
  }, [project, dmsVersions]);

  const featureMax = useMemo(() => {
    const samples = Math.max(1, ...versionFeatures.map((v) => v.samples));
    const density = Math.max(1, ...versionFeatures.map((v) => v.density));
    const boxes = Math.max(1, ...versionFeatures.map((v) => v.boxes));
    const avgArea = Math.max(1e-6, ...versionFeatures.map((v) => v.avg_area));
    const smallRatio = Math.max(1e-6, ...versionFeatures.map((v) => v.small_ratio));
    return { samples, density, boxes, avgArea, smallRatio };
  }, [versionFeatures]);
  const colorPalette = ["#22d3ee", "#a78bfa", "#34d399", "#f59e0b", "#60a5fa", "#f472b6", "#fb7185", "#94a3b8"];
  const currentFeature = versionFeatures.find((v) => v.name === current?.name);
  const whBins = useMemo(() => {
    const bins = Array.from({ length: 10 }, () => Array.from({ length: 10 }, () => 0));
    const points = currentFeature?.bbox_points || [];
    for (const [w, h] of points) {
      const xi = Math.min(9, Math.max(0, Math.floor(w * 10)));
      const yi = Math.min(9, Math.max(0, Math.floor(h * 10)));
      bins[9 - yi][xi] += 1;
    }
    let max = 0;
    for (const row of bins) for (const v of row) max = Math.max(max, v);
    return { bins, max };
  }, [currentFeature]);
  const radarAxes = ["样本量", "标签框", "框密度", "平均面积", "小目标占比"];
  const radarMetrics = useMemo(() => {
    return versionFeatures.slice(0, 4).map((v) => ({
      name: v.name,
      values: [
        v.samples / featureMax.samples,
        v.boxes / featureMax.boxes,
        v.density / featureMax.density,
        v.avg_area / featureMax.avgArea,
        v.small_ratio / featureMax.smallRatio,
      ],
    }));
  }, [versionFeatures, featureMax]);
  const laneCountPairs = useMemo(() => {
    const hist = current?.lane_quality?.lane_count_hist || {};
    const entries = Object.entries(hist);
    entries.sort((a, b) => {
      const av = a[0] === "8+" ? 999 : Number(a[0]);
      const bv = b[0] === "8+" ? 999 : Number(b[0]);
      return av - bv;
    });
    return entries;
  }, [current]);
  const laneLengthHist = current?.lane_quality?.length_hist || [];
  const laneCurvHist = current?.lane_quality?.curvature_hist || [];
  const laneLengthMax = Math.max(1, ...laneLengthHist.map((x) => x.count));
  const laneCurvMax = Math.max(1, ...laneCurvHist.map((x) => x.count));

  const kpis = useMemo(() => {
    const allDms = Object.values(cat?.dms || {}) as NonNullable<CatalogReport["dms"]>[string][];
    const allDmsPacks = allDms.flatMap((x) => x.packs || []);
    const allLane = Object.values(cat?.lane || {}) as NonNullable<CatalogReport["lane"]>[string][];
    const totalVersions = allDmsPacks.length + allLane.length;
    const enabledVersions = allDmsPacks.filter((x) => x.enabled).length + allLane.filter((x) => x.enabled).length;
    const totalSamples = allDmsPacks.reduce((acc, x) => acc + (x.train_images || 0) + (x.val_images || 0) + (x.test_images || 0), 0)
      + allLane.reduce((acc, x) => acc + (x.train_lines || 0) + (x.val_lines || 0) + (x.test_lines || 0), 0);
    const totalBoxes = allDmsPacks.reduce((acc, x) => acc + (x.total_boxes || 0), 0);
    return { totalVersions, enabledVersions, totalSamples, totalBoxes };
  }, [cat]);
  const inspectSplits = useMemo(() => {
    const raw = inspectResult?.split_counts || {};
    return [
      ["train", raw.train || 0],
      ["val", raw.val || 0],
      ["test", raw.test || 0],
    ] as Array<[string, number]>;
  }, [inspectResult]);
  const inspectTotal = inspectSplits.reduce((acc, [, v]) => acc + v, 0);

  const fmt = (n: number) => n.toLocaleString("zh-CN");

  if (loading && !cat) return <p className="empty-state">加载 catalog 数据中…</p>;
  if (loadError && !cat) return <p className="empty-state">{loadError}</p>;
  if (!cat) return <p className="empty-state">暂无数据</p>;

  return (
    <>
      {cacheHint && <p className="audit-note" style={{ marginBottom: 8 }}>{cacheHint}</p>}
      <div className="kpi-strip">
        <div className="kpi"><span className="kpi-val">{fmt(kpis.totalVersions)}</span><span className="kpi-lbl">接入数据版本数</span></div>
        <div className="kpi"><span className="kpi-val">{fmt(kpis.enabledVersions)}</span><span className="kpi-lbl">启用训练版本数</span></div>
        <div className="kpi"><span className="kpi-val">{fmt(kpis.totalSamples)}</span><span className="kpi-lbl">可用样本总量</span></div>
        <div className="kpi"><span className="kpi-val">{fmt(kpis.totalBoxes)}</span><span className="kpi-lbl">DMS 标签框总量</span></div>
      </div>
      <div className="panel">
        <div className="panel-header"><h2>现有目录快速分析</h2></div>
        <div className="panel-body">
          <div className="crud-form">
            <label className="field">
              <span>Project</span>
              <select value={inspectProject} onChange={(e) => setInspectProject(e.target.value as "dms" | "lane")}>
                <option value="dms">dms</option>
                <option value="lane">lane</option>
              </select>
            </label>
            {inspectProject === "dms" && (
              <label className="field">
                <span>Task</span>
                <input value={inspectTask} onChange={(e) => setInspectTask(e.target.value)} placeholder="如 dam" />
              </label>
            )}
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>目录路径</span>
              <input
                value={inspectPath}
                onChange={(e) => setInspectPath(e.target.value)}
                placeholder="例如 /data/workspace/DMS/inbox/dam/batch_xxx"
              />
            </label>
            <div className="crud-actions" style={{ gridColumn: "1 / -1" }}>
              <button type="button" className="btn btn-primary" onClick={() => inspectSource()} disabled={inspecting}>
                {inspecting ? "分析中..." : "分析目录"}
              </button>
            </div>
          </div>
          {inspectError && <p className="empty-state">{inspectError}</p>}
          {inspectResult && (
            <div className="feature-grid" style={{ marginTop: 12 }}>
              <div className="feature-card">
                <h4>Split 分布环形图</h4>
                <div className="donut-wrap">
                  <svg viewBox="0 0 200 200" className="donut-svg" role="img" aria-label="目录 split 分布">
                    <circle cx="100" cy="100" r="70" fill="none" stroke="rgba(148,163,184,0.18)" strokeWidth="28" />
                    {(() => {
                      let angle = 0;
                      return inspectSplits.map(([name, value], idx) => {
                        const sweep = inspectTotal > 0 ? (value / inspectTotal) * 360 : 0;
                        const d = describeArc(100, 100, 70, angle, angle + sweep);
                        angle += sweep;
                        return <path key={name} d={d} fill="none" stroke={colorPalette[idx % colorPalette.length]} strokeWidth="28" />;
                      });
                    })()}
                    <text x="100" y="96" textAnchor="middle" className="donut-center-title">{inspectResult.format_id}</text>
                    <text x="100" y="116" textAnchor="middle" className="donut-center-sub">{fmt(inspectTotal)} samples</text>
                  </svg>
                  <div className="donut-legend">
                    {inspectSplits.map(([name, value], idx) => (
                      <div key={`inspect-${name}`} className="legend-item">
                        <i style={{ background: colorPalette[idx % colorPalette.length] }} />
                        <span>{name}</span>
                        <strong>{fmt(value)}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <div className="feature-card">
                <h4>识别摘要</h4>
                <p className="audit-note">source: <code>{inspectResult.source_path}</code></p>
                <p className="audit-note">annotations: {fmt(inspectResult.annotation_count || 0)}</p>
                <p className="audit-note">artifacts: {(inspectResult.artifacts || []).join(", ") || "—"}</p>
                {(inspectResult.warnings || []).length > 0 ? (
                  <ul className="audit-note">
                    {(inspectResult.warnings || []).map((w, idx) => <li key={`warn-${idx}`}>{w}</li>)}
                  </ul>
                ) : (
                  <p className="audit-note">warnings: none</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      <div className="grid-2-equal">
        <div className="panel">
          <div className="panel-header">
            <h2>数据版本列表</h2>
            <div className="audit-filters">
              <button type="button" className={`btn btn-sm ${project === "dms" ? "btn-primary" : "btn-ghost"}`} onClick={() => setProject("dms")}>DMS</button>
              <button type="button" className={`btn btn-sm ${project === "lane" ? "btn-primary" : "btn-ghost"}`} onClick={() => setProject("lane")}>Lane</button>
            </div>
          </div>
          <div className="panel-body">
            <div className="catalog-toolbar">
              <label className="field">
                <span>{project === "dms" ? "任务" : "包"}</span>
                <select
                  value={selectedTask}
                  onChange={(e) => {
                    const value = e.target.value;
                    setSelectedTask(value);
                    const firstPack = project === "dms" ? (cat.dms?.[value]?.packs?.[0]?.name || "") : value;
                    setSelectedVersion(firstPack);
                  }}
                >
                  {(project === "dms" ? Object.keys(cat.dms || {}) : Object.keys(cat.lane || {})).map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="version-table">
              <table className="data-table compact">
                <thead><tr><th>版本</th><th>状态</th><th>Train</th><th>Val</th><th>Test</th><th>总量</th></tr></thead>
                <tbody>
                  {versions.map((v) => {
                    const total = (v.train_images || 0) + (v.val_images || 0) + (v.test_images || 0);
                    return (
                      <tr
                        key={v.name}
                        className={current?.name === v.name ? "row-active" : ""}
                        onClick={() => setSelectedVersion(v.name)}
                        style={{ cursor: "pointer" }}
                      >
                        <td><strong>{v.name}</strong></td>
                        <td><span className={`badge ${v.enabled ? "badge-promoted" : "badge-idle"}`}>{v.enabled ? "启用中" : "未启用"}</span></td>
                        <td>{fmt(v.train_images || 0)}</td>
                        <td>{fmt(v.val_images || 0)}</td>
                        <td>{fmt(v.test_images || 0)}</td>
                        <td>{fmt(total)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><h2>版本标签分布</h2></div>
          <div className="panel-body">
            {current ? (
              <div>
                <p className="catalog-intro">
                  当前版本：<strong>{current.name}</strong> ·
                  Train {fmt(current.train_images || 0)} / Val {fmt(current.val_images || 0)} / Test {fmt(current.test_images || 0)}
                </p>
                {classPairs.length > 0 ? (
                  <div className="dist-list">
                    {classPairs.map(([name, value]) => (
                      <div key={name} className="dist-row">
                        <div className="dist-meta"><span>{name}</span><strong>{value}</strong></div>
                        <div className="progress-bar"><div className="progress-fill" style={{ width: `${Math.max(6, (value / classMax) * 100)}%` }} /></div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="empty-state">当前版本暂无标签分布数据（Lane 或未入库标签）。</p>
                )}
              </div>
            ) : <p className="empty-state">暂无可展示版本</p>}
          </div>
        </div>
      </div>
      <div className="panel">
        <div className="panel-header"><h2>标签特征可视化</h2></div>
        <div className="panel-body">
          {project === "dms" ? (
            <>
              <div className="feature-grid">
                <div className="feature-card">
                  <h4>类别结构环形图（当前版本）</h4>
                  {classPairs.length > 0 ? (
                    <div className="donut-wrap">
                      <svg viewBox="0 0 200 200" className="donut-svg" role="img" aria-label="类别结构环形图">
                        <circle cx="100" cy="100" r="70" fill="none" stroke="rgba(148,163,184,0.18)" strokeWidth="28" />
                        {(() => {
                          let angle = 0;
                          return classPairs.map(([name, value], idx) => {
                            const sweep = classTotal > 0 ? (value / classTotal) * 360 : 0;
                            const d = describeArc(100, 100, 70, angle, angle + sweep);
                            angle += sweep;
                            return <path key={name} d={d} fill="none" stroke={colorPalette[idx % colorPalette.length]} strokeWidth="28" strokeLinecap="butt" />;
                          });
                        })()}
                        <text x="100" y="96" textAnchor="middle" className="donut-center-title">{current?.name || "-"}</text>
                        <text x="100" y="116" textAnchor="middle" className="donut-center-sub">{fmt(classTotal)} boxes</text>
                      </svg>
                      <div className="donut-legend">
                        {classPairs.slice(0, 6).map(([name, value], idx) => (
                          <div key={`legend-${name}`} className="legend-item">
                            <i style={{ background: colorPalette[idx % colorPalette.length] }} />
                            <span>{name}</span>
                            <strong>{((value / Math.max(1, classTotal)) * 100).toFixed(1)}%</strong>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : <p className="empty-state">暂无类别数据</p>}
                </div>
                <div className="feature-card">
                  <h4>目标宽高散点密度分布（当前版本）</h4>
                  <svg viewBox="0 0 320 220" className="scatter-svg" role="img" aria-label="目标宽高散点密度分布">
                    <rect x="40" y="20" width="250" height="170" fill="rgba(148,163,184,0.05)" stroke="rgba(148,163,184,0.25)" />
                    {whBins.bins.map((row, yi) =>
                      row.map((v, xi) => {
                        if (!v) return null;
                        const alpha = Math.min(0.85, v / Math.max(1, whBins.max));
                        return (
                          <rect
                            key={`bin-${xi}-${yi}`}
                            x={40 + xi * 25}
                            y={20 + yi * 17}
                            width={25}
                            height={17}
                            fill={`rgba(34,211,238,${alpha.toFixed(3)})`}
                          />
                        );
                      })
                    )}
                    {(currentFeature?.bbox_points || []).slice(0, 400).map(([w, h], idx) => (
                      <circle
                        key={`wh-${idx}`}
                        cx={40 + w * 250}
                        cy={190 - h * 170}
                        r={1.6}
                        fill="rgba(255,255,255,0.35)"
                      />
                    ))}
                    <text x="294" y="205" textAnchor="end" className="scatter-axis">宽度 w</text>
                    <text x="12" y="20" className="scatter-axis">高度 h</text>
                  </svg>
                </div>
                <div className="feature-card">
                  <h4>版本多指标雷达对比</h4>
                  <div className="radar-wrap">
                    <svg viewBox="0 0 220 220" className="radar-svg" role="img" aria-label="版本多指标雷达图">
                      {[0.25, 0.5, 0.75, 1].map((lv) => (
                        <polygon
                          key={`grid-${lv}`}
                          points={radarPoints([lv, lv, lv, lv, lv], 110, 110, 76)}
                          fill="none"
                          stroke="rgba(148,163,184,0.2)"
                          strokeWidth="1"
                        />
                      ))}
                      {radarAxes.map((label, i) => {
                        const pt = radarPoints([1, 1, 1, 1, 1], 110, 110, 90).split(" ")[i];
                        const [x, y] = pt.split(",");
                        return <text key={label} x={Number(x)} y={Number(y)} className="radar-axis">{label}</text>;
                      })}
                      {radarMetrics.map((m, idx) => (
                        <polygon
                          key={`radar-${m.name}`}
                          points={radarPoints(m.values, 110, 110, 76)}
                          fill={colorPalette[idx % colorPalette.length]}
                          fillOpacity="0.16"
                          stroke={colorPalette[idx % colorPalette.length]}
                          strokeWidth="2"
                        />
                      ))}
                    </svg>
                    <div className="donut-legend">
                      {radarMetrics.map((m, idx) => (
                        <div key={`radar-leg-${m.name}`} className="legend-item">
                          <i style={{ background: colorPalette[idx % colorPalette.length] }} />
                          <span>{m.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              <div className="version-table" style={{ marginTop: 14 }}>
                <table className="data-table compact">
                  <thead><tr><th>版本</th><th>Train</th><th>Val</th><th>Test</th><th>标签框</th><th>框/样本</th><th>均值面积</th></tr></thead>
                  <tbody>
                    {versionFeatures.map((v) => {
                      const raw = dmsVersions.find((x) => x.name === v.name);
                      return (
                        <tr key={v.name}>
                          <td>{v.name}</td>
                          <td>{fmt(raw?.train_images || 0)}</td>
                          <td>{fmt(raw?.val_images || 0)}</td>
                          <td>{fmt(raw?.test_images || 0)}</td>
                          <td>{fmt(v.boxes)}</td>
                          <td>{v.density.toFixed(2)}</td>
                          <td>{(v.avg_area * 100).toFixed(2)}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : LANE_DATA_VIZ_ENABLED ? (
            <>
              <div className="feature-grid">
                <div className="feature-card">
                  <h4>每帧车道线数量分布</h4>
                  <div className="donut-wrap">
                    <svg viewBox="0 0 200 200" className="donut-svg" role="img" aria-label="每帧车道线数量分布">
                      <circle cx="100" cy="100" r="70" fill="none" stroke="rgba(148,163,184,0.18)" strokeWidth="28" />
                      {(() => {
                        const total = laneCountPairs.reduce((a, [, c]) => a + c, 0);
                        let angle = 0;
                        return laneCountPairs.map(([bucket, cnt], idx) => {
                          const sweep = total > 0 ? (cnt / total) * 360 : 0;
                          const d = describeArc(100, 100, 70, angle, angle + sweep);
                          angle += sweep;
                          return <path key={bucket} d={d} fill="none" stroke={colorPalette[idx % colorPalette.length]} strokeWidth="28" />;
                        });
                      })()}
                      <text x="100" y="100" textAnchor="middle" className="donut-center-title">线数分布</text>
                    </svg>
                    <div className="donut-legend">
                      {laneCountPairs.map(([bucket, cnt], idx) => (
                        <div key={`lc-${bucket}`} className="legend-item">
                          <i style={{ background: colorPalette[idx % colorPalette.length] }} />
                          <span>{bucket} 条</span>
                          <strong>{fmt(cnt)}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="feature-card">
                  <h4>线长度分布曲线</h4>
                  <svg viewBox="0 0 320 200" className="scatter-svg" role="img" aria-label="线长度分布曲线">
                    <line x1="36" y1="170" x2="300" y2="170" stroke="rgba(148,163,184,0.35)" />
                    <line x1="36" y1="20" x2="36" y2="170" stroke="rgba(148,163,184,0.35)" />
                    {laneLengthHist.length > 0 && (
                      <polyline
                        fill="none"
                        stroke="#22d3ee"
                        strokeWidth="2"
                        points={laneLengthHist.map((b, i) => {
                          const x = 36 + (i / Math.max(1, laneLengthHist.length - 1)) * 264;
                          const y = 170 - (b.count / laneLengthMax) * 140;
                          return `${x},${y}`;
                        }).join(" ")}
                      />
                    )}
                    <text x="300" y="188" textAnchor="end" className="scatter-axis">长度区间</text>
                    <text x="8" y="20" className="scatter-axis">频次</text>
                  </svg>
                </div>
                <div className="feature-card">
                  <h4>曲率分布曲线</h4>
                  <svg viewBox="0 0 320 200" className="scatter-svg" role="img" aria-label="曲率分布曲线">
                    <line x1="36" y1="170" x2="300" y2="170" stroke="rgba(148,163,184,0.35)" />
                    <line x1="36" y1="20" x2="36" y2="170" stroke="rgba(148,163,184,0.35)" />
                    {laneCurvHist.length > 0 && (
                      <polyline
                        fill="none"
                        stroke="#a78bfa"
                        strokeWidth="2"
                        points={laneCurvHist.map((b, i) => {
                          const x = 36 + (i / Math.max(1, laneCurvHist.length - 1)) * 264;
                          const y = 170 - (b.count / laneCurvMax) * 140;
                          return `${x},${y}`;
                        }).join(" ")}
                      />
                    )}
                    <text x="300" y="188" textAnchor="end" className="scatter-axis">曲率区间</text>
                    <text x="8" y="20" className="scatter-axis">频次</text>
                  </svg>
                </div>
              </div>
            </>
          ) : (
            <p className="empty-state">车道线数据可视化暂未开放（训练/评估不受影响）。</p>
          )}
          <div className="crud-actions" style={{ marginTop: 14 }}>
            <button type="button" className="btn btn-ghost" onClick={() => load(true)} disabled={loading}>
              {loading ? "刷新中..." : "刷新数据"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setSelectedVersion(versions[0]?.name || "")}>重置视图</button>
          </div>
        </div>
      </div>
    </>
  );
}
