/**
 * session_learn.js — Post-session hook that extracts successful
 * patterns from the session log to train future instincts.
 *
 * Usage:
 *   node src/agent/hooks/session_learn.js [session_log.json]
 *
 * Input:  A session log JSON file with steps, tools used, and outcomes.
 * Output: Appends learned patterns to agent_data/instincts.jsonl
 */

const fs = require('fs');
const path = require('path');

const DATA_DIR = process.env.AGENT_STORAGE_PATH || './agent_data';
const INSTINCTS_FILE = path.join(DATA_DIR, 'instincts.jsonl');
const LOG_FILE = process.argv[2] || path.join(DATA_DIR, 'last_session.json');

// ── Pattern Extraction ──────────────────────────────────

function extractPatterns(session) {
    const patterns = [];

    if (!session || !session.steps) {
        console.log('No steps found in session log.');
        return patterns;
    }

    // 1. Successful tool sequences
    const successfulSteps = session.steps.filter(s => s.status === 'success');
    if (successfulSteps.length > 0) {
        const toolSequence = successfulSteps.map(s => s.tool || s.action).filter(Boolean);
        if (toolSequence.length >= 2) {
            patterns.push({
                type: 'tool_sequence',
                pattern: toolSequence,
                context: session.goal || 'unknown',
                confidence: Math.min(successfulSteps.length / session.steps.length, 1.0),
                learned_at: new Date().toISOString(),
            });
        }
    }

    // 2. Error → Fix pairs (the most valuable instinct)
    for (let i = 0; i < session.steps.length - 1; i++) {
        const step = session.steps[i];
        const next = session.steps[i + 1];
        if (step.status === 'error' && next.status === 'success') {
            patterns.push({
                type: 'error_fix_pair',
                error_type: step.error_type || step.error || 'unknown',
                fix_action: next.tool || next.action || 'unknown',
                fix_detail: next.description || '',
                confidence: 0.85,
                learned_at: new Date().toISOString(),
            });
        }
    }

    // 3. Repeated successful strategies
    const toolCounts = {};
    successfulSteps.forEach(s => {
        const tool = s.tool || s.action;
        if (tool) toolCounts[tool] = (toolCounts[tool] || 0) + 1;
    });
    Object.entries(toolCounts)
        .filter(([, count]) => count >= 3)
        .forEach(([tool, count]) => {
            patterns.push({
                type: 'preferred_tool',
                tool: tool,
                usage_count: count,
                context: session.goal || 'unknown',
                confidence: Math.min(count / 10, 1.0),
                learned_at: new Date().toISOString(),
            });
        });

    return patterns;
}

// ── Main ────────────────────────────────────────────────

function main() {
    console.log('═══ SESSION LEARNER ═══');
    console.log(`Session log: ${LOG_FILE}`);
    console.log(`Instincts file: ${INSTINCTS_FILE}`);

    // Read session log
    if (!fs.existsSync(LOG_FILE)) {
        console.log('⚠ No session log found. Skipping.');
        return;
    }

    let session;
    try {
        session = JSON.parse(fs.readFileSync(LOG_FILE, 'utf-8'));
    } catch (e) {
        console.error(`✗ Failed to parse session log: ${e.message}`);
        return;
    }

    // Extract patterns
    const patterns = extractPatterns(session);
    console.log(`Extracted ${patterns.length} pattern(s).`);

    if (patterns.length === 0) {
        console.log('Nothing new to learn.');
        return;
    }

    // Append to instincts file
    const dir = path.dirname(INSTINCTS_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    const lines = patterns.map(p => JSON.stringify(p)).join('\n') + '\n';
    fs.appendFileSync(INSTINCTS_FILE, lines, 'utf-8');

    console.log(`✅ Learned ${patterns.length} instinct(s). Total file size: ${(fs.statSync(INSTINCTS_FILE).size / 1024).toFixed(1)} KB`);
}

main();
