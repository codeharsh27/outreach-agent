-- ============================================================
-- Outreach Agent — Supabase Schema
-- Paste this entire file into: Supabase Dashboard → SQL Editor → Run
-- ============================================================

-- Companies discovered from YC, GitHub Trending, ProductHunt, etc.
CREATE TABLE IF NOT EXISTS companies (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    domain          TEXT,
    description     TEXT,
    tags            TEXT,           -- JSON array as string
    batch           TEXT,           -- YC batch e.g. "Winter 2025"
    github_org      TEXT,
    linkedin_url    TEXT,
    twitter_url     TEXT,
    hq_country      TEXT,
    team_size       TEXT,
    funding         TEXT,
    source          TEXT,           -- yc | github_trending | producthunt | wellfound | a16z
    tier            TEXT,           -- A | B
    fit_score       REAL,
    pain_point      TEXT,
    evidence_url    TEXT,
    suggested_angle TEXT,
    status          TEXT DEFAULT 'queued',  -- queued | researched | contacted | drafted_ready | approved | sent | skip
    discovered_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, domain)
);

-- Contacts found for each company
CREATE TABLE IF NOT EXISTS contacts (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT REFERENCES companies(id) ON DELETE CASCADE,
    name            TEXT,
    role            TEXT,
    email           TEXT,
    linkedin_url    TEXT,
    twitter_url     TEXT,
    email_verified  BOOLEAN DEFAULT FALSE,
    email_source    TEXT,           -- github | hunter | snovio | minelead | pattern
    found_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Generated outreach drafts (email only)
CREATE TABLE IF NOT EXISTS drafts (
    id              BIGSERIAL PRIMARY KEY,
    company_id      BIGINT REFERENCES companies(id) ON DELETE CASCADE,
    contact_id      BIGINT REFERENCES contacts(id) ON DELETE CASCADE,
    email_subject   TEXT,
    email_body      TEXT,
    status          TEXT DEFAULT 'pending',  -- pending | drafted_ready | approved | edited | skipped
    telegram_msg_id TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    approved_at     TIMESTAMPTZ
);

-- Tracks each email actually sent
CREATE TABLE IF NOT EXISTS sends (
    id              BIGSERIAL PRIMARY KEY,
    draft_id        BIGINT REFERENCES drafts(id) ON DELETE CASCADE,
    platform        TEXT DEFAULT 'email',
    sent_at         TIMESTAMPTZ,
    scheduled_for   TIMESTAMPTZ,
    status          TEXT DEFAULT 'queued',   -- queued | sent | failed
    error           TEXT
);

-- Follow-up emails
CREATE TABLE IF NOT EXISTS follow_ups (
    id              BIGSERIAL PRIMARY KEY,
    send_id         BIGINT REFERENCES sends(id) ON DELETE CASCADE,
    due_at          TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    status          TEXT DEFAULT 'pending'   -- pending | sent | skipped
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(status);
CREATE INDEX IF NOT EXISTS idx_companies_fit_score ON companies(fit_score DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_company_id ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE INDEX IF NOT EXISTS idx_drafts_company_id ON drafts(company_id);
CREATE INDEX IF NOT EXISTS idx_sends_status ON sends(status);
