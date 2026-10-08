#!/usr/bin/env python3
"""Bootstrap the full demo login, or publish its branded S3/CloudFront UI.

--bootstrap collects deployed full-platform outputs and creates/reuses a private
permanent Cognito administrator password. Invitations are always suppressed.
--collect-only reads deployment metadata without changing Cognito.
--publish requires completed source ingestion and an actually accepted ontology,
updates the existing navigator's CSP parameters, and publishes frontend/dist
with full Cognito/namespace settings. The upstream administrator console remains
available. Dependencies: boto3; publish also needs rdflib and pycognito.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import string
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

from botocore.exceptions import ClientError

from aws_common import ROOT, assert_owned, describe_stack, outputs, session, wait_stack

ACCOUNT = "879594333699"
REGION = "us-east-1"
PREFIX = "sgsupport"
ADMIN_EMAIL = "vincenoh@amazon.com"
WEBSITE = "https://d1pbdc1b2fpdk2.cloudfront.net"


def write_private(path, data, exclusive=False):
    path = path.resolve()
    if ROOT / "artifacts" not in path.parents:
        raise ValueError("Deployment artifacts and credentials must remain in the ignored artifacts/ directory.")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    os.chmod(path, 0o600)


def select_output(result, key, optional=False):
    if key in result:
        return result[key]
    matches = [value for name, value in result.items() if key.lower() in name.lower()]
    if len(matches) == 1:
        return matches[0]
    if optional and not matches:
        return None
    raise ValueError(f"Cannot resolve unique deployed output {key}.")


def require_full_stack(cf, component):
    name = f"{PREFIX}-demo-{component}"
    stack = describe_stack(cf, name)
    if not stack or stack["StackStatus"] not in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"}:
        raise RuntimeError(f"Full stack {name} has not completed deployment.")
    if not stack["StackId"].startswith(f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{name}/"):
        raise ValueError("Full stack account/region/name ownership does not match this task.")
    tags = {tag["Key"]: tag["Value"] for tag in stack.get("Tags", [])}
    if tags.get("Project") not in {"sgsupport", "SingaporeContext"} or tags.get("Environment") != "demo":
        raise ValueError(f"Full stack {name} lacks its expected demo ownership tags.")
    return stack


def require_original_deployment(aws, deployment_path):
    deployment = json.loads(deployment_path.read_text())
    if deployment.get("accountId") != ACCOUNT or deployment.get("region") != REGION or deployment.get("projectName") != "singapore-ps-context":
        raise ValueError("Existing navigator metadata does not identify the authorized deployment.")
    cf = aws.client("cloudformation")
    for key in ("mainStack", "artifactsStack"):
        stack = describe_stack(cf, deployment[key])
        if not stack:
            raise ValueError("Existing navigator stack is missing: " + deployment[key])
        assert_owned(stack, deployment["projectName"])
    main = describe_stack(cf, deployment["mainStack"])
    actual = outputs(main)
    if actual["WebsiteUrl"] != WEBSITE or any(actual[key] != deployment["outputs"][key] for key in ("FrontendBucket", "DistributionId", "WebsiteUrl")):
        raise ValueError("Existing navigator output identities changed; inspect before publishing.")
    bucket_tags = {t["Key"]: t["Value"] for t in aws.client("s3").get_bucket_tagging(Bucket=actual["FrontendBucket"], ExpectedBucketOwner=ACCOUNT)["TagSet"]}
    if bucket_tags.get("Project") != "singapore-ps-context":
        raise ValueError("Existing private frontend bucket lacks its project ownership tag.")
    artifact_bucket = deployment["artifactsBucket"]
    aws.client("s3").head_bucket(Bucket=artifact_bucket, ExpectedBucketOwner=ACCOUNT)
    artifact_tags = {t["Key"]: t["Value"] for t in aws.client("s3").get_bucket_tagging(Bucket=artifact_bucket, ExpectedBucketOwner=ACCOUNT)["TagSet"]}
    if artifact_tags.get("Project") != "singapore-ps-context":
        raise ValueError("Existing deployment artifact bucket lacks its project ownership tag.")
    return deployment, main, actual


def collect(aws, deployment_path, metadata_path):
    deployment, main, original = require_original_deployment(aws, deployment_path)
    cf = aws.client("cloudformation")
    auth = outputs(require_full_stack(cf, "auth"))
    api = outputs(require_full_stack(cf, "api"))
    serve = outputs(require_full_stack(cf, "serve"))
    web = outputs(require_full_stack(cf, "web"))
    pool, client_id = select_output(auth, "UserPoolId"), select_output(auth, "UserPoolClientId")
    api_url = select_output(api, "ApiEndpoint").rstrip("/")
    runtime = aws.client("ssm").get_parameter(Name="/sgsupport/serve/runtime-arn")["Parameter"]["Value"]
    if runtime != select_output(serve, "AgentRuntimeArn") or not runtime.startswith(f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/"):
        raise ValueError("Serve SSM ARN does not match the owned full deployment.")
    if not pool.startswith("us-east-1_") or urlparse(api_url).scheme != "https" or not (urlparse(api_url).hostname or "").endswith(".execute-api.us-east-1.amazonaws.com"):
        raise ValueError("Full authentication/API outputs have unexpected region or endpoint identities.")
    console_url = select_output(web, "WebsiteURL")
    if urlparse(console_url).scheme != "https":
        raise ValueError("Full administrator console URL is not HTTPS.")
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    metadata.update({"schemaVersion": 1, "region": REGION, "accountId": ACCOUNT, "prefix": PREFIX, "environment": "demo", "apiUrl": api_url, "serveRuntimeArn": runtime, "cognito": {"userPoolId": pool, "clientId": client_id, "authority": f"https://cognito-idp.{REGION}.amazonaws.com/{pool}", "domain": select_output(auth, "CognitoDomainUrl").rstrip("/"), "scope": "openid email profile"}, "websiteUrl": original["WebsiteUrl"], "frontendBucket": original["FrontendBucket"], "distributionId": original["DistributionId"], "adminConsoleUrl": console_url, "fullStackNames": {name: f"sgsupport-demo-{name}" for name in ("auth", "api", "serve", "web", "sources", "ontology")}, "originalMainStack": deployment["mainStack"]})
    write_private(metadata_path, metadata)
    print(f"Full-platform metadata saved to {metadata_path}.", flush=True)
    return metadata, main, original


def random_password():
    groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%&*+-=?"]
    chars = [secrets.choice(group) for group in groups]
    chars.extend(secrets.choice("".join(groups)) for _ in range(28))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def configure_hosted_ui_style(client, metadata):
    """Apply supported classic-hosted-UI colors only to the demo app client.

    The selectors are from Cognito's documented legacy CSS template:
    https://docs.aws.amazon.com/cognito/latest/developerguide/hosted-ui-classic-branding.html
    No logo/image, user-pool setting, managed-login version or other client
    configuration is changed by SetUICustomization.
    """
    pool = metadata["cognito"]["userPoolId"]
    client_id = metadata["cognito"]["clientId"]
    hostname = urlparse(metadata["cognito"]["domain"]).hostname or ""
    if not hostname.endswith(f".auth.{REGION}.amazoncognito.com"):
        raise ValueError("Expected the owned full-platform Cognito prefix domain.")
    domain = client.describe_user_pool_domain(Domain=hostname.split(".", 1)[0])["DomainDescription"]
    if domain.get("UserPoolId") != pool or domain.get("ManagedLoginVersion") != 1:
        raise ValueError("Singapore CSS requires this pool's existing classic hosted UI (version 1).")
    css = (ROOT / "platform" / "cognito-singapore.css").read_text().strip()
    current = client.get_ui_customization(UserPoolId=pool, ClientId=client_id)["UICustomization"].get("CSS", "")
    if current.strip() == css:
        print("Cognito hosted UI already uses the Singapore red and white palette.", flush=True)
        return False
    client.set_ui_customization(UserPoolId=pool, ClientId=client_id, CSS=css)
    print("Applied Singapore red and white colors to the existing Cognito hosted UI.", flush=True)
    return True


def configure_login(aws, metadata, credentials_path):
    client = aws.client("cognito-idp")
    pool = metadata["cognito"]["userPoolId"]
    client_id = metadata["cognito"]["clientId"]
    try:
        user = client.admin_get_user(UserPoolId=pool, Username=ADMIN_EMAIL)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "UserNotFoundException":
            raise
        user = client.admin_create_user(UserPoolId=pool, Username=ADMIN_EMAIL, MessageAction="SUPPRESS", UserAttributes=[{"Name": "email", "Value": ADMIN_EMAIL}, {"Name": "email_verified", "Value": "true"}])["User"]
    if credentials_path.exists():
        if credentials_path.stat().st_mode & 0o077:
            raise ValueError("Existing login file is not private (chmod 600).")
        credentials = json.loads(credentials_path.read_text())
        if credentials.get("username") != ADMIN_EMAIL or credentials.get("userPoolId") != pool or not credentials.get("password"):
            raise ValueError("Existing private login belongs to a different full user pool or administrator.")
        if user.get("UserStatus") == "FORCE_CHANGE_PASSWORD" and not credentials.get("setupComplete"):
            client.admin_set_user_password(UserPoolId=pool, Username=ADMIN_EMAIL, Password=credentials["password"], Permanent=True)
        print("Reusing the existing full-platform administrator login.", flush=True)
    else:
        credentials = {"username": ADMIN_EMAIL, "password": random_password(), "userPoolId": pool, "clientId": client_id, "region": REGION, "websiteUrl": WEBSITE, "setupComplete": False}
        # Persist first, so an interrupted API call cannot lose the generated
        # secret. The file remains ignored and has mode 0600 from creation.
        write_private(credentials_path, credentials, exclusive=True)
        client.admin_set_user_password(UserPoolId=pool, Username=ADMIN_EMAIL, Password=credentials["password"], Permanent=True)
    credentials["setupComplete"] = True
    credentials["clientId"] = client_id
    write_private(credentials_path, credentials)
    groups = client.admin_list_groups_for_user(UserPoolId=pool, Username=ADMIN_EMAIL).get("Groups", [])
    if not any(group["GroupName"] == "Admin" for group in groups):
        # This is the full deployment's configured initial-administrator group;
        # the upstream authorizer maps it to platform-admin.
        try:
            client.get_group(UserPoolId=pool, GroupName="Admin")
        except client.exceptions.ResourceNotFoundException:
            client.create_group(UserPoolId=pool, GroupName="Admin", Description="Initial administrator group for the Singapore context demo")
        client.admin_add_user_to_group(UserPoolId=pool, Username=ADMIN_EMAIL, GroupName="Admin")
    config = client.describe_user_pool_client(UserPoolId=pool, ClientId=client_id)["UserPoolClient"]
    callback, logout = WEBSITE + "/auth/callback", WEBSITE + "/"
    if callback not in config.get("CallbackURLs", []) or logout not in config.get("LogoutURLs", []):
        accepted = client.meta.service_model.operation_model("UpdateUserPoolClient").input_shape.members
        request = {key: value for key, value in config.items() if key in accepted}
        request["CallbackURLs"] = sorted(set(config.get("CallbackURLs", []) + [callback]))
        request["LogoutURLs"] = sorted(set(config.get("LogoutURLs", []) + [logout]))
        client.update_user_pool_client(**request)
    configure_hosted_ui_style(client, metadata)
    print(f"Administrator login saved privately to {credentials_path}; no invitation email was sent.", flush=True)


def update_csp(aws, metadata, stack):
    cf = aws.client("cloudformation")
    template = json.loads((ROOT / "infra" / "main.json").read_text())
    for key in ("FullPlatformApiOrigin", "FullPlatformCognitoOrigin"):
        if key not in template.get("Parameters", {}):
            raise ValueError("infra/main.json is missing required full-platform CSP parameters.")
    existing = cf.get_template(StackName=stack["StackName"])["TemplateBody"]
    if isinstance(existing, str):
        existing = json.loads(existing)
    if {k: v["Type"] for k, v in existing["Resources"].items()} != {k: v["Type"] for k, v in template["Resources"].items()}:
        raise ValueError("CSP update must preserve the existing navigator resource identities/types.")
    api = urlparse(metadata["apiUrl"])
    values = {"FullPlatformApiOrigin": f"{api.scheme}://{api.netloc}", "FullPlatformCognitoOrigin": metadata["cognito"]["domain"]}
    parameters = [{"ParameterKey": parameter["ParameterKey"], **({"ParameterValue": values[parameter["ParameterKey"]]} if parameter["ParameterKey"] in values else {"UsePreviousValue": True})} for parameter in stack.get("Parameters", [])]
    present = {parameter["ParameterKey"] for parameter in parameters}
    parameters.extend({"ParameterKey": key, "ParameterValue": value} for key, value in values.items() if key not in present)
    try:
        cf.update_stack(StackName=stack["StackName"], TemplateBody=json.dumps(template), Parameters=parameters, Capabilities=["CAPABILITY_NAMED_IAM"], Tags=stack.get("Tags", []))
    except ClientError as exc:
        if "No updates are to be performed" not in str(exc):
            raise
        print("Navigator CSP already includes the full platform origins.", flush=True)
        return
    print("Updating the existing navigator's CSP; all prior stack parameters are preserved.", flush=True)
    wait_stack(cf, stack["StackName"])


def decode_custom_resource_call(value):
    """Decode CDK's JSON-in-Fn::Join without resolving or losing references."""
    references = {}

    def marker(reference):
        token = f"__SGSUPPORT_CFN_TOKEN_{len(references)}__"
        references[token] = reference
        return token

    if isinstance(value, str):
        wire = value
    elif isinstance(value, dict) and "Fn::Join" in value:
        separator, parts = value["Fn::Join"]
        wire = separator.join(part if isinstance(part, str) else marker(part) for part in parts)
    elif isinstance(value, dict) and "Fn::Sub" in value:
        sub = value["Fn::Sub"]
        wire, variables = (sub, {}) if isinstance(sub, str) else sub
        def substitute(match):
            name = match.group(1)
            if name.startswith("!"):
                return "${" + name[1:] + "}"
            reference = variables.get(name)
            if reference is None:
                reference = {"Fn::GetAtt": name.split(".", 1)} if "." in name else {"Ref": name}
            return marker(reference)
        wire = re.sub(r"\$\{([^}]+)\}", substitute, wire)
    else:
        raise ValueError("Owned custom resource call uses an unsupported CloudFormation encoding.")
    return json.loads(wire), references


