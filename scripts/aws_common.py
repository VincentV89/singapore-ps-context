"""Shared deployment helpers. Never print credentials or token-bearing responses."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, ProfileNotFound

ROOT = Path(__file__).resolve().parents[1]
DEMO_TAG = {"Key": "Demo", "Value": "synthetic-citizen-services"}


def session(region: str):
    if region != "us-east-1":
        raise ValueError("This compact demo is configured for us-east-1.")
    try:
        return boto3.Session(region_name=region)
    except ProfileNotFound as exc:
        raise RuntimeError(
            "Selected AWS profile is missing. If your intended identity is supplied "
            "through environment access keys, run this command with env -u AWS_PROFILE. "
            "Keep the supplied proxy and credential variables unchanged."
        ) from exc


def project_name(value: str):
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,31}", value):
        raise ValueError("Project name must be 3–32 lowercase letters, digits or hyphens.")
    return value


def load_deployment(path: Path):
    data = json.loads(path.read_text())
    if data.get("region") != "us-east-1" or not data.get("projectName"):
        raise ValueError("Invalid deployment metadata.")
    project_name(data["projectName"])
    return data


def describe_stack(cf, name):
    try:
        return cf.describe_stacks(StackName=name)["Stacks"][0]
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ValidationError" and "does not exist" in str(exc):
            return None
        raise


def assert_owned(stack, project):
    tags = {tag["Key"]: tag["Value"] for tag in stack.get("Tags", [])}
    if tags.get("Project") != project or tags.get("Demo") != DEMO_TAG["Value"]:
        raise RuntimeError(f"Refusing to modify stack {stack['StackName']}: demo ownership tags do not match.")


def outputs(stack):
    return {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])}


def wait_stack(cf, name, deleting=False, timeout_seconds=3600, since=None):
    seen = set()
    since = since or datetime.now(timezone.utc) - timedelta(seconds=2)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        stack = describe_stack(cf, name)
        if stack is None:
            if deleting:
                return None
            raise RuntimeError(f"Stack {name} disappeared during deployment.")
        page = cf.describe_stack_events(StackName=name)
        for event in reversed(page.get("StackEvents", [])):
            if event["EventId"] not in seen and event["Timestamp"] >= since:
                seen.add(event["EventId"])
                reason = event.get("ResourceStatusReason", "")[:400]
                print(f"  {event['LogicalResourceId']}: {event['ResourceStatus']} {reason}", flush=True)
        status = stack["StackStatus"]
        if status in {"CREATE_COMPLETE", "UPDATE_COMPLETE"} and not deleting:
            return stack
        if status == "DELETE_COMPLETE" and deleting:
            return None
        if not status.endswith("_IN_PROGRESS"):
            raise RuntimeError(f"Stack {name} finished with {status}. Review the resource events above.")
        time.sleep(5)
    raise TimeoutError(f"Timed out waiting for {name}; the AWS operation may still be running.")


def apply_stack(cf, name, template_path, parameters, project):
    template = template_path.read_text()
    cf.validate_template(TemplateBody=template)
    existing = describe_stack(cf, name)
    kwargs = {
        "StackName": name,
        "TemplateBody": template,
        "Parameters": [{"ParameterKey": k, "ParameterValue": str(v)} for k, v in parameters.items()],
        "Capabilities": ["CAPABILITY_IAM"],
        "Tags": [{"Key": "Project", "Value": project}, DEMO_TAG],
    }
    if existing:
        assert_owned(existing, project)
        since = datetime.now(timezone.utc) - timedelta(seconds=2)
        try:
            cf.update_stack(**kwargs)
        except ClientError as exc:
            if "No updates are to be performed" in str(exc):
                print(f"{name}: no changes", flush=True)
                return existing
            raise
    else:
        since = datetime.now(timezone.utc) - timedelta(seconds=2)
        cf.create_stack(**kwargs)
    print(f"Waiting for {name}…", flush=True)
    return wait_stack(cf, name, since=since)
