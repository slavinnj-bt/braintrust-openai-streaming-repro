"""
Modal deployment repro for Braintrust wrap_openai + openai 2.x streaming issue.

Environment matches customer:
  - openai>=2.0.0
  - braintrust==0.10.0rc16
  - httpx (no explicit http2)
  - sync OpenAI client, no custom http_client
  - python 3.12

Run with:
  modal run repro_modal.py
"""

import modal

app = modal.App("braintrust-streaming-repro")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("openai>=2.0.0", "httpx")
    .run_commands(
        "pip install --extra-index-url https://test.pypi.org/simple/ braintrust==0.10.0rc16"
    )
)


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("openai-secret"),       # must contain OPENAI_API_KEY
        modal.Secret.from_name("braintrust-secret"),   # must contain BRAINTRUST_API_KEY
    ],
)
def run_repro():
    import os
    from openai import OpenAI
    from braintrust import init_logger, wrap_openai

    init_logger(project="streaming-repro-modal", api_key=os.environ["BRAINTRUST_API_KEY"])

    # Variant A: no custom httpx client (matches customer's utils.py exactly)
    print("=== VARIANT A: default httpx client ===")
    client_a = wrap_openai(OpenAI(api_key=os.environ["OPENAI_API_KEY"]))
    try:
        stream = client_a.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Count to 3."}],
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print("\n=== VARIANT A: OK ===")
    except Exception as e:
        print(f"\n=== VARIANT A: FAILED: {e} ===")

    # Variant B: explicit httpx client with http2=True
    # (tests the h2 hypothesis — httpx.Client is defined in customer code even though commented out)
    import httpx
    print("\n=== VARIANT B: httpx http2=True ===")
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
    try:
        stream = client_b.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Count to 3."}],
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print("\n=== VARIANT B: OK ===")
    except Exception as e:
        print(f"\n=== VARIANT B: FAILED: {e} ===")


@app.local_entrypoint()
def main():
    run_repro.remote()
