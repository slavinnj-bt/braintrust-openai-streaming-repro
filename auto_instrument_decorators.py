import json
import braintrust
import openai

braintrust.auto_instrument()
braintrust.init_logger(project="braintrust-streaming-repro")

client = openai.OpenAI()

# ---------------------------------------------------------------------------
# Mock tools (leaf nodes — deepest level)
# ---------------------------------------------------------------------------

@braintrust.traced(type="tool")
def get_weather(location: str) -> str:
    return json.dumps({"location": location, "temperature": "72°F", "condition": "sunny"})


@braintrust.traced(type="tool")
def get_forecast(location: str, days: int) -> str:
    forecast = [
        {"day": i + 1, "high": f"{65 + i}°F", "condition": "partly cloudy"}
        for i in range(days)
    ]
    return json.dumps({"location": location, "forecast": forecast})


@braintrust.traced(type="tool")
def get_uv_index(location: str) -> str:
    return json.dumps({"location": location, "uv_index": 6, "risk": "high"})


# ---------------------------------------------------------------------------
# Mid-level helpers — each wraps one or more tool calls
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": "Get a multi-day forecast for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "days": {"type": "integer", "description": "Number of days (1-7)"},
                },
                "required": ["location", "days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_uv_index",
            "description": "Get the current UV index for a city.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    },
]

TOOL_DISPATCH = {
    "get_weather": get_weather,
    "get_forecast": get_forecast,
    "get_uv_index": get_uv_index,
}


@braintrust.traced(type="task")
def run_tool_loop(messages: list) -> str:
    """Run an agentic loop until the model stops calling tools."""
    while True:
        response = client.chat.completions.create(
            model="gpt-4o-mini", messages=messages, tools=TOOLS
        )
        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            return msg.content

        for tool_call in msg.tool_calls:
            fn = TOOL_DISPATCH[tool_call.function.name]
            result = fn(**json.loads(tool_call.function.arguments))
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })


@braintrust.traced(type="task")
def research_location(location: str) -> str:
    """Gather all weather data for a location, then synthesize a summary."""
    messages = [
        {
            "role": "system",
            "content": "You are a weather analyst. Use the available tools to gather "
                       "current conditions, a 3-day forecast, and UV index for the location, "
                       "then provide a comprehensive summary.",
        },
        {"role": "user", "content": f"Research the weather for {location}."},
    ]
    return run_tool_loop(messages)


# ---------------------------------------------------------------------------
# Top-level task — compares two locations
# ---------------------------------------------------------------------------

@braintrust.traced(type="task")
def compare_weather(location_a: str, location_b: str) -> str:
    """
    Research two locations independently, then ask the model to compare them.

    Trace tree:
    compare_weather                      (task)
    ├── research_location(location_a)    (task)
    │   └── run_tool_loop                (task)
    │       ├── Chat Completion          (auto)
    │       ├── get_weather              (tool)
    │       ├── get_forecast             (tool)
    │       ├── get_uv_index             (tool)
    │       └── Chat Completion          (auto)
    ├── research_location(location_b)    (task)
    │   └── ...same structure...
    └── Chat Completion                  (auto — final comparison)
    """
    summary_a = research_location(location_a)
    summary_b = research_location(location_b)

    comparison = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Compare the weather in two cities concisely."},
            {
                "role": "user",
                "content": (
                    f"{location_a}: {summary_a}\n\n"
                    f"{location_b}: {summary_b}\n\n"
                    "Which city has better weather today, and why?"
                ),
            },
        ],
    )
    return comparison.choices[0].message.content


if __name__ == "__main__":
    result = compare_weather("San Francisco", "New York")
    print(result)
