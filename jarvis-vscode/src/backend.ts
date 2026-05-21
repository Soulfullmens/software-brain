/**
 * backend.ts — Communication bridge to Jarvis Python backend.
 * 
 * Spawns `python jarvis_server.py` as a child process.
 * Talks via stdin/stdout JSON lines (one JSON object per line).
 * 
 * No HTTP. No WebSocket. No dependencies beyond Node.js built-ins.
 */

import * as vscode from 'vscode';
import { ChildProcess, spawn } from 'child_process';
import * as path from 'path';
import * as readline from 'readline';

interface PendingRequest {
    resolve: (value: any) => void;
    reject: (reason: any) => void;
    timeout: ReturnType<typeof setTimeout>;
}

export class JarvisBackend {
    private process: ChildProcess | null = null;
    private pythonPath: string;
    private serverPath: string;
    private outputChannel: vscode.OutputChannel;
    private pendingRequests: Map<number, PendingRequest> = new Map();
    private nextId = 1;
    private ready = false;
    private startPromise: Promise<void> | null = null;
    private lineReader: readline.Interface | null = null;

    // Debounce tracking for edit events
    private editDebounceTimer: ReturnType<typeof setTimeout> | null = null;

    constructor(
        pythonPath: string,
        extensionPath: string,
        outputChannel: vscode.OutputChannel
    ) {
        this.pythonPath = pythonPath;
        // jarvis_server.py is in the software-brain/jarvis_v2/ directory
        // Extension needs to find it relative to the workspace
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (workspaceFolders) {
            this.serverPath = path.join(
                workspaceFolders[0].uri.fsPath, 'jarvis_v2', 'jarvis_server.py'
            );
        } else {
            // Fallback: look relative to extension
            this.serverPath = path.join(extensionPath, '..', 'jarvis_v2', 'jarvis_server.py');
        }
        this.outputChannel = outputChannel;
    }

    start(): void {
        this.startPromise = this._startProcess();
    }

    private async _startProcess(): Promise<void> {
        try {
            this.outputChannel.appendLine(`Starting backend: ${this.pythonPath} ${this.serverPath}`);

            this.process = spawn(this.pythonPath, [this.serverPath], {
                stdio: ['pipe', 'pipe', 'pipe'],
                env: { ...process.env },
            });

            if (!this.process.stdout || !this.process.stdin) {
                this.outputChannel.appendLine('ERROR: Could not get process stdio');
                return;
            }

            // Read stdout line by line
            this.lineReader = readline.createInterface({
                input: this.process.stdout,
                crlfDelay: Infinity,
            });

            this.lineReader.on('line', (line: string) => {
                this._handleLine(line);
            });

            // Log stderr
            this.process.stderr?.on('data', (data: Buffer) => {
                this.outputChannel.appendLine(`[backend stderr] ${data.toString().trim()}`);
            });

            this.process.on('exit', (code: number | null) => {
                this.outputChannel.appendLine(`Backend exited with code ${code}`);
                this.ready = false;

                // Reject all pending requests
                for (const [id, pending] of this.pendingRequests) {
                    clearTimeout(pending.timeout);
                    pending.reject(new Error('Backend process exited'));
                }
                this.pendingRequests.clear();
            });

            this.process.on('error', (err: Error) => {
                this.outputChannel.appendLine(`Backend error: ${err.message}`);
                vscode.window.showWarningMessage(
                    `Jarvis: Could not start Python backend. Check that Python is installed.`
                );
            });

            // Wait for ready signal (max 5 seconds)
            await new Promise<void>((resolve) => {
                const readyTimeout = setTimeout(() => {
                    this.outputChannel.appendLine('Backend ready timeout — proceeding anyway');
                    this.ready = true;
                    resolve();
                }, 5000);

                const checkReady = () => {
                    if (this.ready) {
                        clearTimeout(readyTimeout);
                        resolve();
                    } else {
                        setTimeout(checkReady, 100);
                    }
                };
                checkReady();
            });

        } catch (err: any) {
            this.outputChannel.appendLine(`Failed to start backend: ${err.message}`);
        }
    }

    private _handleLine(line: string): void {
        try {
            const msg = JSON.parse(line);

            // Ready signal
            if (msg.type === 'ready') {
                this.outputChannel.appendLine(`Backend ready (v${msg.version})`);
                this.ready = true;
                return;
            }

            // Response to a request
            if (msg.id !== undefined && this.pendingRequests.has(msg.id)) {
                const pending = this.pendingRequests.get(msg.id)!;
                this.pendingRequests.delete(msg.id);
                clearTimeout(pending.timeout);

                if (msg.error) {
                    pending.reject(new Error(msg.error));
                } else {
                    pending.resolve(msg.result);
                }
            }
        } catch {
            this.outputChannel.appendLine(`[backend] unparseable: ${line.substring(0, 200)}`);
        }
    }

    /**
     * Send a request to the backend and wait for response.
     * 
     * @param method - RPC method name
     * @param params - Parameters object
     * @param timeoutMs - Timeout in milliseconds (default 5s)
     * @returns Response result, or null on error
     */
    async send(method: string, params: Record<string, any>, timeoutMs = 5000): Promise<any> {
        // Wait for startup
        if (this.startPromise) {
            await this.startPromise;
        }

        if (!this.process || !this.process.stdin || !this.ready) {
            this.outputChannel.appendLine(`Cannot send ${method} — backend not ready`);
            return null;
        }

        // Debounce edit events (don't flood backend)
        if (method === 'record_edit') {
            if (this.editDebounceTimer) {
                clearTimeout(this.editDebounceTimer);
            }
            return new Promise((resolve) => {
                this.editDebounceTimer = setTimeout(async () => {
                    const result = await this._sendImmediate(method, params, timeoutMs);
                    resolve(result);
                }, 500); // 500ms debounce
            });
        }

        return this._sendImmediate(method, params, timeoutMs);
    }

    private async _sendImmediate(
        method: string,
        params: Record<string, any>,
        timeoutMs: number
    ): Promise<any> {
        const id = this.nextId++;
        const request = JSON.stringify({ id, method, params }) + '\n';

        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                this.pendingRequests.delete(id);
                this.outputChannel.appendLine(`Timeout on ${method} (${timeoutMs}ms)`);
                resolve(null); // Don't reject — just return null on timeout
            }, timeoutMs);

            this.pendingRequests.set(id, { resolve, reject, timeout });

            try {
                this.process!.stdin!.write(request);
            } catch (err: any) {
                this.pendingRequests.delete(id);
                clearTimeout(timeout);
                this.outputChannel.appendLine(`Write error on ${method}: ${err.message}`);
                resolve(null);
            }
        });
    }

    stop(): void {
        if (this.lineReader) {
            this.lineReader.close();
        }
        if (this.process) {
            this.process.kill();
            this.process = null;
        }
        this.ready = false;
    }
}
