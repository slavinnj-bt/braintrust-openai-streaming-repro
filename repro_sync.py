"""
Sync streaming repro for Braintrust wrap_openai issue.
Uses synchronous OpenAI client — may succeed or fail differently than async path.
"""

import os
from openai import OpenAI
from braintrust import init_logger, wrap_openai

init_logger(project="streaming-repro")

client = wrap_openai(
    OpenAI(api_key=os.environ["OPENAI_API_KEY"])
)

print("=== SYNC STREAMING ===")
stream = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Count to 5."}],
    stream=True,
)
for chunk in stream:
    content = chunk.choices[0].delta.content or ""
    print(content, end="", flush=True)
print()
print("=== SYNC STREAMING COMPLETE ===")
