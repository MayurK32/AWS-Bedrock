#!/usr/bin/env python3
"""Run Z.AI GLM 4.7 through Amazon Bedrock's Converse API.

Install in your activated virtual environment:
    python -m pip install --upgrade boto3 python-dotenv

Run:
    python bedrock_glm47.py
    python bedrock_glm47.py "Explain tool calling with a short example."
    python bedrock_glm47.py --region us-east-1 --profile my-profile

Credentials:
    Reads a .env file beside this script without overwriting existing
    environment variables. Otherwise uses boto3's normal AWS credential chain,
    including AWS CLI profiles. Never put access keys in this Python file.

    Recognized .env names:
        AWS_ACCESS_KEY_ID
        AWS_SECRET_ACCESS_KEY
        AWS_SESSION_TOKEN       (required only for temporary credentials)
        AWS_DEFAULT_REGION      (or AWS_REGION)
        AWS_PROFILE             (optional named AWS CLI profile)

    A working access key also needs permission to invoke this model.
    AWS currently lists GLM 4.7 as Legacy; account access may be limited.

Official model documentation:
    https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-zai-glm-4-7.html
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError
    from botocore.exceptions import NoCredentialsError, PartialCredentialsError
    from dotenv import load_dotenv
except ImportError:
    raise SystemExit(
        "Install dependencies first:\n"
        "python -m pip install --upgrade boto3 python-dotenv"
    )

MODEL_ID = "zai.glm-4.7"
DEFAULT_PROMPT = "Explain Amazon Bedrock in three short bullet points."


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
    parser.add_argument("--region", help="AWS region; overrides configured region")
    parser.add_argument("--profile", help="Optional named AWS CLI profile")
    parser.add_argument("--model-id", default=MODEL_ID, help="Bedrock model ID")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="Output token limit (default: 2048)")
    args = parser.parse_args()
    if not args.prompt.strip():
        parser.error("The prompt cannot be empty.")
    if not 1 <= args.max_tokens <= 128000:
        parser.error("--max-tokens must be between 1 and 128000 for GLM 4.7.")
    return args


def main():
    args = parse_args()
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)

    try:
        # boto3 reads your configured credentials. No keys are hardcoded.
        session = boto3.Session(profile_name=args.profile)
        region = (
            args.region
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or session.region_name
            or "us-east-1"
        )
        client = session.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(
                connect_timeout=10,
                read_timeout=180,
                retries={"mode": "standard", "total_max_attempts": 3},
            ),
        )

        print(f"Model: {args.model_id} | Region: {region}", flush=True)
        response = client.converse(
            modelId=args.model_id,
            messages=[{"role": "user", "content": [{"text": args.prompt}]}],
            inferenceConfig={"maxTokens": args.max_tokens},
        )

        # Reasoning and other non-text blocks are excluded from the final answer.
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        answer = "\n".join(
            block["text"] for block in blocks if block.get("text")
        ).strip()
        if answer:
            print(f"\n{answer}\n")
        else:
            print("\nNo final text was returned.", file=sys.stderr)

        usage = response.get("usage", {})
        print(
            f"Tokens - input: {usage.get('inputTokens', '?')}, "
            f"output: {usage.get('outputTokens', '?')}, "
            f"total: {usage.get('totalTokens', '?')}"
        )
        stop_reason = response.get("stopReason", "unknown")
        print(f"Stop reason: {stop_reason}")
        if stop_reason == "max_tokens":
            print(
                "Output limit reached. Try --max-tokens 4096. "
                "Reasoning can consume part of the output budget.",
                file=sys.stderr,
            )
        return 0 if answer else 1

    except (NoCredentialsError, PartialCredentialsError):
        print(
            "AWS credentials are missing or incomplete. Check your AWS CLI "
            "profile or the .env beside this script. Use AWS_ACCESS_KEY_ID "
            "and AWS_SECRET_ACCESS_KEY. Temporary credentials also require "
            "AWS_SESSION_TOKEN.",
            file=sys.stderr,
        )
    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        print(f"Bedrock error [{code}]: {error.get('Message', '')}", file=sys.stderr)
        if code == "AccessDeniedException":
            print(
                "Check IAM permission bedrock:InvokeModel and your account's "
                "model access. GLM 4.7 is listed as Legacy.",
                file=sys.stderr,
            )
        elif code in {"ValidationException", "ResourceNotFoundException"}:
            print(
                "Check the model ID and its regional availability. "
                "You can select a supported region with --region us-east-1.",
                file=sys.stderr,
            )
    except BotoCoreError as exc:
        print(f"AWS configuration or connection error: {exc}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

