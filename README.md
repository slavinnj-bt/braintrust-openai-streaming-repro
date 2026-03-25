# Braintrust Streaming Repro

Attempts to reproduce: `AttributeError: 'LegacyAPIResponse' object has no attribute '_iterator'`

Observed in production on Modal with `braintrust==0.10.0rc16` + `openai>=2.0.0` + sync `OpenAI` client + `stream=True`. **Neither the local nor Modal repro successfully reproduces the issue.** `braintrust==0.10.0rc16` appears to handle streaming correctly in both environments tested.

## Environment

- `openai>=2.0.0`
- `braintrust==0.10.0rc16` (from test PyPI)
- `httpx`
- Python 3.12
- Sync `OpenAI` client, no custom `http_client`

## Local repro

```bash
bash setup.sh
source .venv/bin/activate
export OPENAI_API_KEY=sk-...
export BRAINTRUST_API_KEY=...
python repro_sync.py
```

Note: this does not reproduce the issue in current testing — streaming completes successfully.

## Modal repro

Install the Modal CLI and authenticate:

```bash
pip install modal
modal setup
```

Create secrets:

```bash
modal secret create openai-secret OPENAI_API_KEY=sk-...
modal secret create braintrust-secret BRAINTRUST_API_KEY=...
```

Run:

```bash
modal run repro_modal.py
```

The Modal script tests two variants:
- **Variant A** — default httpx client (no explicit HTTP/2), matches customer's production code exactly
- **Variant B** — explicit `httpx.Client(http2=True)`, tests whether HTTP/2 negotiation is the trigger

Note: both variants completed successfully in testing — the issue did not reproduce on Modal either.

## Root cause hypothesis

Braintrust's `wrap_openai` uses `with_raw_response.create` internally. When the underlying httpx connection negotiates HTTP/2, the OpenAI SDK returns a `LegacyAPIResponse` object. Braintrust's wrapper calls `.parse()` on it, but `.parse()` on a streaming `LegacyAPIResponse` does not return a proper `Stream` object. The wrapper then tries to iterate the result, which internally accesses `._iterator` — an attribute that does not exist on `LegacyAPIResponse`:

```
AttributeError: 'LegacyAPIResponse' object has no attribute '_iterator'
```

The fix on Braintrust's side would be to preserve the full `Stream` interface when wrapping streamed responses rather than returning a bare generator.

## Workaround

The customer's immediate workaround is to not pass an httpx client with `http2=True` to the `OpenAI` constructor, avoiding the `LegacyAPIResponse` code path entirely.
