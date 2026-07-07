#!/usr/bin/env python3
"""
Firecrawl → cartella di file Markdown.

Uso:
    python3 crawl_to_md.py https://example.com
    python3 crawl_to_md.py https://example.com --limit 100 --out ./scrapes

Cosa fa:
  1. avvia un crawl su Firecrawl (default http://localhost:3002) e mostra l'avanzamento live;
  2. crea una cartella col nome del sito (es. example.com/);
  3. scrive un file .md per ogni pagina, rispecchiando l'alberatura degli URL;
  4. genera MAP.md con la struttura ad albero e i link ai file.
"""
import sys, os, re, json, time, argparse, urllib.request, urllib.error
from urllib.parse import urlparse


def http(method, url, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise SystemExit(f"[HTTP {e.code}] {method} {url}\n{detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Connessione fallita a {url}: {e.reason}\n"
                         f"Firecrawl è avviato? (docker compose ps)")


def slug(s):
    s = re.sub(r"[^\w\-.]+", "-", s or "").strip("-.")
    return s or "index"


def segments_for(source_url):
    """Ritorna la lista di segmenti di percorso (l'ultimo è il nome file, senza .md)."""
    p = urlparse(source_url)
    segs = [slug(x) for x in p.path.strip("/").split("/") if x]
    if not segs:
        segs = ["index"]
    elif p.path.endswith("/"):
        segs.append("index")
    if p.query:
        segs[-1] += "-" + slug(p.query)
    return segs


def collect_pages(api, first):
    """Segue la paginazione (campo next) e ritorna tutte le pagine."""
    data = list(first.get("data") or [])
    nxt = first.get("next")
    guard = 0
    while nxt and guard < 200:
        guard += 1
        u = re.sub(r"^https?://[^/]+", api, nxt) if nxt.startswith("http") else api + nxt
        try:
            j = http("GET", u)
        except SystemExit:
            break
        data += (j.get("data") or [])
        nxt = j.get("next")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="URL del sito da scansionare")
    ap.add_argument("--limit", type=int, default=50, help="max pagine (default 50)")
    ap.add_argument("--api", default="http://localhost:3002", help="base URL API Firecrawl")
    ap.add_argument("--out", default=".", help="cartella dove creare l'output (default: qui)")
    ap.add_argument("--format", default="markdown", choices=["markdown", "html"])
    args = ap.parse_args()
    api = args.api.rstrip("/")

    # 1) avvio crawl -------------------------------------------------------
    print(f"▶  Avvio crawl di {args.url} (max {args.limit} pagine)…")
    start = http("POST", api + "/v1/crawl", {
        "url": args.url,
        "limit": args.limit,
        "scrapeOptions": {"formats": [args.format]},
    })
    cid = start.get("id")
    if not cid:
        raise SystemExit(f"Risposta inattesa dall'avvio: {start}")
    print(f"   crawl id: {cid}\n")

    # 2) polling live ------------------------------------------------------
    t0 = time.time()
    while True:
        st = http("GET", f"{api}/v1/crawl/{cid}")
        status = st.get("status", "scraping")
        done, total = st.get("completed", 0), st.get("total", 0)
        elapsed = int(time.time() - t0)
        bar_n = int((done / total) * 24) if total else 0
        bar = "█" * bar_n + "·" * (24 - bar_n)
        sys.stdout.write(f"\r   [{bar}] {done}/{total}  {status}  {elapsed}s   ")
        sys.stdout.flush()
        if status in ("completed", "failed"):
            print()
            break
        time.sleep(2)

    if status == "failed":
        raise SystemExit("\n❌ Crawl fallito. Controlla i log: docker compose logs -f api")

    pages = collect_pages(api, st)
    print(f"\n✓  Crawl completato: {len(pages)} pagine in {int(time.time()-t0)}s")

    # 3) scrittura file ----------------------------------------------------
    host = urlparse(args.url).hostname or "site"
    root = os.path.abspath(os.path.join(args.out, host))
    os.makedirs(root, exist_ok=True)

    used = set()
    tree = {}
    written = 0
    for pg in pages:
        meta = pg.get("metadata") or {}
        src = meta.get("sourceURL") or meta.get("url") or args.url
        title = (meta.get("title") or meta.get("ogTitle") or src).strip()
        body = pg.get("markdown") or pg.get("html") or ""

        segs = segments_for(src)
        rel = os.path.join(*segs) + ".md"
        # evita collisioni di nome
        base, n = rel, 2
        while rel in used:
            rel = base[:-3] + f"-{n}.md"
            n += 1
        used.add(rel)

        fpath = os.path.join(root, rel)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        front = f"---\ntitle: {title!r}\nsource: {src}\n---\n\n"
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(front + body)
        written += 1

        # inserisci nell'albero per la MAP
        node = tree
        for s in segs[:-1]:
            node = node.setdefault(s, {})
        node.setdefault("__files__", []).append((rel.replace(os.sep, "/"), title))

    # 4) MAP.md ------------------------------------------------------------
    def render(node, depth=0):
        lines, indent = [], "  " * depth
        for name in sorted(k for k in node if k != "__files__"):
            lines.append(f"{indent}- **{name}/**")
            lines += render(node[name], depth + 1)
        for rel, title in sorted(node.get("__files__", [])):
            lines.append(f"{indent}- [{title}](<{rel}>)")
        return lines

    map_md = (f"# Mappa di {host}\n\n"
              f"Sorgente: {args.url}  \n"
              f"Pagine: {written} · generato il {time.strftime('%Y-%m-%d %H:%M')}\n\n"
              + "\n".join(render(tree)) + "\n")
    with open(os.path.join(root, "MAP.md"), "w", encoding="utf-8") as f:
        f.write(map_md)

    print(f"📁  {root}")
    print(f"    {written} file .md + MAP.md")


if __name__ == "__main__":
    main()
