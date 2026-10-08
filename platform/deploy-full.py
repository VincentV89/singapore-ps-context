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
EXPECTED_STACKS = {f"sgsupport-demo-{suffix}" for suffix in [
    "network", "auth", "guardrail", "storage", "authnz", "vkg", "namespace",
    "metric-service", "api", "serve", "sources", "data-layer", "edge-waf",
    "web", "ontology", "mcp",
]}


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
        state["assemblyRepairs"] = previous.get("assemblyRepairs", [])
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
    recovery = None
    repair = None
    if args.phase == "deploy":
        candidates = [item for item in state.get("builds", [])
                      if item.get("phase") == "build" and item.get("artifactS3Uri") == args.assembly]
        if not candidates:
            repaired = [item for item in state.get("assemblyRepairs", [])
                        if item.get("artifactS3Uri") == args.assembly]
            if not repaired:
                raise ValueError("Assembly is not recorded as this project's build output or verified narrow repair")
            repair = verify_name_repair(aws, state, repaired[-1])
        else:
            previous = get_build(aws, candidates[-1]["id"])
            if previous["buildStatus"] != "SUCCEEDED":
                if not args.recover_diagnostics_only:
                    raise ValueError("Assembly deployment requires a successful build; diagnostic-only recovery requires --recover-diagnostics-only")
                recovery = recover_diagnostics(aws, previous, args.assembly, args.assembly_file)
                receipt = json.loads(Path(recovery["receipt"]).read_text())
                with ZipFile(receipt["inspectedFile"]) as archive:
                    historical_storage = json.loads(archive.read("cdk.out/sgsupport-demo-storage.template.json"))
                guard_neptune_capacity(aws, historical_storage)
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
    if recovery:
        build["diagnosticRecovery"] = recovery
    if repair:
        build["assemblyRepair"] = repair
    state.setdefault("builds", []).append(build)
    save(args.metadata, state)
    emit(build)


def verify_name_repair(aws, state, recorded):
    """Accept only a published receipt from the fixed three-name repair tool."""
    prefix = f"s3://{state['bucket']}/builds/aoss-name-repair-"
    digest = recorded.get("sha256", "")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Invalid repaired assembly content hash")
    if recorded.get("artifactS3Uri") != prefix + digest + ".zip" or recorded.get("receiptS3Uri") != prefix + digest + ".receipt.json":
        raise ValueError("Recorded repair URI is outside the scoped content-addressed namespace")
    s3 = aws.client("s3")
    key = f"builds/aoss-name-repair-{digest}"
    head = s3.head_object(Bucket=state["bucket"], Key=key + ".zip")
    receipt = json.loads(s3.get_object(Bucket=state["bucket"], Key=key + ".receipt.json")["Body"].read())
    expected_changed = {"cdk.out/manifest.json"}
    for name in ["storage", "sources", "metric-service"]:
        expected_changed.update({f"cdk.out/sgsupport-demo-{name}.template.json", f"cdk.out/sgsupport-demo-{name}.assets.json"})
    if (receipt.get("repairKind") != "aoss-three-name-limit"
        or receipt.get("account") != ACCOUNT or receipt.get("region") != REGION
        or receipt.get("projectName") != PROJECT
        or receipt.get("derivedArtifactS3Uri") != recorded["artifactS3Uri"]
        or receipt.get("derivedAssemblySha256") != digest
        or head.get("Metadata", {}).get("sha256") != digest
        or head["ContentLength"] != receipt.get("derivedAssemblyBytes")
        or head["ContentLength"] != recorded.get("bytes")
        or set(receipt.get("stackNames", [])) != EXPECTED_STACKS
        or set(receipt.get("changedZipEntries", [])) != expected_changed
        or receipt.get("unchangedApplicationAssets") is not True):
        raise ValueError("Published repair receipt or artifact does not match the narrow allowlist")
    original = get_build(aws, recorded["originalBuildId"])
    phases = {p["phaseType"]: p.get("phaseStatus") for p in original["phases"]}
    if (original["buildStatus"] != "FAILED"
        or {n for n, v in phases.items() if v == "FAILED"} != {"POST_BUILD"}
        or any(phases.get(n) != "SUCCEEDED" for n in ["INSTALL", "BUILD", "UPLOAD_ARTIFACTS"])):
        raise ValueError("Original asset publication proof is invalid")
    storage = [item for item in receipt.get("templateRepairs", [])
               if item.get("stack") == "sgsupport-demo-storage"]
    if len(storage) != 1:
        raise ValueError("Repair receipt must identify one storage template")
    storage = storage[0]
    template_hash = storage.get("newSha256", "")
    template_bucket = f"cdk-hnb659fds-assets-{ACCOUNT}-{REGION}"
    if (len(template_hash) != 64 or any(c not in "0123456789abcdef" for c in template_hash)
        or storage.get("objectKey") != template_hash + ".json"
        or receipt.get("publishedTemplateBucket") != template_bucket):
        raise ValueError("Historical storage template is outside the authorized bootstrap namespace")
    template_bytes = s3.get_object(Bucket=template_bucket, Key=storage["objectKey"])["Body"].read()
    if hashlib.sha256(template_bytes).hexdigest() != template_hash:
        raise ValueError("Historical storage template does not match its repair receipt")
    guard_neptune_capacity(aws, json.loads(template_bytes))
    return {"repairKind": receipt["repairKind"], "receiptS3Uri": recorded["receiptS3Uri"],
            "originalBuildId": original["id"], "originalBuildStatus": "FAILED",
            "derivedAssemblySha256": digest, "changedTemplateCount": 3}


