import React, { useEffect, useState } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";

export const VehiclesPage: React.FC = () => {
  const [vehicles, setVehicles] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [plateNo, setPlateNo] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [name, setName] = useState("");
  const [team, setTeam] = useState("");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await hsapApi.fleetVehicles();
      setVehicles((res.items || []) as Record<string, unknown>[]);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    if (!plateNo || !deviceId) return;
    try {
      await hsapApi.fleetCreateVehicle({ plate_no: plateNo, tbox_device_id: deviceId, name: name || undefined, team: team || undefined });
      setShowForm(false);
      setPlateNo(""); setDeviceId(""); setName(""); setTeam("");
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定删除此车辆？")) return;
    try {
      await hsapApi.fleetDeleteVehicle(id);
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>车辆管理</h1>
          <p>管理采集车队车辆信息</p>
        </div>
        <Button variant="primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? "取消" : "添加车辆"}
        </Button>
      </div>

      {showForm && (
        <div className="card mb-4 max-w-lg">
          <div className="form-group">
            <label className="form-label">车牌号</label>
            <input className="form-input" value={plateNo} onChange={(e) => setPlateNo(e.target.value)} placeholder="如 湘A·采集01" />
          </div>
          <div className="form-group">
            <label className="form-label">T-Box 设备 ID</label>
            <input className="form-input" value={deviceId} onChange={(e) => setDeviceId(e.target.value)} placeholder="如 TBOX-001" />
          </div>
          <div className="form-group">
            <label className="form-label">车辆名称（可选）</label>
            <input className="form-input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">所属车队（可选）</label>
            <input className="form-input" value={team} onChange={(e) => setTeam(e.target.value)} />
          </div>
          <Button variant="primary" onClick={handleCreate}>创建车辆</Button>
        </div>
      )}

      <PageQueryState loading={loading} error={error} empty={vehicles.length === 0} emptyMessage="暂无车辆">
        <div className="card">
          <table className="table-auto">
            <thead>
              <tr>
                <th>ID</th>
                <th>车牌号</th>
                <th>T-Box</th>
                <th>名称</th>
                <th>车队</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {vehicles.map((v) => (
                <tr key={v.id as number}>
                  <td>{String(v.id)}</td>
                  <td className="font-medium">{v.plate_no as string}</td>
                  <td className="font-mono text-xs">{v.tbox_device_id as string}</td>
                  <td>{(v.name as string) || "—"}</td>
                  <td>{(v.team as string) || "—"}</td>
                  <td><Badge variant={v.status === "active" ? "success" : "default"}>{v.status as string}</Badge></td>
                  <td>
                    <Button size="small" variant="danger" onClick={() => handleDelete(v.id as number)}>删除</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PageQueryState>
    </div>
  );
};
