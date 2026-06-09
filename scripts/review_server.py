#!/usr/bin/env python3
"""Click-to-ignore review tool for the cropped pretrain corpus.

Serves a per-class thumbnail grid (the cropped 015 training images). Click any
image to toggle "ignore"; toggles persist to <root>/_exclusions.json. The dataset
assembler reads that file and drops excluded images. Reversible — click again to keep.

    python scripts/review_server.py --root scripts/outputs/_cropped [--port 8090]
    open http://127.0.0.1:8090/
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ROOT = Path(".")
EXCL: set[str] = set()
EXCL_FILE = Path("_exclusions.json")


def save() -> None:
    EXCL_FILE.write_text(json.dumps(sorted(EXCL), indent=0))


def classes() -> list[tuple[str, int]]:
    out = []
    for d in sorted(ROOT.iterdir()):
        if d.is_dir():
            out.append((d.name, sum(1 for p in d.iterdir() if p.suffix.lower() in IMG_EXT)))
    return out


def page(html: str) -> bytes:
    return ("<!doctype html><meta charset=utf-8><style>"
            "body{background:#0f172a;color:#e2e8f0;font-family:system-ui;margin:0;padding:16px}"
            "a{color:#7dd3fc}.grid{display:flex;flex-wrap:wrap;gap:6px}"
            ".c{position:relative;cursor:pointer;width:150px;height:150px}"
            ".c img{width:150px;height:150px;object-fit:cover;border:2px solid #334155}"
            ".c.x img{opacity:.32;border-color:#ef4444}"
            ".c.x::after{content:'IGNORED';position:absolute;top:60px;left:34px;color:#ef4444;font-weight:700}"
            "h2{position:sticky;top:0;background:#0f172a;padding:8px 0}</style>" + html).encode()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, body: bytes, ctype="text/html"):
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            rows = "".join(f"<li><a href='/cls?k={quote(c)}'>{c}</a> — {n} imgs"
                           f"{' · <b style=color:#ef4444>'+str(sum(1 for e in EXCL if e.startswith(c+'/')))+' ignored</b>' if any(e.startswith(c+'/') for e in EXCL) else ''}</li>"
                           for c, n in classes())
            self._send(page(f"<h1>Corpus review — click images to ignore</h1>"
                            f"<p>{len(EXCL)} ignored total. Exclusions → {EXCL_FILE}</p><ul>{rows}</ul>"))
        elif u.path == "/cls":
            k = parse_qs(u.query).get("k", [""])[0]
            d = ROOT / k
            if not d.is_dir():
                self._send(page("<p>no such class</p>")); return
            cells = []
            for p in sorted(d.iterdir()):
                if p.suffix.lower() not in IMG_EXT:
                    continue
                rel = f"{k}/{p.name}"
                cls = "c x" if rel in EXCL else "c"
                cells.append(f"<div class='{cls}' data-r=\"{rel}\" onclick=\"t(this)\">"
                             f"<img loading=lazy src='/img?p={quote(rel)}'></div>")
            names = [c for c, _ in classes()]
            idx = names.index(k) if k in names else -1
            prevk = names[idx - 1] if idx > 0 else None
            nextk = names[idx + 1] if 0 <= idx < len(names) - 1 else None
            prev_lnk = f"<a href='/cls?k={quote(prevk)}'>← prev</a>" if prevk else "<span style=color:#475569>← prev</span>"
            next_lnk = f"<a href='/cls?k={quote(nextk)}'>next →</a>" if nextk else "<span style=color:#475569>next →</span>"
            nexturl = f"/cls?k={quote(nextk)}" if nextk else ""
            prevurl = f"/cls?k={quote(prevk)}" if prevk else ""
            js = ("<script>function t(e){fetch('/toggle',{method:'POST',"
                  "headers:{'Content-Type':'application/json'},body:JSON.stringify({r:e.dataset.r})})"
                  ".then(r=>r.json()).then(d=>{e.className=d.excluded?'c x':'c'})}"
                  f"document.addEventListener('keydown',ev=>{{"
                  f"if(ev.key==='ArrowRight'&&'{nexturl}')location='{nexturl}';"
                  f"if(ev.key==='ArrowLeft'&&'{prevurl}')location='{prevurl}';}});</script>")
            self._send(page(f"<h2>{prev_lnk} &nbsp;|&nbsp; <a href='/'>all</a> &nbsp;|&nbsp; {next_lnk}"
                            f" &nbsp;&nbsp; <b>{k}</b> <small>({idx+1}/{len(names)}) — click to ignore, ←/→ to move</small></h2>"
                            f"<div class=grid>{''.join(cells)}</div>{js}"))
        elif u.path == "/img":
            rel = unquote(parse_qs(u.query).get("p", [""])[0])
            fp = (ROOT / rel).resolve()
            if ROOT.resolve() not in fp.parents or not fp.is_file():
                self.send_response(404); self.end_headers(); return
            ct = "image/jpeg" if fp.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            self._send(fp.read_bytes(), ct)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path == "/toggle":
            n = int(self.headers.get("Content-Length", 0))
            rel = json.loads(self.rfile.read(n))["r"]
            if rel in EXCL:
                EXCL.discard(rel); ex = False
            else:
                EXCL.add(rel); ex = True
            save()
            self._send(json.dumps({"excluded": ex}).encode(), "application/json")
        else:
            self.send_response(404); self.end_headers()


def main() -> None:
    global ROOT, EXCL_FILE, EXCL
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("scripts/outputs/_cropped"))
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()
    ROOT = args.root.resolve()
    EXCL_FILE = ROOT / "_exclusions.json"
    if EXCL_FILE.exists():
        EXCL = set(json.loads(EXCL_FILE.read_text()))
    print(f"serving {ROOT} on http://127.0.0.1:{args.port}/  ({len(EXCL)} already excluded)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), H).serve_forever()


if __name__ == "__main__":
    main()
