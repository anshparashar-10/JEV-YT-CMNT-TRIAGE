"""
Step 0 smoke test: prove the Jev endpoint is real and your key works.

Deliberately uses raw HTTP instead of the typesafe-sdk package, so this test
depends on nothing but the documented endpoint. If this passes, the endpoint
and your key are confirmed and we can adopt the SDK with confidence.

Run:  python smoke_test.py
Cost: about 0.01 rupees.
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TYPESAFE_API_KEY")
if not API_KEY:
    sys.exit("TYPESAFE_API_KEY not found. Create a .env file with: TYPESAFE_API_KEY=sk-...")

URL = "https://api.typesafe.ai/v1/systemone"

COMMENT = "wait does this work on windows too? great vid btw"

payload = {
    "model": "jev-1.13.0",
    "state": {"comment": COMMENT},
    "questions": {
        # Noul -> returns a bare 0-1 probability. NOTE: no confidence field.
        "is_question": {
            "type": "noul",
            "instructions": "The comment asks the video's creator a question that expects an answer.",
        },
        # Choice -> returns choice + confidence + probabilities.
        "tone": {
            "type": "choice",
            "instructions": "What is the overall tone of this comment?",
            "criteria": {
                "positive": {"what": "Friendly, appreciative, or enthusiastic."},
                "neutral": {"what": "Matter-of-fact, no clear feeling either way."},
                "negative": {"what": "Annoyed, critical, or hostile."},
            },
        },
    },
}

print(f"POST {URL}")
print(f"Comment: {COMMENT!r}\n")

try:
    r = httpx.post(
        URL,
        json=payload,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30.0,
    )
except httpx.RequestError as e:
    sys.exit(f"Could not reach the endpoint: {e}")

if r.status_code != 200:
    print(f"HTTP {r.status_code}")
    print(r.text)
    sys.exit(
        "\nIf this is 401, the key is wrong or not activated.\n"
        "If this is 404, the request shape is off - send me the body above."
    )

data = r.json()

print("--- RAW RESPONSE ---")
print(data)

print("\n--- READ BACK ---")
answers = data["answers"]
print(f"is_question (noul, 0-1): {answers['is_question']}")
print(f"tone (choice):           {answers['tone']}")

usage = data.get("usage", {})
tokens = usage.get("input_tokens")
print(f"\n--- COST ---")
print(f"usage: {usage}")
if tokens:
    inr = tokens / 1_000_000 * 0.042 * 96.58
    print(f"input_tokens: {tokens}  ->  about {inr:.4f} rupees for this one call")
    print(f"At this token count, 200 comments would cost roughly {inr * 200:.2f} rupees.")

print("\nEndpoint confirmed. Step 0 done.")
