"""飞书多维表格 API（tenant_access_token）。"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from as_platform.auth.feishu import _get_tenant_access_token
from as_platform.config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_BITABLE_APP_TOKEN,
    FEISHU_BITABLE_FIELDS,
    FEISHU_BITABLE_TABLE_ID,
    FEISHU_BITABLE_WIKI_NODE_TOKEN,
)

BITABLE_BASE = "https://open.feishu.cn/open-apis/bitable/v1"
WIKI_GET_NODE = "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node"

_field_cache: dict[str, Any] | None = None
_field_cache_at: float = 0.0
_FIELD_CACHE_TTL = 300.0
_resolved_app_token: str | None = None


def _looks_like_bitable_app_token(token: str) -> bool:
    t = token.strip()
    return t.startswith(("Basc", "basc", "app"))


def _resolve_app_token_from_wiki(node_token: str) -> str:
    with _client() as client:
        access = _token(client)
        resp = client.get(
            WIKI_GET_NODE,
            headers={"Authorization": f"Bearer {access}"},
            params={"token": node_token},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(data.get("msg") or "wiki get_node failed")
        node = data.get("data", {}).get("node") or {}
        obj = (node.get("obj_token") or "").strip()
        if not obj:
            raise RuntimeError(
                "wiki 节点未返回 obj_token；请在开放平台开通 wiki:node:read，或改用 /base/Basc... 填 FEISHU_BITABLE_APP_TOKEN"
            )
        return obj


def _effective_app_token() -> str:
    global _resolved_app_token
    if FEISHU_BITABLE_APP_TOKEN and _looks_like_bitable_app_token(FEISHU_BITABLE_APP_TOKEN):
        return FEISHU_BITABLE_APP_TOKEN
    node = FEISHU_BITABLE_WIKI_NODE_TOKEN or FEISHU_BITABLE_APP_TOKEN
    if not node:
        return FEISHU_BITABLE_APP_TOKEN
    if _resolved_app_token is None:
        _resolved_app_token = _resolve_app_token_from_wiki(node)
    return _resolved_app_token


def is_bitable_configured() -> bool:
    has_app = bool(FEISHU_BITABLE_APP_TOKEN or FEISHU_BITABLE_WIKI_NODE_TOKEN)
    return bool(FEISHU_APP_ID and FEISHU_APP_SECRET and has_app and FEISHU_BITABLE_TABLE_ID)


def _client() -> httpx.Client:
    return httpx.Client(timeout=60.0)


def _token(client: httpx.Client) -> str:
    return _get_tenant_access_token(client)


def _app_table() -> tuple[str, str]:
    return _effective_app_token(), FEISHU_BITABLE_TABLE_ID


def list_tables() -> list[dict[str, Any]]:
    """列出 Base 下数据表（运维查 table_id）。"""
    if not is_bitable_configured():
        return []
    app_token, _ = _app_table()
    with _client() as client:
        token = _token(client)
        resp = client.get(
            f"{BITABLE_BASE}/apps/{app_token}/tables",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_size": 100},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(data.get("msg") or "list tables failed")
        return data.get("data", {}).get("items") or []


def _load_field_meta(force: bool = False) -> dict[str, dict[str, Any]]:
    global _field_cache, _field_cache_at
    now = time.time()
    if not force and _field_cache and now - _field_cache_at < _FIELD_CACHE_TTL:
        return _field_cache

    app_token, table_id = _app_table()
    by_name: dict[str, dict[str, Any]] = {}
    with _client() as client:
        token = _token(client)
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            resp = client.get(
                f"{BITABLE_BASE}/apps/{app_token}/tables/{table_id}/fields",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(data.get("msg") or "list fields failed")
            for item in data.get("data", {}).get("items") or []:
                name = item.get("field_name") or item.get("name")
                if name:
                    by_name[str(name)] = item
            page_token = data.get("data", {}).get("page_token")
            if not page_token:
                break
    _field_cache = by_name
    _field_cache_at = now
    return by_name


def _option_id_for_text(field_meta: dict[str, Any], text: str) -> str | None:
    ui = field_meta.get("ui_type") or field_meta.get("type")
    if ui not in (3, "SingleSelect", "single_select"):
        return None
    prop = field_meta.get("property") or {}
    for opt in prop.get("options") or []:
        if opt.get("name") == text:
            return opt.get("id")
    return None


def _encode_value(field_meta: dict[str, Any], value: Any) -> Any:
    if value is None:
        return None
    ui = field_meta.get("ui_type") or field_meta.get("type")
    if ui in (1, "Text", "text", "Url", "url"):
        if isinstance(value, dict) and "link" in value:
            return value
        return str(value)
    if ui in (2, "Number", "number"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if ui in (3, "SingleSelect", "single_select"):
        oid = _option_id_for_text(field_meta, str(value))
        return oid if oid else str(value)
    if ui in (5, "DateTime", "datetime", "CreatedTime", "ModifiedTime"):
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    if ui in (15, "Url", "url") and isinstance(value, dict):
        return {"text": value.get("text") or value.get("link"), "link": value.get("link")}
    return str(value)


def _flatten_cell(cell: Any) -> str:
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell.strip()
    if isinstance(cell, (int, float)):
        return str(cell)
    if isinstance(cell, list):
        parts = [_flatten_cell(x) for x in cell]
        return ",".join(p for p in parts if p)
    if isinstance(cell, dict):
        if "text" in cell:
            return str(cell.get("text") or "").strip()
        if "name" in cell:
            return str(cell.get("name") or "").strip()
        if "value" in cell:
            return _flatten_cell(cell.get("value"))
    return str(cell).strip()


def list_all_records() -> list[dict[str, Any]]:
    """返回 {record_id, fields_raw, flat}。"""
    if not is_bitable_configured():
        return []
    app_token, table_id = _app_table()
    meta = _load_field_meta()
    id_by_label = {label: meta[name]["field_id"] for name, m in meta.items() if (label := FEISHU_BITABLE_FIELDS.get(name)) and name in meta for name in FEISHU_BITABLE_FIELDS}
    # rebuild: map logical key -> field_name
    name_for_key = {k: v for k, v in FEISHU_BITABLE_FIELDS.items()}

    rows: list[dict[str, Any]] = []
    with _client() as client:
        token = _token(client)
        page_token: str | None = None
        while True:
            body: dict[str, Any] = {"page_size": 500}
            if page_token:
                body["page_token"] = page_token
            resp = client.post(
                f"{BITABLE_BASE}/apps/{app_token}/tables/{table_id}/records/search",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(data.get("msg") or "search records failed")
            for item in data.get("data", {}).get("items") or []:
                record_id = item.get("record_id") or item.get("id")
                fields = item.get("fields") or {}
                flat: dict[str, str] = {}
                for key, col_name in name_for_key.items():
                    raw = fields.get(col_name)
                    if raw is None:
                        fid = meta.get(col_name, {}).get("field_id")
                        if fid:
                            raw = fields.get(fid)
                    flat[key] = _flatten_cell(raw)
                rows.append({"record_id": record_id, "fields": fields, "flat": flat})
            page_token = data.get("data", {}).get("page_token")
            if not page_token:
                break
    return rows


def update_record(record_id: str, values: dict[str, Any]) -> None:
    """values: 逻辑键 delivery_id / status / inbox_path ..."""
    if not record_id or not is_bitable_configured():
        return
    meta = _load_field_meta()
    payload_fields: dict[str, Any] = {}
    for key, val in values.items():
        if val is None:
            continue
        col = FEISHU_BITABLE_FIELDS.get(key)
        if not col or col not in meta:
            continue
        encoded = _encode_value(meta[col], val)
        if encoded is not None:
            payload_fields[col] = encoded

    if not payload_fields:
        return

    app_token, table_id = _app_table()
    with _client() as client:
        token = _token(client)
        resp = client.put(
            f"{BITABLE_BASE}/apps/{app_token}/tables/{table_id}/records/{record_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": payload_fields},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(data.get("msg") or "update record failed")


def connectivity_check() -> dict[str, Any]:
    if not is_bitable_configured():
        return {"configured": False, "ok": False, "message": "缺少 FEISHU_BITABLE_APP_TOKEN 或 TABLE_ID"}
    try:
        tables = list_tables()
        meta = _load_field_meta(force=True)
        missing = [v for k, v in FEISHU_BITABLE_FIELDS.items() if k not in ("record_id",) and v not in meta]
        return {
            "configured": True,
            "ok": len(missing) == 0,
            "tables": [{"table_id": t.get("table_id"), "name": t.get("name")} for t in tables],
            "field_count": len(meta),
            "missing_columns": missing,
        }
    except Exception as e:
        msg = str(e)
        hint = ""
        if "1254302" in msg or "no permissions" in msg.lower():
            hint = (
                "飞书返回 1254302：应用「主动安全算法平台」对该表无读写权。"
                "知识库内嵌表常无法加企业应用，请复制为独立多维表格(/base/Basc...)并加应用协作者，"
                "或见 docs/FEISHU_BITABLE_OPS.md §8；联调可设 FEISHU_BITABLE_SYNC_ENABLED=0。"
            )
        return {"configured": True, "ok": False, "message": msg, "hint": hint or None}
