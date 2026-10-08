"""Infrastructure invariants that catch broken auth, resource isolation and routing."""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = json.loads((ROOT / "infra/main.json").read_text())
ARTIFACTS = json.loads((ROOT / "infra/artifacts.json").read_text())
RESOURCES = MAIN["Resources"]


def references(value):
    if isinstance(value, list):
        return set().union(*(references(item) for item in value)) if value else set()
    if not isinstance(value, dict):
        return set()
    found = set()
    if "Ref" in value:
        found.add(value["Ref"])
    if "Fn::GetAtt" in value:
        found.add(value["Fn::GetAtt"][0] if isinstance(value["Fn::GetAtt"], list) else value["Fn::GetAtt"].split(".")[0])
    if "Fn::Sub" in value:
        template = value["Fn::Sub"]
        template, mapping = (template, {}) if isinstance(template, str) else template
        found |= {match.split(".")[0] for match in re.findall(r"\$\{([^}]+)\}", template) if match not in mapping}
    for nested in value.values():
        found |= references(nested)
    return found


class InfrastructureTests(unittest.TestCase):
    def test_dependencies_have_no_cycles(self):
        dependencies = {}
        for name, resource in RESOURCES.items():
            explicit = resource.get("DependsOn", [])
            explicit = [explicit] if isinstance(explicit, str) else explicit
            dependencies[name] = (references(resource) | set(explicit)) & set(RESOURCES)

        def visit(name, visiting, done):
            self.assertNotIn(name, visiting, "Resource dependency cycle: " + " -> ".join([*visiting, name]))
            if name in done:
                return
            for dependency in dependencies[name]:
                visit(dependency, [*visiting, name], done)
            done.add(name)

        done = set()
        for name in RESOURCES:
            visit(name, [], done)

    def test_both_buckets_are_private_encrypted_and_owned(self):
        for template in [MAIN, ARTIFACTS]:
            for resource in template["Resources"].values():
                if resource["Type"] != "AWS::S3::Bucket":
                    continue
                props = resource["Properties"]
                self.assertTrue(all(props["PublicAccessBlockConfiguration"].values()))
                self.assertEqual(props["OwnershipControls"]["Rules"][0]["ObjectOwnership"], "BucketOwnerEnforced")
                self.assertEqual(props["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]["ServerSideEncryptionByDefault"]["SSEAlgorithm"], "AES256")
                self.assertIn({"Key": "Project", "Value": {"Ref": "ProjectName"}}, props["Tags"])
        permission = RESOURCES["FrontendPolicy"]["Properties"]["PolicyDocument"]["Statement"][0]
        self.assertEqual(permission["Principal"], {"Service": "cloudfront.amazonaws.com"})
        self.assertEqual(permission["Action"], "s3:GetObject")
        self.assertIn("${Distribution}", permission["Condition"]["StringEquals"]["AWS:SourceArn"]["Fn::Sub"])
        self.assertEqual(ARTIFACTS["Resources"]["ArtifactsBucket"]["DeletionPolicy"], "Retain")

    def test_browser_login_has_no_secret_and_all_routes_require_access_scope(self):
        client = RESOURCES["UserPoolClient"]["Properties"]
        self.assertFalse(client["GenerateSecret"])
        self.assertEqual(client["AllowedOAuthFlows"], ["code"])
        self.assertIn("life-events/access", client["AllowedOAuthScopes"])
        self.assertTrue(RESOURCES["UserPool"]["Properties"]["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"])
        self.assertNotIn("ALLOW_USER_PASSWORD_AUTH", client["ExplicitAuthFlows"])
        callbacks = json.dumps([client["CallbackURLs"], client["LogoutURLs"]])
        self.assertNotIn("localhost", callbacks)
        self.assertIn("https://${Distribution.DomainName}/auth/callback", callbacks)
        authorizer = RESOURCES["JwtAuthorizer"]["Properties"]["JwtConfiguration"]
        self.assertEqual(authorizer["Audience"], [{"Ref": "UserPoolClient"}])
        for resource in RESOURCES.values():
            if resource["Type"] == "AWS::ApiGatewayV2::Route":
                route = resource["Properties"]
                if route["RouteKey"].startswith("OPTIONS "):
                    self.assertEqual(route["AuthorizationType"], "NONE")
                    self.assertIn("Target", route, "Unintegrated routes are omitted from API Gateway deployments")
                    self.assertNotIn("AuthorizerId", route)
                else:
                    self.assertEqual(route["AuthorizationType"], "JWT")
                    self.assertEqual(route["AuthorizationScopes"], ["life-events/access"])
        self.assertEqual(RESOURCES["PreflightRoute"]["Properties"]["RouteKey"], "OPTIONS /{proxy+}")

    def test_cors_csp_cache_and_resource_limits(self):
        self.assertEqual(RESOURCES["HttpApi"]["Properties"]["CorsConfiguration"]["AllowOrigins"], [{"Ref": "FrontendOrigin"}])
        self.assertEqual(MAIN["Parameters"]["FrontendOrigin"]["Default"], "https://deployment.invalid")
        csp = RESOURCES["SecurityHeaders"]["Properties"]["ResponseHeadersPolicyConfig"]["SecurityHeadersConfig"]["ContentSecurityPolicy"]["ContentSecurityPolicy"]["Fn::Sub"]
        self.assertIn("script-src 'self';", csp)
        self.assertIn("https://${HttpApi}.execute-api.${AWS::Region}.amazonaws.com", csp)
        self.assertNotIn("script-src 'unsafe-inline'", csp)
        distro = RESOURCES["Distribution"]["Properties"]["DistributionConfig"]
        self.assertEqual(distro["PriceClass"], "PriceClass_All")
        behaviors = {item["PathPattern"]: item for item in distro["CacheBehaviors"]}
        self.assertEqual(behaviors["config.json"]["CachePolicyId"], "4135ea2d-6df8-44a3-9df3-4b5a84be39ad")
        self.assertNotIn("CustomErrorResponses", distro)
        self.assertEqual(RESOURCES["ApiFunction"]["Properties"]["ReservedConcurrentExecutions"], 5)
        self.assertEqual(RESOURCES["DefaultStage"]["Properties"]["DefaultRouteSettings"]["ThrottlingRateLimit"], 5)
        self.assertLessEqual(RESOURCES["FunctionLogs"]["Properties"]["RetentionInDays"], 14)

    def test_actual_spa_function_keeps_asset_paths(self):
        function = RESOURCES["SpaRoutes"]["Properties"]["FunctionCode"]
        cases = {"/": "/index.html", "/auth/callback": "/index.html", "/citizen/context/": "/index.html", "/config.json": "/config.json", "/assets/main-ABC.js": "/assets/main-ABC.js", "/assets/missing.js": "/assets/missing.js", "/favicon.svg": "/favicon.svg"}
        program = function + "\nconst cases=" + json.dumps(cases) + "; for (const [uri, expected] of Object.entries(cases)) { const actual=handler({request:{uri}}).uri; if(actual!==expected) throw new Error(uri+' -> '+actual); }"
        subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)

    def test_lambda_has_only_own_logs_and_optional_single_model(self):
        policies = RESOURCES["FunctionRole"]["Properties"]["Policies"]
        logs = policies[0]["PolicyDocument"]["Statement"][0]
        self.assertEqual(set(logs["Action"]), {"logs:CreateLogStream", "logs:PutLogEvents"})
        self.assertIn("/aws/lambda/${ProjectName}-api", logs["Resource"]["Fn::Sub"])
        bedrock = policies[1]["Fn::If"]
        self.assertEqual(bedrock[0], "UseBedrock")
        statement = bedrock[1]["PolicyDocument"]["Statement"][0]
        self.assertEqual(statement["Action"], ["bedrock:InvokeModel"])
        self.assertEqual(statement["Resource"], [{"Fn::Sub": "arn:${AWS::Partition}:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0"}])


if __name__ == "__main__":
    unittest.main()
