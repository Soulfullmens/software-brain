# Phase P MVP — Recursive Agent Controller

Minimal proof of concept: recursive controller answers questions about the repo without loading everything into context.

## Structure

```
phase_p_mvp/
├── controller/
│   ├── controller.py   # Brain: delegates to workers, synthesizes answers
│   └── trace.py        # Forensic logging
├── index/
│   └── chunk_index.py  # Splits repo into bounded chunks
├── workers/
│   └── worker.py       # Dumb worker: reads one chunk, extracts facts
├── data/
│   ├── repo_chunks/    # Generated chunk files
│   └── traces/         # Execution traces
└── main.py             # Entry point
```

## Run

```bash
cd phase_p_mvp
python main.py
```

## Success Condition

- Controller produces answer without loading entire repo
- Trace file in `data/traces/trace.log` shows all decisions
- Answer is auditable
