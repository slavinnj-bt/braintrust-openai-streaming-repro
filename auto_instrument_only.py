import json
import braintrust
import openai

braintrust.auto_instrument()
braintrust.init_logger(project="braintrust-streaming-repro")

client = openai.OpenAI()


def get_weather(location: str) -> str:
    return json.dumps({"location": location, "temperature": "72°F", "condition": "sunny"})


def get_forecast(location: str, days: int) -> str:
    forecast = [
        {"day": i + 1, "high": f"{65 + i}°F", "condition": "partly cloudy"}
        for i in range(days)
    ]
    return json.dumps({"location": location, "forecast": forecast})


def get_uv_index(location: str) -> str:
    return json.dumps({"location": location, "uv_index": 6, "risk": "high"})


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
                    "days": {"type": "integer"},
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


def run_tool_loop(messages: list) -> str:
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


def research_location(location: str) -> str:
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


def compare_weather(location_a: str, location_b: str) -> str:
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
