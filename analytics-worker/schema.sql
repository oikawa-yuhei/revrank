CREATE TABLE IF NOT EXISTS page_views (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  page     TEXT NOT NULL,
  referrer TEXT DEFAULT '',
  viewed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pv_date ON page_views(viewed_at);
CREATE INDEX IF NOT EXISTS idx_pv_page ON page_views(page);
