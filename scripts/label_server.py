#!/usr/bin/env python3
"""Tiny local web labeler. Browser-based, single-keypress.

Usage:
    python scripts/label_server.py [base-dir]
    # then open http://127.0.0.1:8088/

Default base-dir: scripts/outputs/labels_staging

Keys (in the browser tab):
    F / J  → face
    D / K  → not_face
    S / L  → skip (decide later — moves to skipped/)
    A / ←  → undo last
"""
from __future__ import annotations

import argparse
import http.server
import json
import random
import shutil
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse


class State:
    def __init__(self, base: Path, shuffle: bool = True, seed: int = 42) -> None:
        self.base = base.resolve()
        self.unlabeled = self.base / "unlabeled"
        self.face = self.base / "face"
        self.not_face = self.base / "not_face"
        self.skipped = self.base / "skipped"
        for d in (self.face, self.not_face, self.skipped):
            d.mkdir(parents=True, exist_ok=True)
        if not self.unlabeled.exists():
            raise SystemExit(f"ERROR: {self.unlabeled} does not exist")
        items = [p for p in self.unlabeled.iterdir() if not p.name.startswith(".")]
        if shuffle:
            # Deterministic shuffle so server restarts give the same order.
            random.Random(seed).shuffle(items)
        else:
            items.sort()
        self.todo: list[Path] = items
        self.history: list[tuple[Path, Path]] = []
        self.lock = threading.Lock()

    def next_image(self) -> Path | None:
        return self.todo[0] if self.todo else None

    def _count_dir(self, d: Path) -> int:
        return sum(1 for p in d.iterdir() if not p.name.startswith("."))

    def status(self) -> dict:
        nxt = self.next_image()
        return {
            "done": len(self.history),
            "remaining": len(self.todo),
            "face": self._count_dir(self.face),
            "not_face": self._count_dir(self.not_face),
            "skipped": self._count_dir(self.skipped),
            "next_name": nxt.name if nxt else None,
        }

    def label(self, action: str) -> dict:
        with self.lock:
            if not self.todo:
                return self.status()
            dst_dir = {
                "face": self.face,
                "not_face": self.not_face,
                "skip": self.skipped,
            }.get(action)
            if dst_dir is None:
                return self.status()
            src = self.todo.pop(0)
            dst = dst_dir / src.name
            if dst.exists():
                dst.unlink()
            shutil.move(str(src), str(dst))
            self.history.append((src, dst))
            return self.status()

    def undo(self) -> dict:
        with self.lock:
            if not self.history:
                return self.status()
            orig, current = self.history.pop()
            if current.exists():
                if orig.exists():
                    orig.unlink()
                shutil.move(str(current), str(orig))
            self.todo.insert(0, orig)
            return self.status()


_state: State  # set in main


HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Watch Face Labeler</title>
<style>
  html, body { margin: 0; padding: 0; background: #1c1c1e; color: #ffffff;
               font-family: -apple-system, "Helvetica Neue", Helvetica, sans-serif; }
  body { display: flex; flex-direction: column; height: 100vh; }
  #status { padding: 10px 16px; font-size: 14px; line-height: 1.3;
            background: #2c2c2e; border-bottom: 1px solid #3a3a3c; }
  #status .name { color: #8e8e93; }
  #stage { flex: 1; display: flex; justify-content: center; align-items: center;
           padding: 16px; min-height: 0; }
  #img { max-width: 100%; max-height: 100%; object-fit: contain;
         box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5); border-radius: 4px;
         transition: opacity 80ms; }
  #img.busy { opacity: 0.5; }
  #done { font-size: 36px; padding: 80px; display: none; }
  #help { padding: 12px 16px; font-size: 13px; background: #2c2c2e;
          border-top: 1px solid #3a3a3c; color: #c7c7cc; }
  kbd { background: #3a3a3c; padding: 2px 8px; border-radius: 4px;
        font-family: ui-monospace, Menlo, monospace; font-size: 12px;
        margin: 0 2px; border: 1px solid #48484a; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 12px;
          margin-right: 8px; font-size: 12px; }
  .pill.face { background: #34c759; color: #000; }
  .pill.notface { background: #ff3b30; color: #fff; }
  .pill.skip { background: #ff9500; color: #000; }
  .pill.left { background: #5e5ce6; color: #fff; }
</style>
</head>
<body>
<div id="status"><span id="counts">loading...</span><div class="name" id="name"></div></div>
<div id="stage">
  <img id="img" src="" alt="" style="display:none;">
  <div id="done">DONE — close this tab.</div>
</div>
<div id="help">
  <kbd>F</kbd>/<kbd>J</kbd> face &nbsp;
  <kbd>D</kbd>/<kbd>K</kbd> not_face &nbsp;
  <kbd>S</kbd>/<kbd>L</kbd> skip &nbsp;
  <kbd>A</kbd>/<kbd>←</kbd> undo
</div>
<script>
let busy = false;

function paintStatus(d) {
  const total = d.done + d.remaining;
  const counts = document.getElementById("counts");
  counts.innerHTML =
    '<span class="pill left">' + d.done + ' / ' + total + '</span>' +
    '<span class="pill face">face ' + d.face + '</span>' +
    '<span class="pill notface">not_face ' + d.not_face + '</span>' +
    '<span class="pill skip">skip ' + d.skipped + '</span>';
  const name = document.getElementById("name");
  name.textContent = d.next_name || "";
  const img = document.getElementById("img");
  const done = document.getElementById("done");
  if (d.next_name) {
    img.src = "/image/" + encodeURIComponent(d.next_name) + "?_=" + Date.now();
    img.style.display = "";
    done.style.display = "none";
  } else {
    img.style.display = "none";
    done.style.display = "";
  }
}

async function fetchJSON(method, path, body) {
  const opts = { method };
  if (body) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(path, opts);
  return r.json();
}

async function init() {
  const d = await fetchJSON("GET", "/api/status");
  paintStatus(d);
}

async function act(action) {
  if (busy) return;
  busy = true;
  document.getElementById("img").classList.add("busy");
  try {
    const d = await fetchJSON("POST", "/api/label", { action });
    paintStatus(d);
  } finally {
    busy = false;
    document.getElementById("img").classList.remove("busy");
  }
}

async function undo() {
  if (busy) return;
  busy = true;
  try {
    const d = await fetchJSON("POST", "/api/undo", {});
    paintStatus(d);
  } finally { busy = false; }
}

document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === "f" || k === "j") { e.preventDefault(); act("face"); }
  else if (k === "d" || k === "k") { e.preventDefault(); act("not_face"); }
  else if (k === "s" || k === "l") { e.preventDefault(); act("skip"); }
  else if (k === "a" || k === "arrowleft") { e.preventDefault(); undo(); }
});

init();
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — http.server signature
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send_html(HTML)
        elif u.path == "/api/status":
            self._send_json(_state.status())
        elif u.path.startswith("/image/"):
            name = unquote(u.path[len("/image/"):])
            self._send_image(name)
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else "{}"
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        if u.path == "/api/label":
            self._send_json(_state.label(str(data.get("action", ""))))
        elif u.path == "/api/undo":
            self._send_json(_state.undo())
        else:
            self.send_error(404)

    def _send_image(self, name: str) -> None:
        path = _state.unlabeled / name
        if not path.exists():
            # Fallback: image may already have been moved — look in face/not_face/skipped
            for d in (_state.face, _state.not_face, _state.skipped):
                candidate = d / name
                if candidate.exists():
                    path = candidate
                    break
            else:
                self.send_error(404)
                return
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self.send_error(404)
            return
        suffix = path.suffix.lower()
        ctype = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str) -> None:
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:  # quiet
        return


def main() -> None:
    global _state
    ap = argparse.ArgumentParser()
    ap.add_argument("base_dir", type=Path, nargs="?",
                    default=Path("scripts/outputs/labels_staging"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    args = ap.parse_args()
    _state = State(args.base_dir)
    print(f"serving {args.base_dir.resolve()}")
    print(f"todo:      {len(_state.todo)} images")
    print(f"open:      http://{args.host}:{args.port}/")
    print(f"           press Ctrl-C to stop")
    server = http.server.HTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        s = _state.status()
        print(
            f"stopping. face={s['face']}  not_face={s['not_face']}  "
            f"skipped={s['skipped']}  remaining={s['remaining']}"
        )
        server.server_close()


if __name__ == "__main__":
    main()
