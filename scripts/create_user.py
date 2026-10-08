#!/usr/bin/env python3
"""Create a Cognito demo user. Passwords never appear in arguments or output."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import string
import sys
from pathlib import Path

from botocore.exceptions import ClientError

from aws_common import ROOT, assert_owned, describe_stack, load_deployment, outputs, session


def random_password():
    classes = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%&*+-=?"]
    chars = [secrets.choice(group) for group in classes]
    chars.extend(secrets.choice("".join(classes)) for _ in range(24))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Demo username, for example demo.architect.")
    parser.add_argument("--deployment", type=Path, default=ROOT / "deployment.json")
    parser.add_argument("--credentials-file", type=Path, help="Generate a strong password and save it to a new mode-0600 JSON file. Use an ignored artifacts/ path.")
    parser.add_argument("--reset-existing", action="store_true", help="Explicitly permit resetting an existing demo user's password.")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", args.username):
        raise ValueError("Username must be 3–64 letters, digits, dots, underscores or hyphens.")
    if args.credentials_file and args.credentials_file.exists():
        raise RuntimeError("Credentials file already exists; choose a new ignored path to avoid overwriting a password.")
    deployment = load_deployment(args.deployment)
    aws = session(deployment["region"])
    account = aws.client("sts").get_caller_identity()["Account"]
    if account != deployment["accountId"]:
        raise RuntimeError("The AWS account does not match deployment metadata.")
    stack = describe_stack(aws.client("cloudformation"), f"{deployment['projectName']}-demo")
    if not stack:
        raise RuntimeError("The demo stack is missing.")
    assert_owned(stack, deployment["projectName"])
    result = outputs(stack)
    pool = result["UserPoolId"]
    cognito = aws.client("cognito-idp")
    exists = False
    try:
        cognito.admin_get_user(UserPoolId=pool, Username=args.username)
        exists = True
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "UserNotFoundException":
            raise
    if exists and not args.reset_existing:
        raise RuntimeError("The demo user already exists. Use --reset-existing only if you intend to replace that user's password.")
    password = random_password() if args.credentials_file else getpass.getpass("Demo password (at least 14 characters; upper/lowercase, number and symbol): ")
    if not args.credentials_file and password != getpass.getpass("Confirm password: "):
        raise ValueError("Passwords do not match.")
    if len(password) < 14 or not all(re.search(pattern, password) for pattern in [r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"]):
        raise ValueError("Password does not meet the demo's password policy.")
    if not exists:
        cognito.admin_create_user(UserPoolId=pool, Username=args.username, TemporaryPassword=password, MessageAction="SUPPRESS")
    cognito.admin_set_user_password(UserPoolId=pool, Username=args.username, Password=password, Permanent=True)
    if args.credentials_file:
        args.credentials_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.credentials_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump({"username": args.username, "password": password, "websiteUrl": result["WebsiteUrl"]}, handle, indent=2)
            handle.write("\n")
        print(f"Credentials saved privately to {args.credentials_file}; do not commit or share that file.")
    print(f"Demo user {args.username} is ready at {result['WebsiteUrl']}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"User creation failed: {exc}", file=sys.stderr)
        sys.exit(1)
