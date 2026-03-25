# Braintrust Streaming Repro

## Braintrust tracing examples

Two example files illustrate the difference between `auto_instrument` alone vs. combined with `@traced` decorators.

### How `auto_instrument` works

`braintrust.auto_instrument()` patches the OpenAI client so every `chat.completions.create` call is automatically captured as a span. At the moment of each LLM call it reads the **currently active span** from a `ContextVar` and attaches the new span as a child. If no span is active, the call becomes its own root span.

### `auto_instrument_only.py` — flat traces

```bash
python auto_instrument_only.py
```

No `@traced` decorators anywhere. Every LLM call becomes an independent root span regardless of how deeply nested the calling functions are. The call stack has no effect on the trace hierarchy because nothing sets the `ContextVar`.

**Result:** N separate root spans, one per LLM call — no nesting.

### `auto_instrument_example.py` — nested traces

```bash
python auto_instrument_example.py
```

Each function is decorated with `@braintrust.traced`. When a decorated function runs it:
1. Creates a new span
2. Sets it as the active span in the `ContextVar`
3. Restores the previous active span on exit

Because `auto_instrument` reads that `ContextVar` at call time, every LLM call is automatically attached under whichever `@traced` function is currently on the stack.

**Result:** a fully nested trace tree, e.g.:

```
compare_weather                       (task)
├── research_location(San Francisco)  (task)
│   └── run_tool_loop                 (task)
│       ├── Chat Completion           (auto)
│       ├── get_weather               (tool)
│       ├── get_forecast              (tool)
│       ├── get_uv_index              (tool)
│       └── Chat Completion           (auto)
├── research_location(New York)       (task)
│   └── ...same structure...
└── Chat Completion                   (auto)
```

### Key takeaway

`auto_instrument` handles *capturing* LLM calls. `@traced` handles *context* — establishing a parent so captured calls know where to attach. Without at least one `@traced` ancestor on the call stack, all LLM calls surface as disconnected root spans.