def encode_custom_resource_call(call, references):
    wire = json.dumps(call, separators=(",", ":"))
    parts = re.split(r"(__SGSUPPORT_CFN_TOKEN_\d+__)", wire)
    encoded = [references.get(part, part) for part in parts if part]
    return {"Fn::Join": ["", encoded]} if any(isinstance(part, dict) for part in encoded) else "".join(encoded)


def patch_gateway_error_template(original):
    """Change only the two owned gateway error calls and their redeployment."""
    template = json.loads(json.dumps(original))
    resources = template["Resources"]
    cors_ids, changed = [], False
    for family, response_type in (("UpdateApiCors4XX", "DEFAULT_4XX"), ("UpdateApiCors5XX", "DEFAULT_5XX")):
        matches = [(name, resource) for name, resource in resources.items() if family in name and resource["Type"] == "Custom::AWS"]
        if len(matches) != 1:
            raise ValueError("Cannot uniquely identify the owned " + family + " custom resource.")
        name, resource = matches[0]
        call, refs = decode_custom_resource_call(resource["Properties"]["Update"])
        if call.get("action") != "putGatewayResponse" or call.get("parameters", {}).get("responseType") != response_type:
            raise ValueError("Owned gateway custom resource has an unexpected operation.")
        headers = call["parameters"]["responseParameters"]
        if headers.get("gatewayresponse.header.Access-Control-Allow-Origin") != "'*'":
            headers["gatewayresponse.header.Access-Control-Allow-Origin"] = "'*'"
            resource["Properties"]["Update"] = encode_custom_resource_call(call, refs)
            changed = True
        cors_ids.append(name)
    redeploy = [(name, resource) for name, resource in resources.items() if "RedeployApi" in name and resource["Type"] == "Custom::AWS"]
    if len(redeploy) != 1:
        raise ValueError("Cannot uniquely identify the owned API redeployment custom resource.")
    name, resource = redeploy[0]
    depends = resource.get("DependsOn", [])
    depends = [depends] if isinstance(depends, str) else list(depends)
    missing = set(cors_ids) - set(depends)
    if changed or missing:
        call, refs = decode_custom_resource_call(resource["Properties"]["Update"])
        if call.get("action") != "createDeployment" or not isinstance(call.get("physicalResourceId"), dict):
            raise ValueError("Owned API redeployment custom resource has an unexpected operation.")
        call["physicalResourceId"]["id"] = "api-redeploy-sgsupport-" + str(uuid.uuid4())
        resource["Properties"]["Update"] = encode_custom_resource_call(call, refs)
        resource["DependsOn"] = sorted(set(depends) | set(cors_ids))
        changed = True
    return template, changed, cors_ids + [name]


