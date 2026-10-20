"""CodeDeploy rollback for rollback_deploy: one CreateDeployment call (2 s timeout, no retry)."""

import json

import boto3
from botocore.config import Config


def appspec_revision(function: str, current: str, target: str) -> dict:
    spec = {
        "version": 0.0,
        "Resources": [
            {
                "checkout": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {
                        "Name": function,
                        "Alias": "live",
                        "CurrentVersion": current,
                        "TargetVersion": target,
                    },
                }
            }
        ],
    }
    return {"revisionType": "AppSpecContent", "appSpecContent": {"content": json.dumps(spec)}}


class CodeDeployRollback:
    def __init__(self, application: str, group: str) -> None:
        self._app, self._group = application, group
        self._client = boto3.client(
            "codedeploy",
            config=Config(connect_timeout=1, read_timeout=2, retries={"max_attempts": 1}),
        )

    def start(self, function: str, current: str, target: str) -> str:
        return self._client.create_deployment(
            applicationName=self._app,
            deploymentGroupName=self._group,
            revision=appspec_revision(function, current, target),
            description=f"rollback_deploy (voice): v{current} -> v{target}",
        )["deploymentId"]
