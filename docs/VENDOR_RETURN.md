# 第三方标注回传包

## ZIP 结构

```text
vendor_return.zip
├── manifest.json      # 可选：format, task, batch
├── images/            # jpg/png
└── labels/            # yolo txt 或 json
```

## API

```bash
curl -X POST "http://127.0.0.1:8787/api/v1/labeling/campaigns/{campaign_id}/import-vendor" \
  -H "Authorization: Bearer <token>" \
  -F "file=@vendor_return.zip"
```

权限：`write:labeling_vendor`（工程师、vendor_labeler 角色）。

导入后自动写入 `LabelingCampaignAccess`（vendor_labeler），图片落批次 `images/`，标签落 `labels/`。

## 前端

标注任务列表 → **导入回传**；或侧栏 **导出与入库**。
