/**
 * token_budget_tracker.js — Tracks token usage and estimated cost
 * per session and per day.
 *
 * Usage:
 *   node src/agent/hooks/token_budget_tracker.js [usage_event.json]
 *
 * Or called programmatically:
 *   const tracker = require('./token_budget_tracker');
 *   tracker.recordUsage({ provider: 'gemini', tokens_in: 500, tokens_out: 200 });
 *   tracker.report();
 */

const fs = require('fs');
const path = require('path');

const DATA_DIR = process.env.AGENT_STORAGE_PATH || './agent_data';
const BUDGET_FILE = path.join(DATA_DIR, 'token_budget.json');

// ── Cost Rates (USD per 1K tokens, approximate) ─────────

const RATES = {
    'gemini-2.0-flash': { input: 0.00010, output: 0.00040 },
    'gemini-1.5-pro':   { input: 0.00125, output: 0.00500 },
    'claude-3-opus':    { input: 0.01500, output: 0.07500 },
    'claude-3-sonnet':  { input: 0.00300, output: 0.01500 },
    'claude-3-haiku':   { input: 0.00025, output: 0.00125 },
    'gpt-4o':           { input: 0.00250, output: 0.01000 },
    'gpt-4o-mini':      { input: 0.00015, output: 0.00060 },
    'ollama':           { input: 0.00000, output: 0.00000 },  // Free (local)
    'default':          { input: 0.00100, output: 0.00400 },
};

// ── Budget State ────────────────────────────────────────

function loadBudget() {
    try {
        if (fs.existsSync(BUDGET_FILE)) {
            return JSON.parse(fs.readFileSync(BUDGET_FILE, 'utf-8'));
        }
    } catch (e) { /* start fresh */ }
    return {
        daily_limit_usd: 1.00,
        sessions: [],
        today: todayKey(),
        today_tokens_in: 0,
        today_tokens_out: 0,
        today_cost_usd: 0.0,
        lifetime_cost_usd: 0.0,
    };
}

function saveBudget(budget) {
    const dir = path.dirname(BUDGET_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(BUDGET_FILE, JSON.stringify(budget, null, 2), 'utf-8');
}

function todayKey() {
    return new Date().toISOString().slice(0, 10);
}

// ── Core Functions ──────────────────────────────────────

function recordUsage(event) {
    const budget = loadBudget();

    // Roll over to new day if needed
    if (budget.today !== todayKey()) {
        budget.today = todayKey();
        budget.today_tokens_in = 0;
        budget.today_tokens_out = 0;
        budget.today_cost_usd = 0.0;
    }

    const provider = event.provider || event.model || 'default';
    const tokensIn = event.tokens_in || event.input_tokens || 0;
    const tokensOut = event.tokens_out || event.output_tokens || 0;

    // Look up rate
    const rate = RATES[provider] || RATES['default'];
    const cost = (tokensIn / 1000 * rate.input) + (tokensOut / 1000 * rate.output);

    budget.today_tokens_in += tokensIn;
    budget.today_tokens_out += tokensOut;
    budget.today_cost_usd += cost;
    budget.lifetime_cost_usd += cost;

    // Budget warning
    const pct = budget.today_cost_usd / budget.daily_limit_usd;
    let warning = null;
    if (pct >= 1.0) {
        warning = `⚠ DAILY BUDGET EXCEEDED: $${budget.today_cost_usd.toFixed(4)} / $${budget.daily_limit_usd.toFixed(2)}`;
    } else if (pct >= 0.8) {
        warning = `⚠ 80% of daily budget used: $${budget.today_cost_usd.toFixed(4)} / $${budget.daily_limit_usd.toFixed(2)}`;
    }

    // Log session entry
    budget.sessions.push({
        timestamp: new Date().toISOString(),
        provider,
        tokens_in: tokensIn,
        tokens_out: tokensOut,
        cost_usd: parseFloat(cost.toFixed(6)),
    });

    // Keep only last 200 session entries
    if (budget.sessions.length > 200) {
        budget.sessions = budget.sessions.slice(-200);
    }

    saveBudget(budget);
    return { cost, warning, budget_remaining: budget.daily_limit_usd - budget.today_cost_usd };
}

function report() {
    const budget = loadBudget();
    console.log('═══ TOKEN BUDGET REPORT ═══');
    console.log(`Date      : ${budget.today}`);
    console.log(`Tokens In : ${budget.today_tokens_in.toLocaleString()}`);
    console.log(`Tokens Out: ${budget.today_tokens_out.toLocaleString()}`);
    console.log(`Today Cost: $${budget.today_cost_usd.toFixed(4)}`);
    console.log(`Daily Limit: $${budget.daily_limit_usd.toFixed(2)}`);
    console.log(`Lifetime  : $${budget.lifetime_cost_usd.toFixed(4)}`);
    console.log(`Sessions  : ${budget.sessions.length} logged`);
    const pct = ((budget.today_cost_usd / budget.daily_limit_usd) * 100).toFixed(1);
    console.log(`Usage     : ${pct}% of daily budget`);
    console.log('═══════════════════════════');
}

// ── CLI Mode ────────────────────────────────────────────

if (require.main === module) {
    const eventFile = process.argv[2];
    if (eventFile && fs.existsSync(eventFile)) {
        try {
            const event = JSON.parse(fs.readFileSync(eventFile, 'utf-8'));
            const result = recordUsage(event);
            if (result.warning) console.log(result.warning);
        } catch (e) {
            console.error(`Failed to parse event file: ${e.message}`);
        }
    }
    report();
}

// ── Exports ─────────────────────────────────────────────
module.exports = { recordUsage, report, loadBudget, RATES };
