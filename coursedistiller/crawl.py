"""Authenticated course crawler (Playwright).

Opens a real browser, waits for you to log in to YOUR course, then crawls the
product -> categories -> posts graph using authenticated same-origin fetch()
(fast, gentle), parses each lesson to a compact record, follows in-body links to
close the branching graph, and downloads attachments. Writes JSON shards to
work/harvest_shards/. Only ever run against content you're entitled to access.
"""
import glob
import json
import os
import time
from playwright.sync_api import sync_playwright

# --- in-page parser: HTML -> {content, links, attachments, wistia, cross} -------
PARSE_JS = r"""
(args) => {
  const {html, pid, cat} = args;
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('style,script,noscript,svg').forEach(e => e.remove());
  let col = doc.querySelector('.section__body.col-lg-8') || doc.querySelector('.section__body') || doc.body;
  col.querySelectorAll('[class*="comment"],[id*="comment"],textarea,.btn--completion,[data-post-completion-toggle],.mark-as-complete')
     .forEach(e => e.remove());
  const h2t = (h) => h
    .replace(/<\s*br\s*\/?\s*>/gi, '\n').replace(/<\s*li[^>]*>/gi, '\n- ')
    .replace(/<\/(p|div|h[1-6]|li|tr|ul|ol)>/gi, '\n').replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>')
    .replace(/&#39;|&rsquo;|&apos;/gi, "'").replace(/&quot;|&ldquo;|&rdquo;/gi, '"')
    .replace(/&#?\w+;/g, ' ').replace(/[ \t]+/g, ' ').replace(/ *\n */g, '\n')
    .replace(/\n{3,}/g, '\n\n').trim();
  let panels = [...col.querySelectorAll('.panel__body')].filter(p => p.textContent.trim().length > 0);
  let content = h2t(panels.length ? panels.map(p => p.innerHTML).join('\n\n') : col.innerHTML);
  const boiler = /^(mark as complete|congratulations!.*completed|great job! keep going|next lesson|previous lesson|next category|comments\s*\d*)\s*$/i;
  content = content.split('\n').filter(l => !boiler.test(l.trim())).join('\n').replace(/\n{3,}/g, '\n\n').trim();
  const scope = panels.length ? panels : [col];
  const links = []; const seenL = new Set();
  scope.forEach(p => p.querySelectorAll('a[href]').forEach(a => {
    const h = a.href;
    if (h && !/^javascript/i.test(h) && !seenL.has(h)) {
      seenL.add(h);
      const internal = new RegExp(args.base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(h);
      links.push({t: a.textContent.trim().replace(/\s+/g, ' ').slice(0, 120), h, internal});
    }
  }));
  const atts = [...doc.querySelectorAll('a.downloads__download,a[href*="/courses/downloads/"],a[href*="kajabi-storefronts"],a[download],a[href*="amazonaws"]')]
    .map(a => ({name: a.textContent.trim().replace(/\s+/g, ' ').slice(0, 120) || a.href.split('/').pop(), url: a.href}))
    .filter((v, i, s) => s.findIndex(x => x.url === v.url) === i);
  const w = html.match(/wistia_async_([a-z0-9]+)/) || html.match(/embed\/medias\/([a-z0-9]{8,})/) || html.match(/medias\/([a-z0-9]{8,})/);
  const cross = []; const seenP = new Set();
  doc.querySelectorAll('a[href*="/posts/"]').forEach(a => {
    const m = a.getAttribute('href').match(/categories\/(\d+)\/posts\/(\d+)/);
    if (m && !seenP.has(m[2])) { seenP.add(m[2]); cross.push({pid: m[2], cat: m[1]}); }
  });
  return {pid, cat, content, links, attachments: atts, wistia: (w ? w[1] : null), cross};
}
"""

# --- fetch + parse a batch of posts entirely in-page (authenticated) ------------
HARVEST_BATCH_JS = r"""
async (args) => {
  const {items, base, product, pace} = args;
  const out = [];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  for (const it of items) {
    try {
      const r = await fetch(`/products/${product}/categories/${it.cat}/posts/${it.pid}`, {credentials: 'include'});
      const html = await r.text();
      out.push({html, pid: it.pid, cat: it.cat});
    } catch (e) { out.push({err: String(e).slice(0, 80), pid: it.pid, cat: it.cat}); }
    await sleep(pace);
  }
  return out;
}
"""

LIST_POSTS_JS = r"""
async (args) => {
  const {url} = args;
  const r = await fetch(url, {credentials: 'include'});
  const html = await r.text();
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const posts = {}; const cats = {};
  doc.querySelectorAll('a[href*="/posts/"]').forEach(a => {
    const m = a.getAttribute('href').match(/categories\/(\d+)\/posts\/(\d+)/);
    if (m) posts[m[2]] = m[1];
  });
  doc.querySelectorAll('a[href*="/categories/"]').forEach(a => {
    const m = a.getAttribute('href').match(/categories\/(\d+)/);
    if (m) cats[m[1]] = (a.textContent.trim().replace(/\s+/g, ' ').slice(0, 90)) || cats[m[1]] || '';
  });
  const authed = !/name="password"|Sign in to your account/i.test(html) && html.includes('/posts/');
  return {posts, cats, authed};
}
"""


