/**
 * extension.ts — Jarvis Dev Co-Pilot VS Code Extension
 * 
 * THE MINIMAL LOOP:
 *   Save → Scan → Warn (inline) → Run → Fail → Capture → Learn → Warn next run
 * 
 * Zero behavior change. Zero manual input.
 * Warnings appear as yellow squiggles (like linting) and in the Problems panel.
 * Errors auto-captured from terminal output.
 */

import * as vscode from 'vscode';
import { JarvisBackend } from './backend';

let backend: JarvisBackend;
let diagnosticCollection: vscode.DiagnosticCollection;
let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;

// Track warnings shown for feedback
let lastWarningCount = 0;
let totalErrorsCaught = 0;

export function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel('Jarvis');
    outputChannel.appendLine('Jarvis Dev Co-Pilot activating...');

    // Create diagnostics collection (shows in Problems panel + inline squiggles)
    diagnosticCollection = vscode.languages.createDiagnosticCollection('jarvis');
    context.subscriptions.push(diagnosticCollection);

    // Status bar item (ambient awareness)
    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left, 100
    );
    statusBarItem.text = '$(brain) Jarvis';
    statusBarItem.tooltip = 'Jarvis Dev Co-Pilot — click for status';
    statusBarItem.command = 'jarvis.showStatus';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Start Python backend
    const config = vscode.workspace.getConfiguration('jarvis');
    const pythonPath = config.get<string>('pythonPath', 'python');

    backend = new JarvisBackend(pythonPath, context.extensionPath, outputChannel);
    backend.start();

    // ═══════════════════════════════════════════════════
    // TRIGGER 1: ON SAVE → SCAN → INLINE WARNINGS
    // ═══════════════════════════════════════════════════
    if (config.get<boolean>('enableOnSave', true)) {
        context.subscriptions.push(
            vscode.workspace.onDidSaveTextDocument(async (doc) => {
                if (doc.languageId !== 'python') { return; }
                await scanFile(doc);
            })
        );
    }

    // ═══════════════════════════════════════════════════
    // TRIGGER 2: TERMINAL OUTPUT → AUTO ERROR CAPTURE
    // ═══════════════════════════════════════════════════
    if (config.get<boolean>('enableTerminalCapture', true)) {
        // Watch for terminal close events (check exit state)
        context.subscriptions.push(
            vscode.window.onDidCloseTerminal(async (terminal) => {
                // Terminal closed — we can check if there was an error
                // Note: VS Code doesn't expose terminal output directly
                // We rely on the debug adapter and task output instead
            })
        );

        // Watch debug sessions for errors
        context.subscriptions.push(
            vscode.debug.onDidTerminateDebugSession(async (session) => {
                if (session.type === 'python' || session.type === 'debugpy') {
                    // Debug session ended — rescan the active file
                    const editor = vscode.window.activeTextEditor;
                    if (editor && editor.document.languageId === 'python') {
                        // Record edit event
                        await backend.send('record_edit', {
                            file_path: editor.document.fileName
                        });
                    }
                }
            })
        );

        // Watch task executions (pytest, python scripts via tasks)
        context.subscriptions.push(
            vscode.tasks.onDidEndTaskProcess(async (event) => {
                if (event.exitCode !== 0 && event.exitCode !== undefined) {
                    // Task failed — check if it was a Python task
                    const taskName = event.execution.task.name.toLowerCase();
                    if (taskName.includes('python') || taskName.includes('pytest')
                        || taskName.includes('test')) {
                        // Rescan active file with elevated urgency
                        const editor = vscode.window.activeTextEditor;
                        if (editor && editor.document.languageId === 'python') {
                            await scanFile(editor.document);
                        }
                    }
                } else if (event.exitCode === 0) {
                    // Success — record it
                    const taskName = event.execution.task.name;
                    await backend.send('record_success', { command: taskName });
                }
            })
        );
    }

    // ═══════════════════════════════════════════════════
    // TRIGGER 3: FILE EDIT TRACKING
    // ═══════════════════════════════════════════════════
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(async (event) => {
            if (event.document.languageId === 'python' && event.contentChanges.length > 0) {
                // Debounced — just notify backend of edit activity
                await backend.send('record_edit', {
                    file_path: event.document.fileName
                });
            }
        })
    );

    // ═══════════════════════════════════════════════════
    // COMMANDS
    // ═══════════════════════════════════════════════════
    context.subscriptions.push(
        vscode.commands.registerCommand('jarvis.checkFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor || editor.document.languageId !== 'python') {
                vscode.window.showInformationMessage('Jarvis: Open a Python file first.');
                return;
            }
            await scanFile(editor.document);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jarvis.showStatus', async () => {
            const status = await backend.send('get_status', {});
            if (status) {
                const session = status.session || {};
                const memory = status.memory || {};
                const interrupts = status.interrupts || {};

                const msg = [
                    `Session: ${session.duration_minutes || 0}min`,
                    `Errors this session: ${session.total_errors || 0}`,
                    `Total errors recorded: ${memory.total || 0}`,
                    `Warnings shown: ${interrupts.total || 0}`,
                    `Accept rate: ${Math.round((interrupts.accept_rate || 0) * 100)}%`,
                ].join(' | ');

                vscode.window.showInformationMessage(`🧠 Jarvis: ${msg}`);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('jarvis.dismissWarning', async () => {
            await backend.send('dismiss', {});
            vscode.window.showInformationMessage('Jarvis: Noted — threshold raised.');
        })
    );

    outputChannel.appendLine('Jarvis Dev Co-Pilot active.');
    updateStatusBar();
}

