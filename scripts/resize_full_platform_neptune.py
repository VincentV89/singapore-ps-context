#!/usr/bin/env python3
"""Resize the owned demo Neptune instance after verified graph memory failures.

Only db.t4g.medium -> db.r8g.large is permitted. A CloudFormation change set
must show one in-place instance modification before it is executed. The cluster,
instance identifier, endpoints, parameters, tags and execution role are retained.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid

from full_platform_frontend import (
    ACCOUNT, REGION, ROOT, require_full_stack, require_original_deployment,
    session, write_private,
)
from aws_common import wait_stack


def main():
    aws = session(REGION)
    if aws.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise ValueError("Current credentials do not identify the authorized account.")
    cf = aws.client("cloudformation")
    stack = require_full_stack(cf, "storage")
    deployment, _, _ = require_original_deployment(aws, ROOT / "deployment.json")
    template = cf.get_template(StackName=stack["StackName"], TemplateStage="Original")["TemplateBody"]
    if isinstance(template, str):
        template = json.loads(template)
    original = copy.deepcopy(template)
    instance = template["Resources"]["NeptunePrimaryInstance"]
    if instance["Type"] != "AWS::Neptune::DBInstance" or instance["Properties"]["DBInstanceIdentifier"] != "sgsupport-demo-neptune-primary":
        raise ValueError("Cannot identify the owned Neptune instance.")
    before = instance["Properties"]["DBInstanceClass"]
    if before == "db.r8g.large":
        print("Owned Neptune already uses db.r8g.large.", flush=True)
        return
    if before != "db.t4g.medium":
        raise ValueError("Only the documented t4g.medium -> r8g.large resize is supported.")
    instance["Properties"]["DBInstanceClass"] = "db.r8g.large"
    check = copy.deepcopy(template)
    check["Resources"]["NeptunePrimaryInstance"]["Properties"]["DBInstanceClass"] = before
    if check != original:
        raise ValueError("Resize changes more than the owned instance class.")
    body = json.dumps(template, separators=(",", ":")).encode()
    digest = hashlib.sha256(body).hexdigest()
    key = f"full-platform/cfn/neptune-r8g-large-{digest}.json"
    aws.client("s3").put_object(Bucket=deployment["artifactsBucket"], Key=key, Body=body, ContentType="application/json", ServerSideEncryption="AES256")
    url = f"https://{deployment['artifactsBucket']}.s3.{REGION}.amazonaws.com/{key}"
    cf.validate_template(TemplateURL=url)
    request = {"StackName": stack["StackName"], "ChangeSetName": "sgsupport-neptune-memory-" + uuid.uuid4().hex,
               "ChangeSetType": "UPDATE", "TemplateURL": url,
               "Parameters": [{"ParameterKey": p["ParameterKey"], "UsePreviousValue": True} for p in stack.get("Parameters", [])],
               "Tags": stack.get("Tags", []), "Capabilities": stack.get("Capabilities", [])}
    if stack.get("RoleARN"):
        request["RoleARN"] = stack["RoleARN"]
    change_id = cf.create_change_set(**request)["Id"]
    checkpoint = {"stackName": stack["StackName"], "instanceIdentifier": "sgsupport-demo-neptune-primary",
                  "beforeClass": before, "targetClass": "db.r8g.large", "templateSha256": digest,
                  "reason": "Verified concurrent document ingestion ExecuteOpenCypherQuery MemoryLimitExceededException",
                  "changeSetId": change_id, "status": "CHANGE_SET_PENDING"}
    path = ROOT / "artifacts/full-platform-neptune-resize.local.json"
    write_private(path, checkpoint)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        change = cf.describe_change_set(ChangeSetName=change_id)
        if change["Status"] == "CREATE_COMPLETE":
            break
        if change["Status"] not in {"CREATE_PENDING", "CREATE_IN_PROGRESS"}:
            raise RuntimeError("Neptune resize change set failed: " + change.get("StatusReason", change["Status"]))
        time.sleep(2)
    else:
        raise TimeoutError("Change set is still pending; inspect its recorded ID before retrying.")
    changes = change.get("Changes", [])
    resource = changes[0].get("ResourceChange", {}) if len(changes) == 1 else {}
    if resource.get("LogicalResourceId") != "NeptunePrimaryInstance" or resource.get("Action") != "Modify" or resource.get("Replacement") != "False":
        raise ValueError("Resize must contain exactly one in-place Neptune instance modification.")
    checkpoint["changes"] = changes
    checkpoint["status"] = "EXECUTING"
    write_private(path, checkpoint)
    print("Verified one in-place Neptune modification; resizing to db.r8g.large (16 GiB).", flush=True)
    cf.execute_change_set(ChangeSetName=change_id)
    result = wait_stack(cf, stack["StackName"])
    checkpoint["status"] = result["StackStatus"]
    write_private(path, checkpoint)
    print("Owned Neptune resize completed; verify database health before retrying ingestion.", flush=True)


if __name__ == "__main__":
    main()
