#!/usr/bin/env python3
"""Build and deploy this demo without CDK bootstrap. Requires boto3 and npm."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import subprocess
import sys
from pathlib import Path

from aws_common import ROOT, apply_stack, describe_stack, outputs, project_name, session


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="singapore-ps-context", type=project_name)
    parser.add_argument("--region", default="us-east-1", choices=["us-east-1"])
    parser.add_argument("--enable-bedrock", action="store_true", help="Grant Nova Lite inference and enable optional narration (usage is billable).")
    parser.add_argument("--bedrock-model-id", default="amazon.nova-lite-v1:0", choices=["amazon.nova-lite-v1:0"])
    parser.add_argument("--skip-build", action="store_true", help="Use existing frontend/dist and backend/package.zip.")
    parser.add_argument("--output", type=Path, default=ROOT / "deployment.json")
    return parser.parse_args()


def upload_frontend(s3, bucket, dist):
    if not (dist / "index.html").is_file():
        raise RuntimeError("frontend/dist/index.html is missing; build the frontend first.")
    count = 0
    for path in sorted(dist.rglob("*")):
        if not path.is_file():
            continue
        key = path.relative_to(dist).as_posix()
        # The source config.json is for local preview and must never be deployed.
        if key == "config.json":
            continue
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        if key.endswith(".js"):
            content_type = "application/javascript"
        cache_control = "public,max-age=31536000,immutable" if key.startswith("assets/") else "no-cache,max-age=0,must-revalidate"
        s3.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": content_type, "CacheControl": cache_control, "ServerSideEncryption": "AES256"})
        count += 1
    print(f"Uploaded {count} frontend files.", flush=True)


def main():
    args = parse_args()
    aws = session(args.region)
    account = aws.client("sts").get_caller_identity()["Account"]
    print(f"Deploying {args.project} to AWS account {account}, {args.region}.", flush=True)
    if not args.skip_build:
        subprocess.run(["bash", "backend/package_lambda.sh"], cwd=ROOT, check=True)
        subprocess.run(["npm", "ci"], cwd=ROOT / "frontend", check=True)
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)
    code = ROOT / "backend/package.zip"
    if not code.is_file():
        raise RuntimeError("backend/package.zip is missing; run bash backend/package_lambda.sh.")
    cf = aws.client("cloudformation")
    s3 = aws.client("s3")
    artifacts_name = f"{args.project}-artifacts"
    artifacts = apply_stack(cf, artifacts_name, ROOT / "infra/artifacts.json", {"ProjectName": args.project}, args.project)
    artifacts_bucket = outputs(artifacts)["ArtifactsBucket"]
    key = f"lambda/{hashlib.sha256(code.read_bytes()).hexdigest()}.zip"
    s3.upload_file(str(code), artifacts_bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
    main_name = f"{args.project}-demo"
    old = describe_stack(cf, main_name)
    origin = outputs(old).get("WebsiteUrl", "https://deployment.invalid") if old else "https://deployment.invalid"
    params = {
        "ProjectName": args.project,
        "LambdaCodeBucket": artifacts_bucket,
        "LambdaCodeKey": key,
        "FrontendOrigin": origin,
        "EnableBedrock": "true" if args.enable_bedrock else "false",
        "BedrockModelId": args.bedrock_model_id,
    }
    stack = apply_stack(cf, main_name, ROOT / "infra/main.json", params, args.project)
    result = outputs(stack)
    # First-pass CORS denies the real browser origin until this update completes.
    # A parameter prevents CF CSP -> API -> CORS -> CF dependency cycles.
    if params["FrontendOrigin"] != result["WebsiteUrl"]:
        params["FrontendOrigin"] = result["WebsiteUrl"]
        stack = apply_stack(cf, main_name, ROOT / "infra/main.json", params, args.project)
        result = outputs(stack)
    upload_frontend(s3, result["FrontendBucket"], ROOT / "frontend/dist")
    config = {
        "apiUrl": result["ApiUrl"], "region": args.region,
        "cognito": {"authority": result["CognitoAuthority"], "clientId": result["UserPoolClientId"], "domain": result["CognitoDomain"]},
        "localPreview": False,
    }
    s3.put_object(Bucket=result["FrontendBucket"], Key="config.json", Body=json.dumps(config).encode(), ContentType="application/json", CacheControl="no-store,max-age=0", ServerSideEncryption="AES256")
    invalidation = aws.client("cloudfront").create_invalidation(
        DistributionId=result["DistributionId"],
        InvalidationBatch={"Paths": {"Quantity": 1, "Items": ["/*"]}, "CallerReference": f"deploy-{__import__('uuid').uuid4()}"},
    )
    print(f"CloudFront invalidation {invalidation['Invalidation']['Id']} requested.", flush=True)
    metadata = {
        "projectName": args.project, "region": args.region, "accountId": account,
        "mainStack": main_name, "artifactsStack": artifacts_name,
        "artifactsBucket": artifacts_bucket, "enableBedrock": args.enable_bedrock,
        "outputs": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Deployment metadata saved to {args.output}. It contains no secrets.", flush=True)
    print(f"Demo URL: {result['WebsiteUrl']}", flush=True)
    print("Create a demo login with scripts/create_user.py. CloudFront invalidation may take a few minutes.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Deployment failed: {exc}", file=sys.stderr)
        sys.exit(1)