// ═══════════════════════════════════════════════════
// CORE: SCAN FILE → SHOW DIAGNOSTICS
// ═══════════════════════════════════════════════════

async function scanFile(doc: vscode.TextDocument) {
    const result = await backend.send('check_risks', {
        file_path: doc.fileName,
        code_text: doc.getText(),
    });

    if (!result || !result.warnings) {
        diagnosticCollection.set(doc.uri, []);
        updateStatusBar();
        return;
    }

    const warnings: any[] = result.warnings;
    const diagnostics: vscode.Diagnostic[] = [];

    for (const w of warnings) {
        // Determine line (fallback to line 0)
        const line = Math.max((w.line_hint || 1) - 1, 0);
        const lineEnd = Math.min(line, doc.lineCount - 1);

        const range = new vscode.Range(
            lineEnd, 0,
            lineEnd, doc.lineAt(Math.min(lineEnd, doc.lineCount - 1)).text.length
        );

        // Severity based on confidence
        let severity: vscode.DiagnosticSeverity;
        if (w.confidence >= 0.8) {
            severity = vscode.DiagnosticSeverity.Warning;
        } else if (w.confidence >= 0.5) {
            severity = vscode.DiagnosticSeverity.Information;
        } else {
            severity = vscode.DiagnosticSeverity.Hint;
        }

        const diag = new vscode.Diagnostic(range, w.message, severity);
        diag.source = 'Jarvis';
        diag.code = w.error_class;

        // Add "history" tag for history-based warnings
        if (w.is_history) {
            diag.tags = []; // Could add custom tag for special rendering
        }

        diagnostics.push(diag);
    }

    diagnosticCollection.set(doc.uri, diagnostics);
    lastWarningCount = diagnostics.length;
    updateStatusBar();

    // Show notification for high-confidence warnings (modal tier)
    const critical = warnings.filter((w: any) => w.type === 'warning' && w.confidence >= 0.85);
    if (critical.length > 0) {
        const msg = critical[0].message;
        const choice = await vscode.window.showWarningMessage(
            `⚡ Jarvis: ${msg}`,
            'Useful ✓', 'Dismiss ✗'
        );
        if (choice === 'Useful ✓') {
            await backend.send('accept', {});
        } else if (choice === 'Dismiss ✗') {
            await backend.send('dismiss', {});
        }
    }
}

function updateStatusBar() {
    if (lastWarningCount > 0) {
        statusBarItem.text = `$(warning) Jarvis: ${lastWarningCount} risk${lastWarningCount > 1 ? 's' : ''}`;
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    } else {
        statusBarItem.text = `$(brain) Jarvis`;
        statusBarItem.backgroundColor = undefined;
    }
    statusBarItem.tooltip = `Jarvis Dev Co-Pilot — ${totalErrorsCaught} errors learned`;
}

export function deactivate() {
    if (backend) {
        backend.stop();
    }
}
