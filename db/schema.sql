-- ================================================================
-- PandaMusic v2 — Neon PostgreSQL Schema
-- Run this ONCE on your Neon DB before starting the server
-- ================================================================

-- Users
CREATE TABLE IF NOT EXISTS users (
    id                   SERIAL PRIMARY KEY,
    name                 TEXT,
    email                TEXT UNIQUE NOT NULL,
    referral_code        TEXT UNIQUE,
    referred_by          TEXT,                          -- referral code used at signup
    trial_start_date     TIMESTAMP DEFAULT NOW(),
    subscription_active  BOOLEAN DEFAULT FALSE,
    subscription_expiry  TIMESTAMP,
    fcm_token            TEXT,
    created_at           TIMESTAMP DEFAULT NOW()
);

-- Magic link tokens (replaces OTP)
CREATE TABLE IF NOT EXISTS magic_links (
    id         SERIAL PRIMARY KEY,
    email      TEXT NOT NULL,
    token      TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used       BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Devices (max 2 per user)
CREATE TABLE IF NOT EXISTS devices (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
    device_id     TEXT UNIQUE NOT NULL,
    device_name   TEXT,
    registered_at TIMESTAMP DEFAULT NOW(),
    last_seen     TIMESTAMP DEFAULT NOW()
);

-- Game scores (3 games: 2048, blocks, arrow)
CREATE TABLE IF NOT EXISTS game_scores (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    game         TEXT NOT NULL CHECK (game IN ('2048', 'blocks', 'arrow')),
    score        INTEGER NOT NULL,
    submitted_at TIMESTAMP DEFAULT NOW()
);

-- Play history (for monthly stats)
CREATE TABLE IF NOT EXISTS play_history (
    id                 SERIAL PRIMARY KEY,
    user_id            INTEGER REFERENCES users(id) ON DELETE CASCADE,
    video_id           TEXT NOT NULL,
    title              TEXT,
    duration_played_ms INTEGER,
    played_at          TIMESTAMP DEFAULT NOW()
);

-- Referral discounts
CREATE TABLE IF NOT EXISTS referral_discounts (
    id       SERIAL PRIMARY KEY,
    user_id  INTEGER REFERENCES users(id) ON DELETE CASCADE,
    source   TEXT NOT NULL CHECK (source IN ('referral', 'game_winner')),
    amount   INTEGER NOT NULL,           -- in rupees
    month    TEXT NOT NULL,              -- e.g. '2026-10'
    applied  BOOLEAN DEFAULT FALSE
);

-- Razorpay payment orders
CREATE TABLE IF NOT EXISTS payment_orders (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER REFERENCES users(id) ON DELETE CASCADE,
    razorpay_order_id TEXT NOT NULL,
    amount_paise     INTEGER NOT NULL,
    status           TEXT DEFAULT 'created',   -- created | paid | failed
    created_at       TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- Indexes for performance
-- ================================================================
CREATE INDEX IF NOT EXISTS idx_magic_links_token   ON magic_links(token);
CREATE INDEX IF NOT EXISTS idx_magic_links_email   ON magic_links(email);
CREATE INDEX IF NOT EXISTS idx_devices_user_id     ON devices(user_id);
CREATE INDEX IF NOT EXISTS idx_devices_device_id   ON devices(device_id);
CREATE INDEX IF NOT EXISTS idx_game_scores_game    ON game_scores(game, submitted_at);
CREATE INDEX IF NOT EXISTS idx_play_history_user   ON play_history(user_id, played_at);
CREATE INDEX IF NOT EXISTS idx_referral_user_month ON referral_discounts(user_id, month);