def _is_authed(page, cfg):
    res = page.evaluate(LIST_POSTS_JS, {"url": f"/products/{cfg.site['product_slug']}"})
    return res.get("authed", False), res


def crawl(cfg, progress=lambda **k: None, login_timeout=300):
    """Full crawl. progress(phase=..., done=..., total=..., msg=...). Resumable: skips if already crawled."""
    existing = glob.glob(os.path.join(cfg.shards, "*.json"))
    if existing:
        n = sum(len(json.load(open(f))) for f in existing)
        progress(phase="crawl_done", msg=f"using cached crawl ({n} lessons)")
        return n
    prof = os.path.join(cfg.work, "browser_profile")
    os.makedirs(prof, exist_ok=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(prof, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(cfg.product_url, wait_until="domcontentloaded")

        # 1) wait for login
        progress(phase="login", msg="Log in to your course in the opened browser…")
        authed, seed = _is_authed(page, cfg)
        t0 = time.time()
        while not authed and time.time() - t0 < login_timeout:
            time.sleep(3)
            authed, seed = _is_authed(page, cfg)
        if not authed:
            ctx.close()
            raise RuntimeError("Login not detected within timeout.")

        base = cfg.site["base_url"].rstrip("/")
        product = cfg.site["product_slug"]

        # 2) map: BFS over categories to enumerate posts
        progress(phase="map", msg="Mapping course structure…")
        seen_cat, cat_title, posts = set(), dict(seed["cats"]), dict(seed["posts"])
        frontier = list(cfg.crawl["top_categories"]) or list(seed["cats"].keys())
        while frontier:
            c = frontier.pop(0)
            if c in seen_cat:
                continue
            seen_cat.add(c)
            r = page.evaluate(LIST_POSTS_JS, {"url": f"/products/{product}/categories/{c}"})
            posts.update(r["posts"])
            for cid, t in r["cats"].items():
                if cid not in cat_title or (not cat_title[cid] and t):
                    cat_title[cid] = t
                if cid not in seen_cat and cid not in frontier:
                    frontier.append(cid)
            progress(phase="map", done=len(seen_cat), total=len(seen_cat) + len(frontier), msg=f"{len(posts)} posts found")
            time.sleep(cfg.crawl["pace_ms"] / 1000)

        # 3) harvest with graph closure (follow in-body post links)
        progress(phase="harvest", msg="Harvesting lessons…")
        queue = [{"pid": p, "cat": c} for p, c in posts.items()]
        visited, records, shard_i = set(), [], 0
        while queue:
            batch = [queue.pop(0) for _ in range(min(30, len(queue)))]
            batch = [b for b in batch if b["pid"] not in visited]
            for b in batch:
                visited.add(b["pid"])
            if not batch:
                continue
            raw = page.evaluate(HARVEST_BATCH_JS, {"items": batch, "base": base, "product": product, "pace": cfg.crawl["pace_ms"]})
            for item in raw:
                if item.get("err"):
                    continue
                rec = page.evaluate(PARSE_JS, {"html": item["html"], "pid": item["pid"], "cat": item["cat"], "base": base})
                rec["catTitle"] = cat_title.get(item["cat"], "")
                for cp in rec.get("cross", []):
                    if cp["pid"] not in visited and not any(q["pid"] == cp["pid"] for q in queue):
                        queue.append(cp)
                rec.pop("cross", None)
                records.append(rec)
            if len(records) >= 120:
                _flush(cfg, records, shard_i); shard_i += 1; records = []
            progress(phase="harvest", done=len(visited), total=len(visited) + len(queue), msg=f"{len(visited)} lessons")
        if records:
            _flush(cfg, records, shard_i)

        # 4) attachments: download those referenced (authenticated /courses/downloads/)
        if cfg.attachments["download"]:
            _download_attachments(cfg, page, product, progress)

        ctx.close()
    progress(phase="crawl_done", msg=f"{len(visited)} lessons harvested")
    return len(visited)


def _flush(cfg, records, i):
    path = os.path.join(cfg.shards, f"shard_{i:03d}.json")
    json.dump(records, open(path, "w"))


def _download_attachments(cfg, page, product, progress):
    import glob, hashlib, requests
    urls = set()
    for f in glob.glob(os.path.join(cfg.shards, "*.json")):
        for r in json.load(open(f)):
            for a in r.get("attachments", []):
                urls.add(a["url"])
    urls = list(urls)
    # pull cookies from the authenticated context so requests can download files
    cookies = {c["name"]: c["value"] for c in page.context.cookies()}
    for i, u in enumerate(urls):
        try:
            resp = requests.get(u, cookies=cookies, timeout=60)
            name = u.split("?")[0].rstrip("/").split("/")[-1] or f"file_{i}"
            open(os.path.join(cfg.attachments_dir, name), "wb").write(resp.content)
        except Exception:
            pass
        progress(phase="attachments", done=i + 1, total=len(urls), msg=f"{i+1}/{len(urls)} files")
    # dedupe identical
    seen = {}
    for f in sorted(glob.glob(os.path.join(cfg.attachments_dir, "*"))):
        if not os.path.isfile(f):
            continue
        h = hashlib.md5(open(f, "rb").read()).hexdigest()
        if h in seen:
            os.remove(f)
        else:
            seen[h] = f
