# ESPORTS ARENA

Production-ready esports tournament platform with wallet system, agents, tournaments, and admin panel.

**Theme:** Black + Neon Green  
**Stack:** Flask, SQLAlchemy, PostgreSQL/SQLite, Cloudinary, Vanilla JS/CSS/HTML + Jinja2

## Features

- Player, Agent, Admin roles with server-side RBAC
- Wallet with atomic transactions (deposit, withdraw, hold/release, prizes)
- Manual QR deposits via Admin or Agent
- Admin direct wallet load/deduct
- Withdrawals with user QR upload
- Tournaments (join with entry fee), Rooms, Match results, Prize distribution
- Leaderboard, News CMS, Notifications, Audit logs

## Quick Start (Development)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env if needed (defaults to SQLite at /tmp/esports_arena.db)

python run.py
# In another terminal:
python seed.py
```

Open http://localhost:5000

### Demo Credentials

| Role   | Username | Password  |
|--------|----------|-----------|
| Admin  | admin    | admin123  |
| Player | player1  | player123 |
| Agent  | agent1   | agent123  |

## Environment Variables

- `DATABASE_URL` – PostgreSQL (Neon) or omit for SQLite (`sqlite:////tmp/esports_arena.db`)
- `SECRET_KEY` – Flask secret
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` – image uploads (optional; uploads fall back to local)

## Main Flows

1. **Register / Login** as player
2. **Add money** → Admin deposit (upload screenshot) or Agent deposit
3. **Admin** approves deposit → wallet credited
4. **Join tournament** from tournament detail page (entry fee debited)
5. **Withdraw** → funds held → Admin approves & marks paid
6. **Agent** can load wallets and earn commission

## Deployment (Vercel + Neon)

1. Create Neon PostgreSQL database, copy connection string.
2. Set env vars on Vercel: `DATABASE_URL`, `SECRET_KEY`, Cloudinary keys, `FLASK_ENV=production`.
3. Deploy; run seed against Neon once.

## Critical Rules Implemented

- Never modify wallet without a `WalletTransaction`
- Atomic operations with row locking
- Admin direct load ≠ user deposit request
- Withdrawal hold → release or paid
- Prize only after admin result approval
- Server-side RBAC on all sensitive routes

Brand: **ESPORTS ARENA**


## Vercel + Neon (production)

1. Create a free DB at [Neon](https://neon.tech) → copy connection string.
2. Push this repo to GitHub → Import on [Vercel](https://vercel.com).
3. Vercel project **Environment Variables**:
   - `DATABASE_URL` = `postgresql://...?sslmode=require` (Neon URI)
   - `SECRET_KEY` = long random string
   - `FLASK_ENV` = `production`
   - Optional Cloudinary: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
4. Deploy. Then run seed once against Neon:

```bash
export DATABASE_URL='postgresql://...?sslmode=require'
python seed.py
```

Entry: `wsgi.py` (see `vercel.json`).
