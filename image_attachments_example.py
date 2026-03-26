"""
Demonstrates logging image attachments with Braintrust so they render
in the trace view. Each image gets its own @traced span containing:
  - input: the image as a braintrust.Attachment
  - output: the model's description of the image
"""

import base64
from pathlib import Path

import braintrust
from braintrust import Attachment
import openai

braintrust.auto_instrument()
braintrust.init_logger(project="braintrust-streaming-repro")

client = openai.OpenAI()

IMAGES_DIR = Path(__file__).parent / "images"


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


@braintrust.traced(type="task")
def describe_image(image_path: Path) -> str:
    """Send an image to the model and return its description."""
    b64 = _b64(image_path)
    content_type = "image/jpeg"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{b64}"},
                    },
                    {"type": "text", "text": "Describe this image in one sentence."},
                ],
            }
        ],
    )

    description = response.choices[0].message.content

    # Log the image as an Attachment so it renders in the trace view,
    # alongside the model's output.
    braintrust.current_span().log(
        input={
            "image": Attachment(
                data=str(image_path),
                filename=image_path.name,
                content_type=content_type,
            ),
            "prompt": "Describe this image in one sentence.",
        },
        output=description,
    )

    return description


@braintrust.traced(type="task")
def describe_all_images() -> dict:
    """Run describe_image for each file in the images directory."""
    results = {}
    for image_path in sorted(IMAGES_DIR.glob("*.jpeg")):
        results[image_path.name] = describe_image(image_path)
    return results


if __name__ == "__main__":
    results = describe_all_images()
    for name, description in results.items():
        print(f"{name}: {description}")