def align_owned_gateway_errors(aws, metadata, args):
    cf = aws.client("cloudformation")
    stack = require_full_stack(cf, "web")
    original = cf.get_template(StackName=stack["StackName"], TemplateStage="Original")["TemplateBody"]
    if isinstance(original, str):
        original = json.loads(original)
    template, changed, resource_ids = patch_gateway_error_template(original)
    if not changed:
        print("Owned full API gateway errors already support both navigator and console origins.", flush=True)
        return
    body = json.dumps(template, separators=(",", ":"))
    deployment = json.loads(args.deployment.read_text())
    template_hash = hashlib.sha256(body.encode()).hexdigest()
    key = f"full-platform/cfn/web-cors-{template_hash}.json"
    aws.client("s3").put_object(Bucket=deployment["artifactsBucket"], Key=key, Body=body.encode(), ContentType="application/json", ServerSideEncryption="AES256")
    request = {"StackName": stack["StackName"], "TemplateURL": f"https://{deployment['artifactsBucket']}.s3.{REGION}.amazonaws.com/{key}", "Parameters": [{"ParameterKey": p["ParameterKey"], "UsePreviousValue": True} for p in stack.get("Parameters", [])], "Tags": stack.get("Tags", []), "Capabilities": stack.get("Capabilities", [])}
    if stack.get("RoleARN"):
        request["RoleARN"] = stack["RoleARN"]
    checkpoint = {"stackName": stack["StackName"], "status": "submitting", "changedResourceIds": resource_ids, "templateSha256": template_hash}
    checkpoint_path = ROOT / "artifacts" / "full-platform-gateway-cors.local.json"
    write_private(checkpoint_path, checkpoint)
    cf.update_stack(**request)
    checkpoint["status"] = "UPDATE_IN_PROGRESS"
    write_private(checkpoint_path, checkpoint)
    print("Aligning owned full API gateway error CORS with existing demo OPTIONS/success responses; preserving the administrator console.", flush=True)
    result = wait_stack(cf, stack["StackName"])
    checkpoint["status"] = result["StackStatus"]
    write_private(checkpoint_path, checkpoint)
    metadata["gatewayErrorCors"] = "*"


