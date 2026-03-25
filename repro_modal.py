"""
Modal deployment repro for Braintrust wrap_openai + openai 2.x streaming issue.

Environment matches customer:
  - openai>=2.0.0
  - braintrust==0.10.0rc16
  - ddtrace==2.21.1 with OpenAI + httpx auto-patching (matches customer's Datadog setup)
  - httpx (no explicit http2)
  - sync OpenAI client, no custom http_client
  - python 3.12

Simulates a multi-turn conversation with nested Braintrust spans, matching the
complexity of a real production trace.

No Datadog account needed — ddtrace patches libraries regardless of whether
traces are exported anywhere.

Run with:
  modal run repro_modal.py
"""

import modal

app = modal.App("braintrust-streaming-repro")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .dockerfile_commands([
        "COPY --from=datadog/serverless-init /datadog-init /app/datadog-init",
        'ENTRYPOINT ["/app/datadog-init"]',
    ])
    .pip_install("openai==2.29.0", "httpx", "ddtrace==2.21.1")
    .run_commands(
        "pip install --extra-index-url https://test.pypi.org/simple/ braintrust==0.10.0rc16"
    )
)


def stream_response(client, messages):
    """Stream a single turn, accumulate and return the full response text."""
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )
    content = ""
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            delta = chunk.choices[0].delta.content
            content += delta
            print(delta, end="", flush=True)
    print()
    return content


def run_variant(label, client):
    """
    Run a multi-turn conversation under a nested Braintrust trace.

    Trace structure:
      conversation            <- outer span (start_span)
        turn_1                <- child span
          openai.request      <- auto-traced by wrap_openai
        turn_2                <- child span
          openai.request
        turn_3                <- child span
          openai.request
    """
    import braintrust

    print(f"\n=== {label} ===")
    try:
        with braintrust.start_span(name="conversation", type="task") as conv_span:
            messages = [{"role": "system", "content": "You are a helpful assistant. Be brief."}]

            # Turn 1
            with conv_span.start_span(name="turn_1", type="llm"):
                messages.append({"role": "user", "content": "Name three planets."})
                reply = stream_response(client, messages)
                messages.append({"role": "assistant", "content": reply})

            # Turn 2 — follow-up referencing turn 1
            with conv_span.start_span(name="turn_2", type="llm"):
                messages.append({"role": "user", "content": "Which of those is largest?"})
                reply = stream_response(client, messages)
                messages.append({"role": "assistant", "content": reply})

            # Turn 3 — follow-up referencing turn 2
            with conv_span.start_span(name="turn_3", type="llm"):
                messages.append({"role": "user", "content": "How many Earths fit inside it?"})
                reply = stream_response(client, messages)
                messages.append({"role": "assistant", "content": reply})

        print(f"=== {label}: OK ===")
    except Exception as e:
        print(f"=== {label}: FAILED: {e} ===")


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("openai-secret"),       # must contain OPENAI_API_KEY
        modal.Secret.from_name("braintrust-secret"),   # must contain BRAINTRUST_API_KEY
    ],
)
def run_repro():
    import os
    import ddtrace

    # Patch before importing openai/braintrust to match customer's datadog-init
    # entrypoint behavior, which instruments libraries before any app code runs
    ddtrace.patch(openai=True, httpx=True)

    from openai import OpenAI
    from braintrust import init_logger, wrap_openai
    import openai
    from importlib.metadata import version as pkg_version
    print(f"openai=={openai.__version__}")
    print(f"braintrust=={pkg_version('braintrust')}")

    # Confirm LegacyAPIResponse exists — its presence indicates openai 1.x is active
    try:
        from openai._legacy_response import LegacyAPIResponse
        print("WARNING: LegacyAPIResponse found — openai 1.x is active despite pinning 2.x")
    except ImportError:
        print("OK: LegacyAPIResponse not present (openai 2.x confirmed)")

    init_logger(project="streaming-repro-modal", api_key=os.environ["BRAINTRUST_API_KEY"])

    # Variant A: default httpx client (matches customer's utils.py exactly)
    client_a = wrap_openai(OpenAI(api_key=os.environ["OPENAI_API_KEY"]))
    run_variant("VARIANT A: default httpx", client_a)

    # Variant B: explicit httpx client with http2=True
    import httpx
    http_client = httpx.Client(
        http2=True,
        timeout=30.0,
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=30.0,
        ),
    )
    client_b = wrap_openai(OpenAI(api_key=os.environ["OPENAI_API_KEY"], http_client=http_client))
    run_variant("VARIANT B: httpx http2=True", client_b)

    # Variant C: call with_raw_response.create directly without .parse(), matching
    # the usage pattern from https://github.com/openai/openai-python/issues/1115
    print("\n=== VARIANT C: with_raw_response without .parse() ===")
    client_c = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    try:
        stream = client_c.chat.completions.with_raw_response.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Count to 3."}],
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print("\n=== VARIANT C: OK ===")
    except Exception as e:
        import traceback
        print(f"\n=== VARIANT C: FAILED: {e} ===")
        traceback.print_exc()

    # Variant D: same as C but with wrap_openai — isolates whether braintrust's
    # wrapping is what triggers the LegacyAPIResponse error
    print("\n=== VARIANT D: with_raw_response without .parse() + wrap_openai ===")
    client_d = wrap_openai(OpenAI(api_key=os.environ["OPENAI_API_KEY"]))
    try:
        stream = client_d.chat.completions.with_raw_response.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Count to 3."}],
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print("\n=== VARIANT D: OK ===")
    except Exception as e:
        import traceback
        print(f"\n=== VARIANT D: FAILED: {e} ===")
        traceback.print_exc()


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("openai-secret"),
        modal.Secret.from_name("braintrust-secret"),
    ],
)
def run_repro_no_ddtrace():
    """Same as run_repro but without ddtrace patching — isolates whether ddtrace
    is what causes with_raw_response to return LegacyAPIResponse instead of Stream."""
    import os
    from openai import OpenAI
    from braintrust import init_logger, wrap_openai
    import openai
    from importlib.metadata import version as pkg_version

    print(f"openai=={openai.__version__}")
    print(f"braintrust=={pkg_version('braintrust')}")
    print("ddtrace: NOT patched")

    init_logger(project="streaming-repro-modal", api_key=os.environ["BRAINTRUST_API_KEY"])

    # Variant C (no ddtrace): with_raw_response without .parse(), no wrap_openai
    print("\n=== VARIANT C (no ddtrace): with_raw_response without .parse() ===")
    client_c = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    try:
        stream = client_c.chat.completions.with_raw_response.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Count to 3."}],
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print("\n=== VARIANT C (no ddtrace): OK ===")
    except Exception as e:
        import traceback
        print(f"\n=== VARIANT C (no ddtrace): FAILED: {e} ===")
        traceback.print_exc()

    # Variant D (no ddtrace): with_raw_response without .parse(), with wrap_openai
    print("\n=== VARIANT D (no ddtrace): with_raw_response without .parse() + wrap_openai ===")
    client_d = wrap_openai(OpenAI(api_key=os.environ["OPENAI_API_KEY"]))
    try:
        stream = client_d.chat.completions.with_raw_response.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Count to 3."}],
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print("\n=== VARIANT D (no ddtrace): OK ===")
    except Exception as e:
        import traceback
        print(f"\n=== VARIANT D (no ddtrace): FAILED: {e} ===")
        traceback.print_exc()


@app.local_entrypoint()
def main():
    run_repro.remote()
    run_repro_no_ddtrace.remote()
