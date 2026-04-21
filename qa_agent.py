"""
QA Agent v2 для stoq.ai — версия для GitHub Actions (headless)
"""

import asyncio
import json
import base64
import datetime
import os
import sys
import urllib.request
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Установите: pip install playwright && playwright install chromium")
    sys.exit(1)

TARGET_URL = "https://stoq.ai/"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SCREENS = [
    {"name": "Mobile",   "label": "Мобильный (iPhone 14)", "width": 390,  "height": 844,  "icon": "📱", "device_scale_factor": 3, "is_mobile": True,  "has_touch": True,  "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"},
    {"name": "Tablet",   "label": "Планшет (iPad)",        "width": 768,  "height": 1024, "icon": "📲", "device_scale_factor": 2, "is_mobile": True,  "has_touch": True,  "user_agent": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"},
    {"name": "Laptop",   "label": "Ноутбук (1280px)",      "width": 1280, "height": 800,  "icon": "💻", "device_scale_factor": 1, "is_mobile": False, "has_touch": False, "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
    {"name": "Desktop",  "label": "Десктоп (1920px)",      "width": 1920, "height": 1080, "icon": "🖥", "device_scale_factor": 1, "is_mobile": False, "has_touch": False, "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
]


async def check_horizontal_scroll(page, screen):
    return await page.evaluate(f"""
        () => {{
            const vw = {screen['width']};
            const docW = document.documentElement.scrollWidth;
            const hasScroll = docW > vw + 2;
            const culprits = [];
            if (hasScroll) {{
                document.querySelectorAll('*').forEach(el => {{
                    const rect = el.getBoundingClientRect();
                    if (rect.right > vw + 2 && rect.width > 10 && rect.height > 2) {{
                        const tag = el.tagName.toLowerCase();
                        const id = el.id ? '#' + el.id : '';
                        const cls = el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.') : '';
                        const text = el.innerText ? el.innerText.trim().slice(0, 40) : '';
                        culprits.push({{ selector: tag + id + cls, text, right: Math.round(rect.right), top: Math.round(rect.top), left: Math.round(rect.left), bottom: Math.round(rect.bottom), width: Math.round(rect.width), height: Math.round(rect.height) }});
                    }}
                }});
            }}
            return {{ hasScroll, docWidth: docW, viewportWidth: vw, culprits: culprits.slice(0, 8) }};
        }}
    """)


async def check_overflow_elements(page, screen):
    return await page.evaluate(f"""
        () => {{
            const vw = {screen['width']};
            const found = [];
            document.querySelectorAll('*').forEach(el => {{
                const rect = el.getBoundingClientRect();
                const parent = el.parentElement;
                if (!parent) return;
                const pRect = parent.getBoundingClientRect();
                const overflowsRight = rect.right > pRect.right + 15;
                const overflowsLeft  = rect.left < pRect.left - 15;
                if ((overflowsRight || overflowsLeft) && rect.width > 20 && rect.height > 5) {{
                    const tag = el.tagName.toLowerCase();
                    const id = el.id ? '#' + el.id : '';
                    const cls = el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.') : '';
                    const text = el.innerText ? el.innerText.trim().slice(0, 50) : '(нет текста)';
                    found.push({{ selector: tag + id + cls, text, overflowsRight, overflowsLeft, left: Math.round(rect.left), right: Math.round(rect.right), top: Math.round(rect.top), width: Math.round(rect.width), height: Math.round(rect.height), parentRight: Math.round(pRect.right), excess: Math.round(rect.right - pRect.right) }});
                }}
            }});
            return found.slice(0, 10);
        }}
    """)


async def check_broken_images(page):
    return await page.evaluate("""
        () => {
            const all = Array.from(document.querySelectorAll('img'));
            const broken = all.filter(img => !img.complete || img.naturalWidth === 0)
                .map(img => ({ src: img.src || '(нет src)', alt: img.alt || '(нет alt)', top: Math.round(img.getBoundingClientRect().top), left: Math.round(img.getBoundingClientRect().left), width: Math.round(img.getBoundingClientRect().width), height: Math.round(img.getBoundingClientRect().height) }));
            return { broken, total: all.length };
        }
    """)


async def check_truncated_text(page):
    return await page.evaluate("""
        () => {
            const found = [];
            document.querySelectorAll('p,h1,h2,h3,h4,h5,span,a,li,button,div,td,label').forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.textOverflow === 'ellipsis' && (style.overflow === 'hidden' || style.overflowX === 'hidden') && el.scrollWidth > el.clientWidth + 2) {
                    const rect = el.getBoundingClientRect();
                    found.push({ tag: el.tagName.toLowerCase(), fullText: el.innerText ? el.innerText.trim().slice(0, 100) : '', visibleWidth: Math.round(el.clientWidth), fullWidth: Math.round(el.scrollWidth), top: Math.round(rect.top), left: Math.round(rect.left) });
                }
            });
            return found.slice(0, 8);
        }
    """)


async def check_overlapping_elements(page):
    return await page.evaluate("""
        () => {
            const els = Array.from(document.querySelectorAll('button,a,input,select,h1,h2,[role="button"]'))
                .filter(el => { const r = el.getBoundingClientRect(); return r.width > 5 && r.height > 5 && r.top >= 0; }).slice(0, 60);
            const overlaps = [];
            for (let i = 0; i < els.length; i++) {
                for (let j = i + 1; j < els.length; j++) {
                    const r1 = els[i].getBoundingClientRect();
                    const r2 = els[j].getBoundingClientRect();
                    if (!(r1.right <= r2.left || r2.right <= r1.left || r1.bottom <= r2.top || r2.bottom <= r1.top)) {
                        const t1 = (els[i].innerText || els[i].tagName).trim().slice(0,30);
                        const t2 = (els[j].innerText || els[j].tagName).trim().slice(0,30);
                        overlaps.push({ el1: els[i].tagName.toLowerCase() + ': "' + t1 + '"', el2: els[j].tagName.toLowerCase() + ': "' + t2 + '"', top: Math.round(Math.min(r1.top, r2.top)), left: Math.round(Math.min(r1.left, r2.left)) });
                    }
                }
            }
            return overlaps.slice(0, 5);
        }
    """)


async def check_broken_links(page):
    links = await page.evaluate("""
        () => {
            const hrefs = Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({ href: a.href, text: (a.innerText || '').trim().slice(0,40) }))
                .filter(l => l.href.startsWith('http') && !l.href.includes('mailto') && !l.href.includes('tel'));
            const seen = new Set();
            return hrefs.filter(l => { if (seen.has(l.href)) return false; seen.add(l.href); return true; }).slice(0, 20);
        }
    """)
    broken = []
    ok_count = 0
    for link in links:
        try:
            req = urllib.request.Request(link["href"], method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status >= 400:
                    broken.append({"url": link["href"], "text": link["text"], "status": resp.status})
                else:
                    ok_count += 1
        except Exception as e:
            err = str(e)
            if any(c in err for c in ["404","403","500","410"]):
                broken.append({"url": link["href"], "text": link["text"], "error": err[:60]})
            else:
                ok_count += 1
    return {"checked": len(links), "ok": ok_count, "broken": broken}


async def check_performance(page):
    return await page.evaluate("""
        () => {
            const nav = performance.getEntriesByType('navigation')[0];
            const paint = performance.getEntriesByType('paint');
            const fcp = paint.find(p => p.name === 'first-contentful-paint');
            const resources = performance.getEntriesByType('resource');
            const slowResources = resources.filter(r => r.duration > 1000)
                .map(r => ({ url: r.name.split('/').pop().slice(0,50), duration: Math.round(r.duration) })).slice(0,5);
            return {
                fcp: fcp ? Math.round(fcp.startTime) : 0,
                loadComplete: nav ? Math.round(nav.loadEventEnd) : 0,
                transferSizeKB: nav ? Math.round(nav.transferSize / 1024) : 0,
                resourceCount: resources.length,
                slowResources
            };
        }
    """)


async def get_page_text(page):
    return await page.evaluate("""
        () => {
            const clone = document.body.cloneNode(true);
            clone.querySelectorAll('script,style,noscript,svg').forEach(el => el.remove());
            return clone.innerText.replace(/\\s+/g, ' ').trim().slice(0, 3000);
        }
    """)


async def take_annotated_screenshot(page, problem_coords):
    if problem_coords:
        await page.evaluate(f"""
            () => {{
                {json.dumps(problem_coords)}.forEach((c, i) => {{
                    const d = document.createElement('div');
                    d.style.cssText = `position:fixed;left:${{c.left}}px;top:${{c.top}}px;width:${{c.width||100}}px;height:${{c.height||30}}px;border:3px solid #ff0044;background:rgba(255,0,68,0.08);z-index:999999;pointer-events:none;box-sizing:border-box;`;
                    const l = document.createElement('div');
                    l.textContent = c.label || ('Проблема ' + (i+1));
                    l.style.cssText = `position:absolute;top:-22px;left:0;background:#ff0044;color:white;font-size:11px;font-family:monospace;padding:2px 6px;border-radius:3px;white-space:nowrap;max-width:200px;overflow:hidden;text-overflow:ellipsis;`;
                    d.appendChild(l);
                    document.body.appendChild(d);
                }});
            }}
        """)
        await page.wait_for_timeout(300)
    screenshot = await page.screenshot(full_page=True)
    if problem_coords:
        await page.evaluate("() => { document.querySelectorAll('div[style*=\"z-index:999999\"]').forEach(el => el.remove()); }")
    return base64.b64encode(screenshot).decode()


async def analyze_with_ai(all_issues, page_text, api_key):
    issues_text = "\n".join([f"[{i['severity'].upper()}] {i['title']}: {i.get('detail','')}" for i in all_issues])
    prompt = f"""Ты — опытный QA-инженер. Проанализируй результаты проверки сайта stoq.ai.

РЕЗУЛЬТАТЫ:
{issues_text}

ТЕКСТ СО СТРАНИЦЫ:
{page_text[:2000]}

Дай анализ на русском:
1. Оценка качества (1-10) с обоснованием
2. Критические проблемы — что исправить первым
3. Качество текста и перевода
4. Топ-3 рекомендации разработчикам"""

    payload = json.dumps({"model": "claude-sonnet-4-20250514", "max_tokens": 1200, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=payload,
        headers={"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["content"][0]["text"]


def generate_report(results, ai_analysis=None):
    date_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    all_issues = [i for r in results for i in r.get("issues", [])]
    crit = sum(1 for i in all_issues if i["severity"] == "critical")
    warn = sum(1 for i in all_issues if i["severity"] == "warning")
    ok   = sum(1 for i in all_issues if i["severity"] == "ok")

    def issue_html(issue):
        cls = {"critical":"crit","warning":"warn","ok":"ok","info":"info"}.get(issue["severity"],"info")
        badge_labels = {"critical":"КРИТ","warning":"WARN","ok":"OK","info":"INFO"}
        details_html = "".join(
            f'<li>{d["text"]} {"<span class=coord>📍 top:"+str(d["coords"]["top"])+"px left:"+str(d["coords"]["left"])+"px</span>" if d.get("coords") else ""}</li>'
            for d in issue.get("details", [])
        )
        return f"""<div class="issue {cls}">
            <div class="issue-header"><span class="badge badge-{cls}">{badge_labels.get(issue['severity'],'?')}</span><span class="issue-title">{issue['title']}</span></div>
            {f'<div class="issue-detail">{issue["detail"]}</div>' if issue.get("detail") else ""}
            {f'<ul class="details-list">{details_html}</ul>' if details_html else ""}
        </div>"""

    screens_html = ""
    screenshots_html = ""
    for r in results:
        s = r.get("screen", {})
        issues = r.get("issues", [])
        crit_c = sum(1 for i in issues if i["severity"] == "critical")
        warn_c = sum(1 for i in issues if i["severity"] == "warning")
        status_cls = "crit" if crit_c > 0 else ("warn" if warn_c > 0 else "ok")
        status_txt = f"{crit_c} крит, {warn_c} предупр." if (crit_c + warn_c) > 0 else "Всё OK"
        screens_html += f"""<div class="screen-block">
            <div class="screen-title"><span>{s.get('icon','')}</span><span>{s.get('label',s.get('name',''))}</span>
            <span class="screen-size">{s.get('width','')}×{s.get('height','')}px</span>
            <span class="status-badge {status_cls}">{status_txt}</span></div>
            {"".join(issue_html(i) for i in issues)}</div>"""
        if r.get("screenshot"):
            screenshots_html += f"""<div class="screenshot-wrap">
                <div class="screen-title">{s.get('icon','')} {s.get('label','')} — скриншот с пометками</div>
                <img src="data:image/png;base64,{r['screenshot']}" loading="lazy"></div>"""

    ai_html = f"""<div class="ai-block"><div class="ai-label">🤖 ИИ-анализ Claude</div>
        <div class="ai-text">{ai_analysis}</div></div>""" if ai_analysis else ""

    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<title>QA Отчёт — stoq.ai — {date_str}</title>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;max-width:1000px;margin:40px auto;padding:24px;background:#f5f5fa;color:#1a1a2e}}
h1{{font-size:26px;font-weight:700;margin-bottom:4px}}
.meta{{color:#888;font-size:13px;margin-bottom:28px}}
.summary{{display:flex;gap:14px;margin-bottom:32px;flex-wrap:wrap}}
.stat{{padding:16px 28px;border-radius:12px;font-weight:700;font-size:26px;text-align:center;min-width:100px}}
.stat span{{display:block;font-size:11px;font-weight:400;margin-top:4px;opacity:.7}}
.stat.crit{{background:#fff0f3;color:#cc2244}}.stat.warn{{background:#fffbf0;color:#aa8800}}.stat.ok{{background:#f0fff8;color:#008844}}
h2{{font-size:18px;font-weight:600;margin:32px 0 14px}}
.screen-block{{background:#fff;border-radius:14px;padding:20px 22px;margin-bottom:20px;box-shadow:0 1px 6px rgba(0,0,0,.07)}}
.screen-title{{display:flex;align-items:center;gap:10px;font-size:15px;font-weight:600;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f0f0f5}}
.screen-size{{color:#999;font-size:12px;font-weight:400}}
.status-badge{{margin-left:auto;font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px}}
.status-badge.crit{{background:#fff0f3;color:#cc2244}}.status-badge.warn{{background:#fffbf0;color:#aa8800}}.status-badge.ok{{background:#f0fff8;color:#008844}}
.issue{{padding:12px 14px;border-radius:10px;margin-bottom:10px}}
.issue.crit{{background:#fff0f3;border-left:4px solid #ff4466}}.issue.warn{{background:#fffbf0;border-left:4px solid #ffcc00}}
.issue.ok{{background:#f0fff8;border-left:4px solid #00cc66}}.issue.info{{background:#f0f4ff;border-left:4px solid #6c63ff}}
.issue-header{{display:flex;align-items:center;gap:10px}}
.badge{{font-size:9px;font-weight:700;padding:3px 7px;border-radius:4px;white-space:nowrap;flex-shrink:0}}
.badge-crit{{background:#ff4466;color:#fff}}.badge-warn{{background:#ffcc00;color:#000}}.badge-ok{{background:#00cc66;color:#fff}}.badge-info{{background:#6c63ff;color:#fff}}
.issue-title{{font-size:13px;font-weight:600}}.issue-detail{{font-size:12px;color:#666;margin:6px 0 4px}}
.details-list{{margin:8px 0 0;padding-left:18px}}.details-list li{{font-size:12px;color:#444;margin-bottom:4px;line-height:1.5;font-family:Consolas,monospace}}
.coord{{display:inline-block;margin-left:8px;background:#f0f0f8;color:#6c63ff;font-size:10px;padding:1px 6px;border-radius:4px}}
.ai-block{{background:#fff;border-radius:14px;padding:22px;margin-top:28px;border-left:5px solid #6c63ff;box-shadow:0 1px 6px rgba(0,0,0,.07)}}
.ai-label{{font-size:12px;font-weight:700;color:#6c63ff;margin-bottom:12px;letter-spacing:.05em}}
.ai-text{{font-size:13px;line-height:1.8;white-space:pre-wrap}}
.screenshot-wrap{{background:#fff;border-radius:14px;padding:20px;margin-bottom:20px;box-shadow:0 1px 6px rgba(0,0,0,.07)}}
.screenshot-wrap img{{width:100%;border-radius:8px;border:1px solid #eee;margin-top:12px}}
</style></head><body>
<h1>QA Отчёт — stoq.ai</h1>
<div class="meta">Дата: {date_str} | Playwright QA Agent v2 | GitHub Actions</div>
<div class="summary">
  <div class="stat crit">{crit}<span>критичных</span></div>
  <div class="stat warn">{warn}<span>предупреждений</span></div>
  <div class="stat ok">{ok}<span>OK</span></div>
</div>
<h2>Результаты по экранам</h2>
{screens_html}
{ai_html}
<h2>Скриншоты с пометками</h2>
{screenshots_html or '<p style="color:#999;font-size:13px">Скриншоты не сделаны</p>'}
</body></html>"""


async def run_audit():
    print("\n" + "="*55)
    print("  QA Agent v2 — stoq.ai (GitHub Actions)")
    print("="*55 + "\n")

    results = []
    all_page_text = ""

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)  # headless для GitHub Actions

        # Общие проверки
        print("[1/5] Общие проверки...")
        context = await browser.new_context(viewport={"width": 1280, "height": 800}, user_agent=SCREENS[2]["user_agent"])
        page = await context.new_page()
        console_errors = []
        page.on("console", lambda m: console_errors.append({"type": m.type, "text": m.text}) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append({"type": "pageerror", "text": str(e)}))

        t0 = datetime.datetime.now()
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        load_time = (datetime.datetime.now() - t0).total_seconds()
        await page.wait_for_timeout(2000)

        perf = await check_performance(page)
        all_page_text = await get_page_text(page)
        print(f"   Загрузка: {load_time:.1f}с | FCP: {perf['fcp']}мс | Ресурсов: {perf['resourceCount']}")

        print("   Проверяю ссылки...")
        links_result = await check_broken_links(page)
        await page.close()
        await context.close()

        general_issues = []
        sev = "ok" if load_time < 2 else ("warning" if load_time < 4 else "critical")
        desc = {"ok": "Быстрая загрузка", "warning": "Средняя скорость — рекомендуется оптимизация", "critical": "Медленная загрузка — требует оптимизации"}[sev]
        general_issues.append({"severity": sev, "title": f"Скорость загрузки: {load_time:.1f}с", "detail": desc, "details": []})

        if perf["fcp"] > 0:
            fcp_s = perf["fcp"] / 1000
            sev2 = "ok" if fcp_s < 1.8 else ("warning" if fcp_s < 3 else "critical")
            general_issues.append({"severity": sev2, "title": f"First Contentful Paint: {fcp_s:.1f}с", "detail": "Время до появления первого контента", "details": []})

        if perf["slowResources"]:
            general_issues.append({"severity": "warning", "title": f"Медленные ресурсы: {len(perf['slowResources'])} файлов > 1с", "detail": "Файлы замедляющие загрузку:",
                "details": [{"text": f'{r["url"]} — {r["duration"]}мс', "coords": None} for r in perf["slowResources"]]})

        if console_errors:
            general_issues.append({"severity": "critical", "title": f"JS ошибки в консоли: {len(console_errors)} шт", "detail": "Ошибки JavaScript:",
                "details": [{"text": f'[{e["type"]}] {e["text"][:120]}', "coords": None} for e in console_errors[:8]]})
        else:
            general_issues.append({"severity": "ok", "title": "JS ошибки в консоли: не обнаружены", "detail": "", "details": []})

        if links_result["broken"]:
            general_issues.append({"severity": "critical", "title": f"Битые ссылки: {len(links_result['broken'])} из {links_result['checked']}", "detail": "Ссылки которые не работают:",
                "details": [{"text": f'{l.get("text","?")} → {l["url"][:80]} [{l.get("status", l.get("error","?"))}]', "coords": None} for l in links_result["broken"]]})
        else:
            general_issues.append({"severity": "ok", "title": f"Ссылки: все {links_result['checked']} работают", "detail": "", "details": []})

        results.append({"screen": {"name": "General", "label": "Общие проверки", "icon": "⚡"}, "issues": general_issues})

        # Проверка на каждом экране
        for idx, screen in enumerate(SCREENS):
            print(f"\n[{idx+2}/5] {screen['icon']} {screen['label']} ({screen['width']}×{screen['height']})...")
            context = await browser.new_context(
                viewport={"width": screen["width"], "height": screen["height"]},
                device_scale_factor=screen["device_scale_factor"],
                is_mobile=screen["is_mobile"], has_touch=screen["has_touch"],
                user_agent=screen["user_agent"]
            )
            page = await context.new_page()
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)

            issues = []
            problem_coords = []

            hscroll = await check_horizontal_scroll(page, screen)
            if hscroll["hasScroll"]:
                culprit_details = [{"text": f'{c["selector"]} | текст: "{c["text"]}" | right: {c["right"]}px (выходит на {c["right"] - screen["width"]}px)', "coords": {"top": max(0, c["top"]), "left": max(0, c["left"])}} for c in hscroll["culprits"]]
                for c in hscroll["culprits"]:
                    problem_coords.append({"top": max(0,c["top"]), "left": max(0,c["left"]), "width": min(c["width"], screen["width"]), "height": c["bottom"]-c["top"], "label": f'Overflow: {c["selector"][:30]}'})
                issues.append({"severity": "critical", "title": f"Горизонтальный скролл: страница {hscroll['docWidth']}px при экране {screen['width']}px", "detail": f"Лишних пикселей: {hscroll['docWidth'] - screen['width']}px. Виновные элементы:", "details": culprit_details})
            else:
                issues.append({"severity": "ok", "title": "Горизонтальный скролл отсутствует", "detail": "", "details": []})

            overflow_els = await check_overflow_elements(page, screen)
            if overflow_els:
                ov_details = []
                for el in overflow_els:
                    direction = "вправо" if el["overflowsRight"] else "влево"
                    ov_details.append({"text": f'{el["selector"]} | "{el["text"]}" | выходит {direction} на {abs(el["excess"])}px | top:{el["top"]}px left:{el["left"]}px', "coords": {"top": max(0,el["top"]), "left": max(0,el["left"])}})
                    problem_coords.append({"top": max(0,el["top"]), "left": max(0,el["left"]), "width": el["width"], "height": el["height"], "label": f'Overflow {direction}: {el["selector"][:25]}'})
                issues.append({"severity": "warning", "title": f"Элементов выходящих за границы: {len(overflow_els)}", "detail": "Детали:", "details": ov_details})
            else:
                issues.append({"severity": "ok", "title": "Все элементы в пределах экрана", "detail": "", "details": []})

            imgs = await check_broken_images(page)
            if imgs["broken"]:
                img_details = [{"text": f'src: {img["src"][:80]} | alt: "{img["alt"]}" | top:{img["top"]}px left:{img["left"]}px', "coords": {"top": max(0,img["top"]), "left": max(0,img["left"])}} for img in imgs["broken"]]
                for img in imgs["broken"]:
                    if img["width"] > 0:
                        problem_coords.append({"top": max(0,img["top"]), "left": max(0,img["left"]), "width": img["width"], "height": img["height"], "label": f'Сломана: {img["src"].split("/")[-1][:30]}'})
                issues.append({"severity": "critical", "title": f"Сломанные картинки: {len(imgs['broken'])} из {imgs['total']}", "detail": "Картинки которые не загрузились:", "details": img_details})
            else:
                issues.append({"severity": "ok", "title": f"Все {imgs['total']} картинок загружены", "detail": "", "details": []})

            truncated = await check_truncated_text(page)
            if truncated:
                tr_details = [{"text": f'<{t["tag"]}> | текст: "{t["fullText"]}" | видимая:{t["visibleWidth"]}px полная:{t["fullWidth"]}px | top:{t["top"]}px left:{t["left"]}px', "coords": {"top": max(0,t["top"]), "left": max(0,t["left"])}} for t in truncated]
                for t in truncated:
                    problem_coords.append({"top": max(0,t["top"]), "left": max(0,t["left"]), "width": t["visibleWidth"], "height": 30, "label": f'Обрезан: "{t["fullText"][:20]}..."'})
                issues.append({"severity": "warning", "title": f"Обрезанный текст (...): {len(truncated)} элементов", "detail": "Текст скрыт троеточием:", "details": tr_details})
            else:
                issues.append({"severity": "ok", "title": "Обрезанный текст не обнаружен", "detail": "", "details": []})

            overlaps = await check_overlapping_elements(page)
            if overlaps:
                ov_details = [{"text": f'{o["el1"]}  ↔  {o["el2"]} | top:{o["top"]}px left:{o["left"]}px', "coords": {"top": max(0,o["top"]), "left": max(0,o["left"])}} for o in overlaps]
                for o in overlaps:
                    problem_coords.append({"top": max(0,o["top"]), "left": max(0,o["left"]), "width": 120, "height": 40, "label": f'Перекрытие: {o["el1"][:20]}'})
                issues.append({"severity": "warning", "title": f"Перекрытие элементов: {len(overlaps)} случаев", "detail": "Элементы перекрывают друг друга:", "details": ov_details})
            else:
                issues.append({"severity": "ok", "title": "Перекрытие элементов не обнаружено", "detail": "", "details": []})

            print(f"   → скриншот с пометками ({len(problem_coords)} проблем)...")
            screenshot_b64 = await take_annotated_screenshot(page, problem_coords)

            crit_c = sum(1 for i in issues if i["severity"] == "critical")
            warn_c = sum(1 for i in issues if i["severity"] == "warning")
            print(f"   ✓ Готово | Критичных: {crit_c} | Предупреждений: {warn_c}")

            results.append({"screen": screen, "issues": issues, "screenshot": screenshot_b64})
            await page.close()
            await context.close()

        await browser.close()

    # ИИ-анализ
    ai_analysis = None
    if ANTHROPIC_API_KEY:
        print("\n[AI] Запускаю ИИ-анализ...")
        try:
            all_issues_flat = [i for r in results for i in r.get("issues", [])]
            ai_analysis = await analyze_with_ai(all_issues_flat, all_page_text, ANTHROPIC_API_KEY)
            print("     ✓ Готово")
        except Exception as e:
            print(f"     ⚠ Ошибка: {e}")

    print("\n[OUT] Генерирую отчёт...")
    report_html = generate_report(results, ai_analysis)
    report_name = f"qa-report-stoqai-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
    Path(report_name).write_text(report_html, encoding="utf-8")

    all_issues_flat = [i for r in results for i in r.get("issues", [])]
    crit = sum(1 for i in all_issues_flat if i["severity"] == "critical")
    warn = sum(1 for i in all_issues_flat if i["severity"] == "warning")

    print(f"\n{'='*55}")
    print(f"  ГОТОВО! Крит: {crit} | Предупреждений: {warn}")
    print(f"  Отчёт: {report_name}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    asyncio.run(run_audit())
