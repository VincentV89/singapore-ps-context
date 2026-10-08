#!/usr/bin/env python3
"""Package and run the full accelerator in project-owned AWS CodeBuild jobs.

The interactive machine never needs privileged Docker or ARM emulation.
`prepare` creates the build project and uploads a source bundle; `start --phase
build` publishes CDK assets without creating platform stacks. After prerequisites
are ready, `start --phase deploy --assembly <build-artifact-S3-URI>` deploys that
exact assembly without repeating the Docker builds. `status` is nonblocking.

Examples (boto3 is needed only by AWS subcommands):
  python platform/deploy-full.py package --source /workspace/context-ontology-accelerator
  python platform/deploy-full.py prepare
  python platform/deploy-full.py start --phase build
  python platform/deploy-full.py status --build-id <project:build-id>
  python platform/deploy-full.py start --phase deploy --assembly s3://<bucket>/builds/<artifact>.zip

Region and account are deliberately restricted to the authorized deployment.
The source bundle includes checked-in and nonignored new files, local patches,
and the buildspec. Credentials, generated files, caches, and local settings are
excluded. No environment values or Cognito passwords are printed or uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = Path(__file__).resolve().parent
ACCOUNT = "879594333699"
REGION = "us-east-1"
PROJECT = "sgsupport-full-platform"
STACK = "sgsupport-full-platform-build"
TAGS = {"Project": "sgsupport", "Purpose": "SingaporeContext"}
METADATA = ROOT / "artifacts" / "full-platform-build.local.json"
ARCHIVE = ROOT / "artifacts" / "full-platform-source.zip"
EXCLUDED_PARTS = {
    ".git", ".aws", ".venv", "node_modules", "__pycache__", ".gradle",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "cdk.out", "dist",
    "build", "smithy-generated", "platform-artifacts", "artifacts",
    "htmlcov", "coverage", "test-results", "playwright-report",
}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def emit(value):
    print(json.dumps(value, indent=2, default=str), flush=True)


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")
    path.chmod(0o600)


def package(source: Path, archive: Path):
    source = source.resolve()
    if not (source / ".git").exists():
        raise ValueError("Source must be the accelerator Git checkout")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if commit != "c84a3043a989c30fe33658c763f5f279c6981aba":
        raise ValueError("This build scaffold targets the pinned accelerator v0.3.4 commit")
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=source,
    ).decode().split("\0")
    archive.parent.mkdir(parents=True, exist_ok=True)
    included = []
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as output:
        for name in sorted(set(names)):
            if not name:
                continue
            relative = Path(name)
            if any(part in EXCLUDED_PARTS for part in relative.parts):
                continue
            lower = relative.name.lower()
            if lower == ".env" or lower.startswith(".env.") or lower.endswith(".local.json"):
                continue
            if lower in {"credentials", "config.local.json", "id_rsa", "id_ed25519"}:
                continue
            path = source / relative
            if not path.is_file():
                continue
            if not path.resolve().is_relative_to(source):
                raise ValueError(f"Source symlink escapes the checkout: {relative}")
            output.write(path, relative.as_posix())
            included.append(relative.as_posix())
        output.write(PLATFORM / "full-platform-build.yml", "platform/full-platform-build.yml")
        manifest = {
            "acceleratorRelease": "v0.3.4", "upstreamCommit": commit,
            "containsLocalPatches": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=source)),
            "packagedAt": stamp(), "sourceFileCount": len(included),
            "account": ACCOUNT, "region": REGION, "prefix": "sgsupport", "environment": "demo",
        }
        output.writestr("platform/source-manifest.json", json.dumps(manifest, indent=2) + "\n")
    archive.chmod(0o600)
    result = {
        **manifest, "archive": str(archive), "bytes": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    emit(result)
    return result


def aws_session():
    import boto3
    from botocore.exceptions import ProfileNotFound
    try:
        aws = boto3.Session(region_name=REGION)
    except ProfileNotFound as exc:
        raise RuntimeError("Configured AWS profile is missing; use env -u AWS_PROFILE when environment credentials are intended") from exc
    identity = aws.client("sts").get_caller_identity()
    if identity["Account"] != ACCOUNT:
        raise ValueError(f"Refusing account {identity['Account']}; expected authorized account {ACCOUNT}")
    return aws


def describe_stack(cf):
    from botocore.exceptions import ClientError
    try:
        return cf.describe_stacks(StackName=STACK)["Stacks"][0]
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ValidationError" and "does not exist" in str(exc):
            return None
        raise


def owned(stack):
    tags = {item["Key"]: item["Value"] for item in stack.get("Tags", [])}
    if any(tags.get(key) != value for key, value in TAGS.items()):
        raise ValueError("Existing build stack does not have this project's ownership tags")


def prepare(args):
    from botocore.exceptions import ClientError
    if not args.archive.is_file():
        raise ValueError("Run package before prepare")
    aws = aws_session()
    cf = aws.client("cloudformation")
    template = (PLATFORM / "build-project.json").read_text()
    cf.validate_template(TemplateBody=template)
    existing = describe_stack(cf)
    parameters = [{"ParameterKey": "ProjectName", "ParameterValue": PROJECT}]
    options = {
        "StackName": STACK, "TemplateBody": template, "Parameters": parameters,
        "Capabilities": ["CAPABILITY_NAMED_IAM"],
        "Tags": [{"Key": key, "Value": value} for key, value in TAGS.items()],
    }
    if existing:
        owned(existing)
        try:
            cf.update_stack(**options)
        except ClientError as exc:
            if "No updates are to be performed" not in str(exc):
                raise
    else:
        cf.create_stack(**options)
    deadline = time.monotonic() + 1200
    last = None
    while time.monotonic() < deadline:
        stack = describe_stack(cf)
        if stack is None:
            raise RuntimeError("Build stack disappeared")
        status = stack["StackStatus"]
        if status != last:
            emit({"stack": STACK, "status": status})
            last = status
        if status in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
            break
        if not status.endswith("_IN_PROGRESS"):
            raise RuntimeError(f"Build stack finished in {status}; inspect its resource events")
        time.sleep(5)
    else:
        raise TimeoutError("Build stack may still be provisioning")
    owned(stack)
    outputs = {item["OutputKey"]: item["OutputValue"] for item in stack["Outputs"]}
    checksum = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    key = f"sources/{checksum}.zip"
    aws.client("s3").upload_file(str(args.archive), outputs["BuildBucket"], key,
                                 ExtraArgs={"ServerSideEncryption": "AES256"})
    state = {
        "account": ACCOUNT, "region": REGION, "stackName": STACK,
        "projectName": outputs["BuildProjectName"], "bucket": outputs["BuildBucket"],
        "sourceKey": key, "sourceSha256": checksum,
        "logGroup": outputs["LogGroupName"], "preparedAt": stamp(), "builds": [],
    }
    if args.metadata.exists():
        previous = load_state(args.metadata)
        state["builds"] = previous.get("builds", [])
    save(args.metadata, state)
    emit({**state, "metadata": str(args.metadata)})


def load_state(path):
    data = json.loads(path.read_text())
    if data.get("account") != ACCOUNT or data.get("region") != REGION or data.get("projectName") != PROJECT:
        raise ValueError("Invalid build metadata")
    expected_bucket = f"{PROJECT}-build-{ACCOUNT}-{REGION}"
    if data.get("bucket") != expected_bucket or not data.get("sourceKey", "").startswith("sources/"):
        raise ValueError("Build source ownership does not match this project")
    return data


def start(args):
    state = load_state(args.metadata)
    if args.phase == "deploy" and not args.assembly:
        raise ValueError("Deploy requires --assembly from a completed build")
    if args.assembly and not args.assembly.startswith(f"s3://{state['bucket']}/builds/"):
        raise ValueError("Assembly must be an artifact from this project's build bucket")
    aws = aws_session()
    if args.phase == "deploy":
        candidates = [item for item in state.get("builds", [])
                      if item.get("phase") == "build" and item.get("artifactS3Uri") == args.assembly]
        if not candidates:
            raise ValueError("Assembly is not recorded as this project's build output")
        previous = get_build(aws, candidates[-1]["id"])
        if previous["buildStatus"] != "SUCCEEDED":
            raise ValueError("Assembly deployment requires a successfully completed build")
    token = uuid.uuid4().hex
    artifact_name = f"{args.phase}-{token}.zip"
    result = aws.client("codebuild").start_build(
        projectName=state["projectName"],
        sourceTypeOverride="S3", sourceLocationOverride=f"{state['bucket']}/{state['sourceKey']}",
        environmentVariablesOverride=[
            {"name": "SGSUPPORT_PHASE", "value": args.phase, "type": "PLAINTEXT"},
            {"name": "SGSUPPORT_ASSEMBLY_S3_URI", "value": args.assembly or "", "type": "PLAINTEXT"},
        ],
        artifactsOverride={
            "type": "S3", "location": state["bucket"], "path": "builds", "namespaceType": "NONE",
            "name": artifact_name, "packaging": "ZIP", "encryptionDisabled": False,
        },
    )["build"]
    build = {"id": result["id"], "phase": args.phase, "startedAt": stamp(),
             "artifactS3Uri": f"s3://{state['bucket']}/builds/{artifact_name}"}
    state.setdefault("builds", []).append(build)
    save(args.metadata, state)
    emit(build)


def get_build(aws, build_id):
    if not build_id.startswith(PROJECT + ":"):
        raise ValueError("Build ID does not belong to this project")
    data = aws.client("codebuild").batch_get_builds(ids=[build_id])
    if len(data.get("builds", [])) != 1:
        raise ValueError("Build was not found")
    return data["builds"][0]


def status(args):
    build = get_build(aws_session(), args.build_id)
    emit({
        "id": build["id"], "status": build["buildStatus"], "currentPhase": build.get("currentPhase"),
        "startTime": build.get("startTime"), "endTime": build.get("endTime"),
        "artifactLocation": build.get("artifacts", {}).get("location"),
        "logs": {key: build.get("logs", {}).get(key) for key in ["groupName", "streamName", "deepLink"]},
        "phases": [{"type": phase["phaseType"], "status": phase.get("phaseStatus"),
                    "contexts": phase.get("contexts", [])} for phase in build.get("phases", [])],
    })


def download(args):
    aws = aws_session()
    build = get_build(aws, args.build_id)
    location = build.get("artifacts", {}).get("location", "")
    if not location.startswith("arn:aws:s3:::"):
        raise ValueError("No S3 artifact has been reported for this build yet")
    bucket, key = location.removeprefix("arn:aws:s3:::").split("/", 1)
    if bucket != f"{PROJECT}-build-{ACCOUNT}-{REGION}" or not key.startswith("builds/"):
        raise ValueError("Build artifact is outside this project's bucket")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    aws.client("s3").download_file(bucket, key, str(args.output))
    args.output.chmod(0o600)
    emit({"artifact": str(args.output), "bytes": args.output.stat().st_size,
          "s3Uri": f"s3://{bucket}/{key}", "buildStatus": build["buildStatus"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("package", help="Create a credential-free source ZIP locally")
    pack.add_argument("--source", type=Path, default=Path("/workspace/context-ontology-accelerator"))
    pack.add_argument("--output", type=Path, default=ARCHIVE)
    prep = commands.add_parser("prepare", help="Create/update the owned build stack and upload the source ZIP")
    prep.add_argument("--archive", type=Path, default=ARCHIVE)
    prep.add_argument("--metadata", type=Path, default=METADATA)
    run = commands.add_parser("start", help="Start a nonblocking build or assembly deployment")
    run.add_argument("--phase", choices=["build", "deploy"], required=True)
    run.add_argument("--assembly")
    run.add_argument("--metadata", type=Path, default=METADATA)
    poll = commands.add_parser("status", help="Read build status and scoped log/artifact locations")
    poll.add_argument("--build-id", required=True)
    fetch = commands.add_parser("download", help="Download the project's reported build artifact")
    fetch.add_argument("--build-id", required=True)
    fetch.add_argument("--output", type=Path, default=ROOT / "artifacts" / "full-platform-assembly.zip")
    args = parser.parse_args()
    if args.command == "package":
        package(args.source, args.output)
    else:
        {"prepare": prepare, "start": start, "status": status, "download": download}[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