def guard_neptune_capacity(aws, historical_storage):
    """Prevent only historical medium assemblies from undoing the owned resize."""
    resource = historical_storage.get("Resources", {}).get("NeptunePrimaryInstance", {})
    props = resource.get("Properties", {})
    if props.get("DBInstanceClass") != "db.t4g.medium":
        return
    identifier = "sgsupport-demo-neptune-primary"
    if resource.get("Type") != "AWS::Neptune::DBInstance" or props.get("DBInstanceIdentifier") != identifier:
        raise ValueError("Historical Neptune resource does not match this project's primary")
    from botocore.exceptions import ClientError
    try:
        instance = aws.client("neptune").describe_db_instances(DBInstanceIdentifier=identifier)["DBInstances"][0]
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"DBInstanceNotFound", "DBInstanceNotFoundFault"}:
            return
        raise
    if instance["DBInstanceClass"] != "db.r8g.large":
        return
    owned_instance = aws.client("cloudformation").describe_stack_resource(
        StackName="sgsupport-demo-storage", LogicalResourceId="NeptunePrimaryInstance",
    )["StackResourceDetail"]
    if owned_instance.get("PhysicalResourceId") != identifier:
        raise ValueError("Cannot verify ownership of the Neptune primary for historical assembly replay")
    raise ValueError(
        "Refusing historical db.t4g.medium assembly: the owned Neptune primary is already "
        "db.r8g.large after medium-instance graph memory failures. Run package, prepare and "
        "start --phase build with the current db.r8g.large build settings, then deploy that new assembly."
    )


def inspect_assembly_archive(path):
    """Validate stack boundaries and every ZIP entry without extracting code."""
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Assembly ZIP contains duplicate paths")
        for item in archive.infolist():
            relative = Path(item.filename)
            if relative.is_absolute() or ".." in relative.parts or "\\" in item.filename:
                raise ValueError("Unsafe assembly ZIP path")
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Assembly ZIP contains a symbolic link")
        manifest = json.loads(archive.read("cdk.out/manifest.json"))
        stacks = {
            value.get("properties", {}).get("stackName", artifact_id): value
            for artifact_id, value in manifest.get("artifacts", {}).items()
            if value.get("type") == "aws:cloudformation:stack"
        }
        if set(stacks) != EXPECTED_STACKS:
            raise ValueError("Assembly must contain exactly the 16 expected Singapore platform stacks")
        for value in stacks.values():
            template = value["properties"]["templateFile"]
            if "cdk.out/" + template not in names:
                raise ValueError("Assembly is missing a stack template")
            if value.get("environment") not in {
                "aws://unknown-account/unknown-region", f"aws://{ACCOUNT}/{REGION}",
            }:
                raise ValueError("Assembly targets an unauthorized account or region")
        asset_manifests = []
        files = set()
        images = set()
        for name in names:
            if name.startswith("cdk.out/") and name.endswith(".assets.json") and name.count("/") == 1:
                data = json.loads(archive.read(name))
                asset_manifests.append(name)
                files.update(data.get("files", {}))
                images.update(data.get("dockerImages", {}))
        if not asset_manifests or not files or not images:
            raise ValueError("Assembly is missing its published asset manifests")
    return {"stackNames": sorted(stacks), "assetManifests": sorted(asset_manifests),
            "uniqueFileAssetCount": len(files), "uniqueDockerAssetCount": len(images)}