def publish(aws, metadata, main, original, args):
    from deploy import upload_frontend
    from full_platform_ingest import PlatformClient, load_corpus, redact, save_private, field, utc_now

    state = json.loads(args.state.read_text())
    catalogue, _, digest = load_corpus(ROOT / "data" / "official")
    if state.get("corpusHash") != digest or state.get("model", {}).get("status") != "completed" or state.get("model", {}).get("proposalStatus") != "accepted" or not state.get("model", {}).get("ontologyId"):
        raise ValueError("Publishing requires this verified corpus and a completed, accepted real ontology induction.")
    if state.get("pending") or any(source.get("status") not in {"APPROVED", "COMPLETED"} for source in state.get("sources", {}).values()):
        raise ValueError("Source ingestion/review is still pending; finish it before switching the live UI.")
    client = PlatformClient(args.metadata, args.credentials)
    namespace = state["namespaceId"]
    proposal = client.request("GET", f"/namespaces/{namespace}/proposals/{state['model']['proposalId']}")
    if proposal["status"] != "accepted" or field(proposal, "ontologyId") != state["model"]["ontologyId"]:
        raise ValueError("Actual platform proposal state differs from the saved accepted ontology.")
    actual_sources = client.paginate(f"/namespaces/{namespace}/sources")
    actual_ids = {field(source, "sourceId"): source["status"] for source in actual_sources}
    if any(actual_ids.get(source["sourceId"]) != source["status"] for source in state["sources"].values()):
        raise ValueError("Actual source statuses differ from the completed ingestion checkpoint.")
    if not (args.dist / "index.html").exists() or any(p.name.endswith(".local.json") or p.name.startswith(".env") for p in args.dist.rglob("*")):
        raise ValueError("Frontend build is missing or contains private configuration files.")
    config = {"apiUrl": metadata["apiUrl"], "region": REGION, "localPreview": False, "cognito": {key: metadata["cognito"][key] for key in ("authority", "clientId", "domain", "scope")}, "platform": {"mode": "full", "apiUrl": metadata["apiUrl"], "namespaceId": namespace, "serveRuntimeArn": metadata["serveRuntimeArn"], "region": REGION, "catalogueUrl": "/official/catalogue.json", "ontologyId": state["model"]["ontologyId"]}}
    save_private(ROOT / "artifacts" / "full-platform-public-config.local.json", config)
    if not args.skip_gateway_error_alignment:
        align_owned_gateway_errors(aws, metadata, args)
    update_csp(aws, metadata, main)
    s3 = aws.client("s3")
    upload_frontend(s3, original["FrontendBucket"], args.dist)
    s3.put_object(Bucket=original["FrontendBucket"], Key="official/catalogue.json", Body=json.dumps(catalogue, ensure_ascii=False).encode(), ContentType="application/json", CacheControl="no-cache,max-age=0,must-revalidate", ServerSideEncryption="AES256")
    s3.put_object(Bucket=original["FrontendBucket"], Key="config.json", Body=json.dumps(config).encode(), ContentType="application/json", CacheControl="no-store,max-age=0", ServerSideEncryption="AES256")
    invalidation = aws.client("cloudfront").create_invalidation(DistributionId=original["DistributionId"], InvalidationBatch={"Paths": {"Quantity": 1, "Items": ["/*"]}, "CallerReference": "full-platform-" + str(uuid.uuid4())})
    metadata.update({"namespaceId": namespace, "ontologyId": state["model"]["ontologyId"], "publishedAt": utc_now(), "invalidationId": invalidation["Invalidation"]["Id"], "officialSchemeCount": len(catalogue["schemes"])})
    write_private(args.metadata, redact(metadata))
    print(f"Published the full-platform Singapore navigator at {WEBSITE}.", flush=True)
    print(f"CloudFront invalidation {metadata['invalidationId']} requested.", flush=True)
    print(f"Upstream administrator console: {metadata['adminConsoleUrl']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--bootstrap", action="store_true")
    mode.add_argument("--collect-only", action="store_true")
    mode.add_argument("--publish", action="store_true")
    parser.add_argument("--deployment", type=Path, default=ROOT / "deployment.json")
    parser.add_argument("--metadata", type=Path, default=ROOT / "artifacts" / "full-platform.json")
    parser.add_argument("--credentials", type=Path, default=ROOT / "artifacts" / "full-platform-login.local.json")
    parser.add_argument("--state", type=Path, default=ROOT / "artifacts" / "full-platform-ingest.local.json")
    parser.add_argument("--dist", type=Path, default=ROOT / "frontend" / "dist")
    parser.add_argument("--skip-gateway-error-alignment", action="store_true", help="Skip the owned full-web stack gateway-error CORS update when it was already handled separately.")
    args = parser.parse_args()
    aws = session(REGION)
    if aws.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise ValueError("AWS credentials do not identify the authorized account.")
    metadata, main_stack, original = collect(aws, args.deployment, args.metadata)
    if args.bootstrap or args.publish:
        configure_login(aws, metadata, args.credentials)
    if args.publish:
        publish(aws, metadata, main_stack, original, args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Full-platform frontend stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
