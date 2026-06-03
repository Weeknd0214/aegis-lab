#!/usr/bin/env bash
# Build HSAP standalone frontend from platform/web/ and deploy to platform/ui-hsap/dist/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "[web] Installing dependencies..."
cd "$ROOT/platform/web"
npm ci --silent

echo "[web] Building..."
npm run build

DIST="$ROOT/platform/ui-hsap/dist"

# Copy Label Studio Editor legacy build for /annotate/
EDITOR_SRC="${LABEL_STUDIO_DIST:-${ROOT}/../workspace/BK2/label-studio/web/dist/apps/hsap-platform}"
if [ -d "$EDITOR_SRC" ]; then
  mkdir -p "$DIST/annotate"
  cp -r "$EDITOR_SRC"/* "$DIST/annotate/"

  # Copy webpack chunks to dist root (webpack publicPath="/" loads them from root)
  for f in editor.js 849.js 710.js 408.js 63.js main.css editor.css; do
    [ -f "$DIST/annotate/$f" ] && cp "$DIST/annotate/$f" "$DIST/$f"
  done

  # Custom annotate index.html
  cat > "$DIST/annotate/index.html" << 'HTMLEOF'
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>HSAP · 标注编辑器</title>
    <base href="/" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="stylesheet" href="/annotate/main.css" />
    <link rel="stylesheet" href="/annotate/editor.css" />
  </head>
  <body>
    <div id="root"></div>
    <script>
      (function() {
        var p = new URLSearchParams(location.search);
        var cid = p.get('c');
        if (cid) {
          history.replaceState(null, '', '/labeling/campaigns/' + cid + '/annotate');
        }
      })();
    </script>
    <script src="/annotate/main.js"></script>
  </body>
</html>
HTMLEOF
  echo "[web] Annotate editor (legacy LS) deployed from $EDITOR_SRC"
else
  echo "[web] ⚠ annotate editor source not found at $EDITOR_SRC"
fi

echo "[web] Build complete → $DIST"
echo "[web] Files:"
ls -lh "$DIST/index.html" "$DIST/assets/" | head -8
