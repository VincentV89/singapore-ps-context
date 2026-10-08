#!/usr/bin/env python3
"""Preview or remove only this project's tagged demo stacks and owned S3 buckets."""
from __future__ import annotations

import argparse
import sys

from aws_common import DEMO_TAG, assert_owned, describe_stack, project_name, session, wait_stack


def bucket_owned(s3, bucket, project):
    try:
        tags = {item["Key"]: item["Value"] for item in s3.get_bucket_tagging(Bucket=bucket)["TagSet"]}
    except s3.exceptions.NoSuchBucket:
        return False
    if tags.get("Project") != project or tags.get("Demo") != DEMO_TAG["Value"]:
        raise RuntimeError(f"Refusing to empty {bucket}: ownership tags do not match.")
    return True


def empty_bucket(s3, bucket, project):
    if not bucket_owned(s3, bucket, project):
        return
    # Versioned buckets need both object versions and deletion markers removed.
    # Pages are read from the start after each batch so deleted pagination keys
    # cannot skip objects during cleanup.
    while True:
        page = s3.list_object_versions(Bucket=bucket, MaxKeys=1000)
        items = [{"Key": item["Key"], "VersionId": item["VersionId"]} for category in ["Versions", "DeleteMarkers"] for item in page.get(category, [])]
        if not items:
            break
        result = s3.delete_objects(Bucket=bucket, Delete={"Objects": items, "Quiet": True})
        if result.get("Errors"):
            raise RuntimeError(f"Could not delete all versions in {bucket}; inspect S3 permissions.")
    print(f"Emptied owned bucket {bucket}.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=project_name, default="singapore-ps-context")
    parser.add_argument("--region", choices=["us-east-1"], default="us-east-1")
    parser.add_argument("--confirm", metavar="PROJECT_NAME", help="Actually delete the project. Must exactly equal --project.")
    args = parser.parse_args()
    if args.confirm and args.confirm != args.project:
        raise ValueError("--confirm must exactly match the project name.")
    aws = session(args.region)
    account = aws.client("sts").get_caller_identity()["Account"]
    cf, s3 = aws.client("cloudformation"), aws.client("s3")
    names = [f"{args.project}-demo", f"{args.project}-artifacts"]
    stacks = {name: describe_stack(cf, name) for name in names}
    buckets = {f"{args.project}-web-{account}-{args.region}", f"{args.project}-artifacts-{account}-{args.region}"}
    for name, stack in stacks.items():
        if stack:
            assert_owned(stack, args.project)
            for page in cf.get_paginator("list_stack_resources").paginate(StackName=name):
                for item in page["StackResourceSummaries"]:
                    if item["ResourceType"] == "AWS::S3::Bucket" and item.get("PhysicalResourceId") not in buckets:
                        raise RuntimeError("Stack contains an unexpected S3 bucket; refusing cleanup.")
    owned_buckets = [name for name in sorted(buckets) if bucket_owned(s3, name, args.project)]
    print(f"AWS account {account}: project {args.project}")
    print("Stacks: " + ", ".join(name for name, stack in stacks.items() if stack))
    print("Owned buckets, including retained artifacts: " + ", ".join(owned_buckets))
    if not args.confirm:
        print(f"Preview only. To remove these resources, run with --confirm {args.project}.")
        return
    for bucket in owned_buckets:
        empty_bucket(s3, bucket, args.project)
    for name in names:
        if stacks[name]:
            cf.delete_stack(StackName=name)
            print(f"Waiting for deletion of {name}…", flush=True)
            wait_stack(cf, name, deleting=True)
    # CloudFormation intentionally retains the artifact bucket; delete it only
    # after verifying its tags again. Never touch existing account resources.
    for bucket in owned_buckets:
        if bucket_owned(s3, bucket, args.project):
            empty_bucket(s3, bucket, args.project)
            s3.delete_bucket(Bucket=bucket)
            print(f"Deleted retained bucket {bucket}.", flush=True)
    print("Tagged demo resources removed. Local generated files remain on disk.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Cleanup failed: {exc}", file=sys.stderr)
        sys.exit(1)