def recover_diagnostics(aws, build, uri, assembly_file):
    """Recover an intact build whose sole failure is the known summary bug."""
    phases = {phase["phaseType"]: phase.get("phaseStatus") for phase in build["phases"]}
    failures = {name for name, status in phases.items() if status == "FAILED"}
    if build["buildStatus"] != "FAILED" or failures != {"POST_BUILD"}:
        raise ValueError("Recovery is restricted to a POST_BUILD-only failed build")
    if any(phases.get(name) != "SUCCEEDED" for name in ["INSTALL", "BUILD", "UPLOAD_ARTIFACTS"]):
        raise ValueError("Install, asset build/publication, and artifact upload must all have succeeded")
    logs = build.get("logs", {})
    events = aws.client("logs").filter_log_events(
        logGroupName=logs["groupName"], logStreamNames=[logs["streamName"]],
        filterPattern='"KeyError"', limit=100,
    )["events"]
    proof = next((event for event in events if event["message"].strip() == "KeyError: 'stackName'"), None)
    if proof is None:
        raise ValueError("Exact known stackName diagnostic exception was not found in this build's CloudWatch log")
    bucket, key = uri.removeprefix("s3://").split("/", 1)
    if build.get("artifacts", {}).get("location") != f"arn:aws:s3:::{bucket}/{key}":
        raise ValueError("Assembly URI does not match the original build's actual S3 artifact")
    s3 = aws.client("s3")
    remote = s3.head_object(Bucket=bucket, Key=key)
    if assembly_file is None:
        assembly_file = ROOT / "artifacts" / f"recovery-{build['id'].split(':')[-1]}.zip"
        assembly_file.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, key, str(assembly_file))
        assembly_file.chmod(0o600)
    if not assembly_file.is_file() or assembly_file.stat().st_size != remote["ContentLength"]:
        raise ValueError("Local assembly file does not match the original artifact size")
    validated = inspect_assembly_archive(assembly_file)
    receipt = {
        "diagnosticsOnlyRecovery": True, "originalBuildId": build["id"],
        "originalBuildStatus": build["buildStatus"], "phaseStates": phases,
        "cloudWatchError": "KeyError: 'stackName'", "cloudWatchEventId": proof["eventId"],
        "artifactS3Uri": uri, "artifactETag": remote["ETag"],
        "artifactBytes": remote["ContentLength"],
        "inspectedFile": str(assembly_file.resolve()),
        "inspectedFileSha256": hashlib.sha256(assembly_file.read_bytes()).hexdigest(),
        "validatedAt": stamp(), **validated,
        "publicationProof": "BUILD phase succeeded after checked publication of every CDK asset manifest",
    }
    receipt_path = ROOT / "artifacts" / f"diagnostic-recovery-{build['id'].split(':')[-1]}.local.json"
    save(receipt_path, receipt)
    emit({"diagnosticRecoveryValidated": True, "originalBuildStatus": "FAILED",
          "stackCount": len(validated["stackNames"]), "receipt": str(receipt_path)})
    return {"receipt": str(receipt_path), "originalBuildId": build["id"],
            "originalBuildStatus": "FAILED", "diagnosticsOnlyRecovery": True,
            "inspectedFileSha256": receipt["inspectedFileSha256"]}


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
    run.add_argument("--recover-diagnostics-only", action="store_true",
                     help="Recover only the verified post-build stackName summary failure; preserve its FAILED evidence")
    run.add_argument("--assembly-file", type=Path,
                     help="Already downloaded original assembly ZIP for diagnostic recovery; size and manifest are validated")
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
