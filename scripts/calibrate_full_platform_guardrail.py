#!/usr/bin/env python3
"""Plan the owned primary guardrail's HIGH -> MEDIUM prompt-attack calibration.

Default: read-only AWS inspection and a private local receipt. --apply creates
and executes one verified, non-replacing guardrail policy modification. The two
dependent SSM references may refresh; their ID/version values must stay equal.
Every
other primary policy, the retrieval guardrail and all stack properties remain
unchanged. Run with env -u AWS_PROFILE when using the supplied environment keys.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone

from full_platform_frontend import ACCOUNT, REGION, ROOT, require_full_stack, session, write_private

PRIMARY_ID = "29id4s0qsd4r"
RETRIEVAL_ID = "ia89bt9wwzfu"
LOGICAL_ID = "BedrockGuardrail"
STACK_NAME = "sgsupport-demo-guardrail"
SSM_REFERENCES = {
    "SsmGuardrailIdED99FB12": ("/sgsupport/bedrock/guardrail-id", "GuardrailId", PRIMARY_ID),
    "SsmGuardrailVersionE02A7D78": ("/sgsupport/bedrock/guardrail-version", "Version", "DRAFT"),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def template_of(cf, stack_id):
    value = cf.get_template(StackName=stack_id, TemplateStage="Original")["TemplateBody"]
    return json.loads(value) if isinstance(value, str) else value


def prompt_filter(filters, key):
    found = [item for item in filters if item.get(key) == "PROMPT_ATTACK"]
    if len(found) != 1:
        raise ValueError("Expected exactly one PROMPT_ATTACK filter.")
    return found[0]


def proposed_template(original):
    target = copy.deepcopy(original)
    resource = target["Resources"][LOGICAL_ID]
    if resource["Type"] != "AWS::Bedrock::Guardrail" or resource["Properties"]["Name"] != STACK_NAME:
        raise ValueError("Primary guardrail resource identity differs from the owned deployment.")
    filter_ = prompt_filter(resource["Properties"]["ContentPolicyConfig"]["FiltersConfig"], "Type")
    if filter_.get("InputStrength") not in {"HIGH", "MEDIUM"} or filter_.get("OutputStrength") != "NONE":
        raise ValueError("Only the documented HIGH -> MEDIUM input change is supported.")
    before = filter_["InputStrength"]
    filter_["InputStrength"] = "MEDIUM"
    check = copy.deepcopy(target)
    prompt_filter(check["Resources"][LOGICAL_ID]["Properties"]["ContentPolicyConfig"]["FiltersConfig"], "Type")["InputStrength"] = before
    if check != original:
        raise ValueError("Calibration would change another template property.")
    return target, before


def snapshot(bedrock, guardrail_id):
    result = bedrock.get_guardrail(guardrailIdentifier=guardrail_id, guardrailVersion="DRAFT")
    if result.get("guardrailId") != guardrail_id or result.get("guardrailArn") != f"arn:aws:bedrock:{REGION}:{ACCOUNT}:guardrail/{guardrail_id}":
        raise ValueError("Guardrail account, region or physical identity changed.")
    if result.get("version") != "DRAFT" or result.get("status") != "READY":
        raise ValueError("Expected the existing READY DRAFT guardrail.")
    # Keep all policies and configuration, excluding service timestamps/status.
    excluded = {"ResponseMetadata", "createdAt", "updatedAt", "status", "statusReasons", "failureRecommendations"}
    return {key: value for key, value in result.items() if key not in excluded}


def require_resources(cf, stack_id):
    for logical, expected in ((LOGICAL_ID, PRIMARY_ID), ("RetrievalGuardrail", RETRIEVAL_ID)):
        detail = cf.describe_stack_resource(StackName=stack_id, LogicalResourceId=logical)["StackResourceDetail"]
        expected_arn = f"arn:aws:bedrock:{REGION}:{ACCOUNT}:guardrail/{expected}"
        if detail.get("PhysicalResourceId") != expected_arn or detail.get("ResourceType") != "AWS::Bedrock::Guardrail":
            raise ValueError("Guardrail physical resource ownership changed.")


def wait_change(cf, change_id, deadline):
    while time.monotonic() < deadline:
        change = cf.describe_change_set(ChangeSetName=change_id)
        if change["Status"] == "CREATE_COMPLETE":
            changes = list(change.get("Changes", []))
            while change.get("NextToken"):
                change = cf.describe_change_set(ChangeSetName=change_id, NextToken=change["NextToken"])
                changes.extend(change.get("Changes", []))
            return changes
        if change["Status"] not in {"CREATE_PENDING", "CREATE_IN_PROGRESS"}:
            raise RuntimeError("Guardrail change set failed; inspect its recorded ID.")
        time.sleep(5)
    raise TimeoutError("Change set remains pending; inspect the recorded ID before retrying.")


def ssm_values(ssm):
    values = {name: ssm.get_parameter(Name=name)["Parameter"]["Value"] for name, _, _ in SSM_REFERENCES.values()}
    if values != {name: value for name, _, value in SSM_REFERENCES.values()}:
        raise ValueError("Active SSM guardrail ID/version differ from the owned READY DRAFT policy.")
    return values


def require_one_change(changes):
    by_id = {item.get("ResourceChange", {}).get("LogicalResourceId"): item.get("ResourceChange", {}) for item in changes}
    if len(by_id) != len(changes) or set(by_id) not in ({LOGICAL_ID}, {LOGICAL_ID, *SSM_REFERENCES}):
        raise ValueError("Only the primary guardrail and its two derived SSM references may refresh.")
    resource = by_id[LOGICAL_ID]
    if (resource.get("LogicalResourceId") != LOGICAL_ID or resource.get("ResourceType") != "AWS::Bedrock::Guardrail"
            or resource.get("Action") != "Modify" or resource.get("Replacement") != "False"
            or resource.get("PhysicalResourceId") != f"arn:aws:bedrock:{REGION}:{ACCOUNT}:guardrail/{PRIMARY_ID}"):
        raise ValueError("Change set must contain exactly one non-replacing primary guardrail modification.")
    for detail in resource.get("Details", []):
        target = detail.get("Target", {})
        if target.get("Attribute") != "Properties" or target.get("Name") != "ContentPolicyConfig":
            raise ValueError("Change set includes an unexpected guardrail property.")
    for logical, (name, attribute, _) in SSM_REFERENCES.items():
        dependent = by_id.get(logical)
        if dependent is None:
            continue
        if (dependent.get("Action") != "Modify" or dependent.get("Replacement") != "False"
                or dependent.get("ResourceType") != "AWS::SSM::Parameter" or dependent.get("PhysicalResourceId") != name):
            raise ValueError("Only non-replacing derived SSM value refreshes are permitted.")
        details = dependent.get("Details", [])
        if len(details) != 1:
            raise ValueError("Unexpected SSM refresh details.")
        detail = details[0]
        target = detail.get("Target", {})
        if (target.get("Attribute") != "Properties" or target.get("Name") != "Value"
                or target.get("RequiresRecreation") != "Never" or detail.get("Evaluation") != "Dynamic"
                or detail.get("ChangeSource") != "ResourceAttribute"
                or detail.get("CausingEntity") != f"{LOGICAL_ID}.{attribute}"):
            raise ValueError("SSM refresh does not originate solely from the guardrail's unchanged identity/version.")


def run(args):
    aws = session(REGION)
    if aws.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise ValueError("Credentials do not identify the authorized account.")
    cf, bedrock, ssm = aws.client("cloudformation"), aws.client("bedrock"), aws.client("ssm")
    stack = require_full_stack(cf, "guardrail")
    if stack["StackName"] != STACK_NAME or stack.get("DisableRollback", False):
        raise ValueError("Expected the owned stack with rollback enabled.")
    stack_id = stack["StackId"]
    require_resources(cf, stack_id)
    original = template_of(cf, stack_id)
    target, before = proposed_template(original)
    primary_before, retrieval_before = snapshot(bedrock, PRIMARY_ID), snapshot(bedrock, RETRIEVAL_ID)
    ssm_before = ssm_values(ssm)
    live_filter = prompt_filter(primary_before["contentPolicy"]["filters"], "type")
    if live_filter.get("inputStrength") != before or live_filter.get("outputStrength") != "NONE":
        raise ValueError("Primary live policy differs from its CloudFormation template.")
    run_id = uuid.uuid4().hex
    path = ROOT / f"artifacts/full-platform-guardrail-calibration-{run_id}.local.json"
    receipt = {"schemaVersion": 1, "checkedAt": datetime.now(timezone.utc).isoformat(),
               "accountId": ACCOUNT, "region": REGION, "stackName": STACK_NAME, "stackId": stack_id,
               "primaryGuardrailId": PRIMARY_ID, "retrievalGuardrailId": RETRIEVAL_ID, "version": "DRAFT",
               "change": {"logicalResourceId": LOGICAL_ID, "property": "ContentPolicyConfig.FiltersConfig[PROMPT_ATTACK].InputStrength", "before": before, "after": "MEDIUM"},
               "beforeTemplateSha256": digest(original), "targetTemplateSha256": digest(target),
               "beforePolicies": {"primary": primary_before, "retrieval": retrieval_before},
               "beforeSsmValues": ssm_before,
               "status": "ALREADY_CALIBRATED" if before == "MEDIUM" else "READ_ONLY_PLAN"}
    write_private(path, receipt)
    print(f"Private receipt: {path}", flush=True)
    print(f"Primary PROMPT_ATTACK input: {before} -> MEDIUM; all other properties retained.", flush=True)
    if not args.apply or before == "MEDIUM":
        return
    body = json.dumps(target, separators=(",", ":"))
    if len(body.encode()) > 51200:
        raise ValueError("Guardrail template exceeds the inline CloudFormation limit.")
    deadline = time.monotonic() + args.timeout_seconds
    try:
        cf.validate_template(TemplateBody=body)
        request = {"StackName": stack_id, "ChangeSetName": "sgsupport-guardrail-calibration-" + run_id,
                   "ChangeSetType": "UPDATE", "TemplateBody": body,
                   "Parameters": [{"ParameterKey": item["ParameterKey"], "UsePreviousValue": True} for item in stack.get("Parameters", [])],
                   "Tags": stack.get("Tags", []), "Capabilities": stack.get("Capabilities", []),
                   "NotificationARNs": stack.get("NotificationARNs", [])}
        for key in ("RoleARN", "RollbackConfiguration"):
            if stack.get(key):
                request[key] = stack[key]
        change_id = cf.create_change_set(**request)["Id"]
        receipt.update({"changeSetId": change_id, "status": "CHANGE_SET_PENDING"})
        write_private(path, receipt)
        changes = wait_change(cf, change_id, deadline)
        require_one_change(changes)
        # A concurrent update must not invalidate the original narrow proposal.
        current = require_full_stack(cf, "guardrail")
        require_resources(cf, stack_id)
        if current["StackId"] != stack_id or template_of(cf, stack_id) != original:
            raise ValueError("Stack changed while preparing the change set; refusing execution.")
        if snapshot(bedrock, PRIMARY_ID) != primary_before or snapshot(bedrock, RETRIEVAL_ID) != retrieval_before or ssm_values(ssm) != ssm_before:
            raise ValueError("Guardrail policy changed while preparing the change set.")
        receipt.update({"changes": changes, "status": "EXECUTING", "rollbackEnabled": True})
        write_private(path, receipt)
        print("Verified one policy modification and unchanged derived SSM references; executing with rollback enabled.", flush=True)
        cf.execute_change_set(ChangeSetName=change_id, StackName=stack_id, DisableRollback=False, ClientRequestToken=run_id)
        last_status = None
        while time.monotonic() < deadline:
            result = cf.describe_stacks(StackName=stack_id)["Stacks"][0]
            status = result["StackStatus"]
            if status != last_status:
                print(f"{STACK_NAME}: {status}", flush=True)
                last_status = status
            if status == "UPDATE_COMPLETE":
                # ExecuteChangeSet is asynchronous: the first stack read can
                # still expose the previous UPDATE_COMPLETE state.
                execution = cf.describe_change_set(ChangeSetName=change_id)["ExecutionStatus"]
                if execution == "EXECUTE_COMPLETE":
                    break
                if execution == "EXECUTE_FAILED":
                    raise RuntimeError("Guardrail change set execution failed; inspect the recorded ID.")
            elif status == current["StackStatus"]:
                # A newly executed update can briefly expose CREATE_COMPLETE
                # from the original deployment before its first update starts.
                execution = cf.describe_change_set(ChangeSetName=change_id)["ExecutionStatus"]
                if execution not in {"AVAILABLE", "EXECUTE_PENDING", "EXECUTE_IN_PROGRESS"}:
                    raise RuntimeError("Guardrail change set did not enter its expected update; inspect the recorded ID.")
            elif not status.endswith("_IN_PROGRESS"):
                raise RuntimeError("Guardrail update ended unsuccessfully; inspect the recorded stack and change set.")
            time.sleep(10)
        else:
            raise TimeoutError("Update may still be running; inspect the private receipt before retrying.")
        require_resources(cf, stack_id)
        actual_template = template_of(cf, stack_id)
        primary_after, retrieval_after = snapshot(bedrock, PRIMARY_ID), snapshot(bedrock, RETRIEVAL_ID)
        ssm_after = ssm_values(ssm)
        receipt.update({"afterTemplateSha256": digest(actual_template), "afterPolicies": {"primary": primary_after, "retrieval": retrieval_after}, "afterSsmValues": ssm_after, "status": "VERIFYING"})
        write_private(path, receipt)
        expected_policy = copy.deepcopy(primary_before)
        prompt_filter(expected_policy["contentPolicy"]["filters"], "type")["inputStrength"] = "MEDIUM"
        if actual_template != target or primary_after != expected_policy or retrieval_after != retrieval_before or ssm_after != ssm_before:
            raise ValueError("Post-update verification detected another template or policy difference.")
        receipt["status"] = "UPDATE_COMPLETE_VERIFIED"
        write_private(path, receipt)
        print("Primary input strength is MEDIUM; all other primary and retrieval policies are unchanged.", flush=True)
    except Exception as exc:
        receipt.update({"status": "ERROR_REVIEW_REQUIRED", "errorType": type(exc).__name__})
        write_private(path, receipt)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Execute the narrowly verified change set; default is read-only.")
    parser.add_argument("--timeout-seconds", type=int, default=900, help="Combined change-set/update wait deadline (1–900 seconds).")
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 900:
        parser.error("--timeout-seconds must be 1–900.")
    run(args)


if __name__ == "__main__":
    main()
