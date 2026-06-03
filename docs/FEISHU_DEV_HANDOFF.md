# 飞书多维表格 → HSAP 开发交接单

运维/协调员填好后交给开发写入 `HSAP/manifests/feishu.env`（勿提交含密钥的 feishu.env 到 git）。

## 从 URL 截取（最快）

在电脑浏览器打开 **「HSAP数据批次台账」** 多维表格，看地址栏，形态类似：

```text
https://xxx.feishu.cn/base/Bascnxxxxxxxxxxxxxxxx?table=tblxxxxxxxxxxxx&view=vewxxxxxxxx
                              └─ APP_TOKEN ─┘              └─ TABLE_ID ─┘
```

- **APP_TOKEN** → 填 `FEISHU_BITABLE_APP_TOKEN`（`/base/` 后面、`?` 前面整段，常以大写 `Basc` 开头）  
- **TABLE_ID** → 填 `FEISHU_BITABLE_TABLE_ID`（`table=` 后面、`&` 前面，以 `tbl` 开头）

**表只在知识库（wiki）里、没有 `/base/` 链接时：**

- **WIKI 节点** → 填 `FEISHU_BITABLE_WIKI_NODE_TOKEN`（`/wiki/` 后面、`?` 前面，如 `SFvfwCqskiWM0Jk0VfPcdtkun9c`）  
- `FEISHU_BITABLE_APP_TOKEN` 留空；HSAP 会用 wiki API 解析出真正的 Basc `obj_token`  
- 开放平台须开通 **wiki:node:read**（或 wiki:wiki:readonly）+ **bitable:app**，并给表格 **企业应用可管理**

## 必填

| 变量 | 值 | 获取方式 |
|------|-----|----------|
| `FEISHU_BITABLE_APP_TOKEN` | | 浏览器打开台账，地址栏 `/base/` 与 `?table=` 之间整段（见下文「从 URL 截取」） |
| `FEISHU_BITABLE_TABLE_ID` | | 地址栏 `table=` 后、`&` 前，形如 `tblXXXXXXXX`；或配好 APP_TOKEN 后跑 `feishu_bitable_verify.sh` 列出 |

## 已有（登录应用）

| 变量 | 值 |
|------|-----|
| `FEISHU_APP_ID` | |
| `FEISHU_APP_SECRET` | |

## 建议

| 变量 | 值 |
|------|-----|
| `AS_FRONTEND_URL` | 内网 HSAP 根 URL，如 `http://192.168.x.x:8787` |
| `FEISHU_BITABLE_SYNC_ENABLED` | `1` |
| `FEISHU_BITABLE_SYNC_INTERVAL_SEC` | `120` |
| `FEISHU_BITABLE_AUTO_INGEST` | `0`（内网 Phase A 保持 0） |

## 可选

| 变量 | 值 |
|------|-----|
| `FEISHU_LABELING_CHAT_ID` | 协作群 chat_id（群机器人通知） |

## 表格列名

默认与 [FEISHU_BITABLE_OPS.md](./FEISHU_BITABLE_OPS.md) 中文列名一致；若飞书表改了列名，在 `feishu.env` 用 `FEISHU_BITABLE_FIELD_*` 覆盖（见 `feishu.env.example`）。

## 验证

```bash
cd HSAP
# 确保 manifests/feishu.env 已填 BITABLE_*
bash scripts/feishu_bitable_verify.sh
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/v1/integrations/feishu/bitable/status
```
