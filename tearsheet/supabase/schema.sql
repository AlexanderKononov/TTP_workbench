-- Schema for tearsheet trade persistence (see SUPABASE_PLAN.md).
-- Run once in the Supabase SQL editor (or via the Supabase CLI) against a
-- fresh project. Safe to re-run only after dropping the tables below first -
-- it does not use "if not exists" guards, to avoid silently skipping a
-- schema change during development.

create extension if not exists pgcrypto;

create table participants (
    id          uuid primary key default gen_random_uuid(),
    username    text unique not null,
    created_at  timestamptz not null default now()
);

create table sessions (
    id              uuid primary key default gen_random_uuid(),
    participant_id  uuid not null references participants(id) on delete cascade,
    file_name       text not null,
    file_format     text not null check (file_format in ('A', 'B')),
    storage_path    text,
    uploaded_at     timestamptz not null default now(),
    trade_count     integer not null,
    inserted_count  integer not null default 0
);

create table trades (
    id              uuid primary key default gen_random_uuid(),
    participant_id  uuid not null references participants(id) on delete cascade,
    session_id      uuid not null references sessions(id) on delete cascade,
    trade_time      timestamptz not null,
    market          text not null,
    symbol          text not null,
    direction       text not null,
    profit          numeric not null,
    profit_pct      numeric,
    fee             numeric not null,
    net_pnl         numeric not null,
    trade_hash      text not null,
    created_at      timestamptz not null default now(),
    unique (participant_id, trade_hash)
);

create index trades_participant_time_idx on trades (participant_id, trade_time);
create index sessions_participant_idx on sessions (participant_id);
