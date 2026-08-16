const cors = (origin) => ({
  'Access-Control-Allow-Origin': origin || '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-Admin-Key',
});

export default {
  async fetch(request, env) {
    const url    = new URL(request.url);
    const origin = request.headers.get('Origin') || '';

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors(origin) });
    }

    // ── POST /track ──────────────────────────────────────────
    if (request.method === 'POST' && url.pathname === '/track') {
      try {
        const body = await request.json();
        const page = String(body.p || '/').slice(0, 200);
        const ref  = String(body.r || '').slice(0, 500);
        await env.DB.prepare(
          'INSERT INTO page_views (page, referrer, viewed_at) VALUES (?, ?, datetime("now"))'
        ).bind(page, ref).run();
        return new Response('ok', { headers: cors(origin) });
      } catch {
        return new Response('error', { status: 500, headers: cors(origin) });
      }
    }

    // ── GET /stats ───────────────────────────────────────────
    if (request.method === 'GET' && url.pathname === '/stats') {
      const key = request.headers.get('X-Admin-Key') || url.searchParams.get('key');
      if (!env.ADMIN_KEY || key !== env.ADMIN_KEY) {
        return new Response('Unauthorized', { status: 401 });
      }

      const days = Math.min(parseInt(url.searchParams.get('days') || '30'), 365);
      const since = `-${days} days`;

      const [total, byPage, byDay, recent] = await Promise.all([
        env.DB.prepare(
          'SELECT COUNT(*) as n FROM page_views WHERE viewed_at >= datetime("now", ?)'
        ).bind(since).first(),

        env.DB.prepare(`
          SELECT page, COUNT(*) as count
          FROM page_views
          WHERE viewed_at >= datetime('now', ?)
          GROUP BY page ORDER BY count DESC LIMIT 50
        `).bind(since).all(),

        env.DB.prepare(`
          SELECT date(viewed_at) as date, COUNT(*) as count
          FROM page_views
          WHERE viewed_at >= datetime('now', ?)
          GROUP BY date(viewed_at) ORDER BY date ASC
        `).bind(since).all(),

        env.DB.prepare(`
          SELECT page, referrer, viewed_at
          FROM page_views ORDER BY viewed_at DESC LIMIT 30
        `).all(),
      ]);

      return new Response(JSON.stringify({
        total:   total?.n   || 0,
        by_page: byPage.results,
        by_day:  byDay.results,
        recent:  recent.results,
      }), {
        headers: { ...cors(origin), 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};
