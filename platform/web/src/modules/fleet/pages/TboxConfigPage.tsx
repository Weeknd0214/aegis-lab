import React from "react";

export const TboxConfigPage: React.FC = () => {
  return (
    <div className="page-container">
      <div className="page-header">
        <h1>T-Box 配置</h1>
        <p>T-Box 设备上报配置说明</p>
      </div>

      <div className="card mb-4">
        <div className="card-header">上报接口</div>
        <table className="table-auto">
          <thead>
            <tr>
              <th>方法</th>
              <th>路径</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="font-mono text-xs">POST</td>
              <td className="font-mono text-xs">/api/v1/tbox/gps</td>
              <td>单点 GPS 上报</td>
            </tr>
            <tr>
              <td className="font-mono text-xs">POST</td>
              <td className="font-mono text-xs">/api/v1/tbox/gps/batch</td>
              <td>批量 GPS 上报（最多 100 点）</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card mb-4">
        <div className="card-header">认证</div>
        <p className="text-sm text-gray-600">
          T-Box 上报需要在 HTTP Header 中携带 <code className="bg-gray-100 px-1 rounded">X-Tbox-Token</code>，
          值为环境变量 <code className="bg-gray-100 px-1 rounded">AS_TBOX_INGEST_TOKEN</code> 的值（默认: <code className="bg-gray-100 px-1 rounded">hsap-demo-tbox-token</code>）。
        </p>
      </div>

      <div className="card">
        <div className="card-header">上报示例</div>
        <pre className="text-xs bg-gray-50 p-3 rounded overflow-auto">{`curl -X POST http://127.0.0.1:8787/api/v1/tbox/gps \\
  -H "Content-Type: application/json" \\
  -H "X-Tbox-Token: hsap-demo-tbox-token" \\
  -d '{
    "device_id": "TBOX-001",
    "lat": 28.2282,
    "lng": 112.9388,
    "speed_kmh": 40,
    "run_signal": "active",
    "plate_no": "湘A·采集01"
  }'`}</pre>
      </div>
    </div>
  );
};
