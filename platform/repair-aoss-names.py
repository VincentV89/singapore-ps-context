#!/usr/bin/env python3
"""Repair only three overlong AOSS names in a verified, published CDK assembly.

This changes no Docker image or application asset and never starts deployment.
Use --publish to upload the three changed content-addressed templates and the
derived assembly to this project's private bucket. Original failed build
evidence and both assembly hashes are retained in a separate receipt.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deploy_full", Path(__file__).with_name("deploy-full.py"))
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
REPAIRS = {
    "sgsupport-demo-storage": {
        "old": "sgsupport-demo-vector-store-group", "new": "sgsupport-demo-vector-group",
        "paths": [("VectorStoreGroup", "Name"), ("VectorStore", "CollectionGroupName")],
    },
    "sgsupport-demo-sources": {
        "old": "sgsupport-demo-src-ingestion-access", "new": "sgsupport-demo-src-access",
        "paths": [("SourcesOSSDataAccessPolicy", "Name")],
    },
    "sgsupport-demo-metric-service": {
        "old": "sgsupport-demo-metric-data-access", "new": "sgsupport-demo-metric-access",
        "paths": [("OSSDataAccessPolicy", "Name")],
    },
}


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encoded(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def resolve_aws(value):
    return value.replace("${AWS::AccountId}", deploy.ACCOUNT).replace("${AWS::Region}", deploy.REGION).replace("${AWS::Partition}", "aws")


def check_destinations(archive):
    for name in archive.namelist():
        if not name.startswith("cdk.out/") or not name.endswith(".assets.json") or name.count("/") != 1:
            continue
        assets = json.loads(archive.read(name))
        for kind in ("files", "dockerImages"):
            for asset in assets.get(kind, {}).values():
                for target in asset.get("destinations", {}).values():
                    role = resolve_aws(target.get("assumeRoleArn", ""))
                    if not role.startswith(f"arn:aws:iam::{deploy.ACCOUNT}:role/cdk-hnb659fds-") or not role.endswith(f"-{deploy.REGION}"):
                        raise ValueError("Asset publishing role is outside the authorized bootstrap namespace")
                    if "bucketName" in target and resolve_aws(target["bucketName"]) != f"cdk-hnb659fds-assets-{deploy.ACCOUNT}-{deploy.REGION}":
                        raise ValueError("File asset bucket is outside the authorized bootstrap namespace")
                    if "repositoryName" in target and resolve_aws(target["repositoryName"]) != f"cdk-hnb659fds-container-assets-{deploy.ACCOUNT}-{deploy.REGION}":
                        raise ValueError("Docker repository is outside the authorized bootstrap namespace")


def repair(source, output):
    validated = deploy.inspect_assembly_archive(source)
    if source.resolve() == output.resolve():
        raise ValueError("Derived assembly must not overwrite original evidence")
    changes = {}
    templates = []
    with ZipFile(source) as archive:
        check_destinations(archive)
        manifest = json.loads(archive.read("cdk.out/manifest.json"))
        for stack, rule in REPAIRS.items():
            if not re.fullmatch(r"[a-z][a-z0-9-]{2,31}", rule["new"]):
                raise ValueError("Repaired AOSS name is invalid")
            props = manifest["artifacts"][stack]["properties"]
            template_name = "cdk.out/" + props["templateFile"]
            original = archive.read(template_name)
            before = json.loads(original)
            after = copy.deepcopy(before)
            for resource, prop in rule["paths"]:
                if after["Resources"][resource]["Properties"][prop] != rule["old"]:
                    raise ValueError("Original assembly does not match the narrow AOSS repair")
                after["Resources"][resource]["Properties"][prop] = rule["new"]
            if original.count(rule["old"].encode()) != len(rule["paths"]):
                raise ValueError("Unexpected additional occurrences of an AOSS name")
            repaired = original.replace(rule["old"].encode(), rule["new"].encode())
            if json.loads(repaired) != after:
                raise ValueError("Repair changes properties outside its allowlist")
            old_hash = hashlib.sha256(original).hexdigest()
            new_hash = hashlib.sha256(repaired).hexdigest()
            asset_name = f"cdk.out/{stack}.assets.json"
            assets = json.loads(archive.read(asset_name))
            entry = assets["files"].pop(old_hash)
            if entry["source"] != {"path": props["templateFile"], "packaging": "file"}:
                raise ValueError("Unexpected template asset source")
            for target in entry["destinations"].values():
                if target["objectKey"] != old_hash + ".json":
                    raise ValueError("Original template asset key does not match its content")
                target["objectKey"] = new_hash + ".json"
            assets["files"][new_hash] = entry
            old_url = f"s3://cdk-hnb659fds-assets-${{AWS::AccountId}}-${{AWS::Region}}/{old_hash}.json"
            if props["stackTemplateAssetObjectUrl"] != old_url:
                raise ValueError("Original template URL does not match its content")
            props["stackTemplateAssetObjectUrl"] = old_url.replace(old_hash, new_hash)
            changes[template_name] = repaired
            changes[asset_name] = encoded(assets)
            templates.append({"stack": stack, "template": template_name,
                              "oldName": rule["old"], "newName": rule["new"],
                              "oldSha256": old_hash, "newSha256": new_hash,
                              "objectKey": new_hash + ".json",
                              "changedProperties": [f"{r}.{p}" for r, p in rule["paths"]]})
        changes["cdk.out/manifest.json"] = encoded(manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w", allowZip64=True) as derived:
            for info in archive.infolist():
                if info.filename in changes:
                    derived.writestr(info, changes[info.filename])
                else:
                    with archive.open(info) as incoming, derived.open(info, "w") as outgoing:
                        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        output.chmod(0o600)
    result = deploy.inspect_assembly_archive(output)
    if result != validated:
        raise ValueError("Repair changed stack or application asset membership")
    with ZipFile(source) as original, ZipFile(output) as derived:
        check_destinations(derived)
        if original.namelist() != derived.namelist():
            raise ValueError("Repair changed ZIP entry membership")
        for entry in original.infolist():
            other = derived.getinfo(entry.filename)
            if entry.filename not in changes and (entry.CRC, entry.file_size) != (other.CRC, other.file_size):
                raise ValueError("An unrelated assembly entry changed")
    return {"repairKind": "aoss-three-name-limit", "account": deploy.ACCOUNT,
            "region": deploy.REGION, "projectName": deploy.PROJECT,
            "createdAt": deploy.stamp(), "originalAssembly": str(source.resolve()),
            "originalAssemblySha256": sha_file(source), "derivedAssembly": str(output.resolve()),
            "derivedAssemblySha256": sha_file(output), "derivedAssemblyBytes": output.stat().st_size,
            "changedZipEntries": sorted(changes), "templateRepairs": templates,
            "unchangedApplicationAssets": True, **result}, changes


def publish(args, receipt, changes):
    import boto3
    aws = deploy.aws_session()
    state = deploy.load_state(args.metadata)
    original_build = deploy.get_build(aws, args.original_build_id)
    recovery = deploy.recover_diagnostics(aws, original_build, args.original_uri, args.input)
    receipt.update({"originalBuildId": original_build["id"],
                    "originalBuildStatus": original_build["buildStatus"],
                    "originalArtifactS3Uri": args.original_uri,
                    "diagnosticRecovery": recovery})
    role = f"arn:aws:iam::{deploy.ACCOUNT}:role/cdk-hnb659fds-file-publishing-role-{deploy.ACCOUNT}-{deploy.REGION}"
    credentials = aws.client("sts").assume_role(RoleArn=role, RoleSessionName="sgsupport-assembly-name-repair")["Credentials"]
    publisher = boto3.Session(region_name=deploy.REGION, aws_access_key_id=credentials["AccessKeyId"],
                              aws_secret_access_key=credentials["SecretAccessKey"],
                              aws_session_token=credentials["SessionToken"]).client("s3")
    bootstrap_bucket = f"cdk-hnb659fds-assets-{deploy.ACCOUNT}-{deploy.REGION}"
    for template in receipt["templateRepairs"]:
        body = changes[template["template"]]
        publisher.put_object(Bucket=bootstrap_bucket, Key=template["objectKey"], Body=body,
                             ContentType="application/json", Metadata={"sha256": template["newSha256"]})
        uploaded = publisher.get_object(Bucket=bootstrap_bucket, Key=template["objectKey"])["Body"].read()
        if hashlib.sha256(uploaded).hexdigest() != template["newSha256"]:
            raise ValueError("Published template hash verification failed")
    digest = receipt["derivedAssemblySha256"]
    key = f"builds/aoss-name-repair-{digest}.zip"
    receipt["derivedArtifactS3Uri"] = f"s3://{state['bucket']}/{key}"
    receipt["publishedTemplateBucket"] = bootstrap_bucket
    receipt["receiptS3Uri"] = f"s3://{state['bucket']}/builds/aoss-name-repair-{digest}.receipt.json"
    s3 = aws.client("s3")
    s3.upload_file(str(args.output), state["bucket"], key,
                   ExtraArgs={"ServerSideEncryption": "AES256", "Metadata": {"sha256": digest}})
    head = s3.head_object(Bucket=state["bucket"], Key=key)
    if head["ContentLength"] != receipt["derivedAssemblyBytes"] or head["Metadata"].get("sha256") != digest:
        raise ValueError("Derived artifact upload verification failed")
    receipt["derivedArtifactETag"] = head["ETag"]
    receipt_key = f"builds/aoss-name-repair-{digest}.receipt.json"
    s3.put_object(Bucket=state["bucket"], Key=receipt_key, Body=json.dumps(receipt, indent=2).encode(),
                  ServerSideEncryption="AES256", ContentType="application/json")
    state.setdefault("assemblyRepairs", []).append({
        "artifactS3Uri": receipt["derivedArtifactS3Uri"], "sha256": digest,
        "bytes": receipt["derivedAssemblyBytes"], "receiptS3Uri": receipt["receiptS3Uri"],
        "originalBuildId": original_build["id"], "repairKind": receipt["repairKind"],
    })
    deploy.save(args.metadata, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "artifacts/full-platform-assembly.zip")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/full-platform-assembly-aoss-fixed.zip")
    parser.add_argument("--receipt", type=Path, default=ROOT / "artifacts/full-platform-assembly-aoss-repair.local.json")
    parser.add_argument("--metadata", type=Path, default=deploy.METADATA)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--original-build-id")
    parser.add_argument("--original-uri")
    args = parser.parse_args()
    if args.publish and (not args.original_build_id or not args.original_uri):
        parser.error("--publish requires the original build ID and actual artifact URI")
    receipt, changes = repair(args.input, args.output)
    deploy.save(args.receipt, receipt)
    if args.publish:
        publish(args, receipt, changes)
        deploy.save(args.receipt, receipt)
    deploy.emit({"derivedAssembly": str(args.output), "receipt": str(args.receipt),
                 "stackCount": len(receipt["stackNames"]), "changedTemplateCount": 3,
                 "applicationAssetsChanged": False,
                 "derivedArtifactS3Uri": receipt.get("derivedArtifactS3Uri"),
                 "sha256": receipt["derivedAssemblySha256"]})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
