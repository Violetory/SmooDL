"""Validate a compiled, unsigned workflow before signing or sharing it."""

import json
import plistlib
import sys
from pathlib import Path


def validate(path: Path) -> None:
    workflow = plistlib.loads(path.read_bytes())
    actions = workflow["WFWorkflowActions"]
    outputs = {}
    groups = []
    closed = set()
    uuids = set()
    for action in actions:
        params = action.get("WFWorkflowActionParameters", {})
        if "UUID" in params:
            assert params["UUID"] not in uuids, "Duplicate action UUID"
            uuids.add(params["UUID"])
        if "CustomOutputName" in params:
            outputs[params["CustomOutputName"]] = params
        if "GroupingIdentifier" in params:
            group = params["GroupingIdentifier"]
            mode = params["WFControlFlowMode"]
            if mode == 0:
                assert group not in groups and group not in closed, "Reused control-flow group"
                groups.append(group)
            else:
                assert groups and groups[-1] == group, "Unbalanced control flow"
                if mode == 2:
                    closed.add(groups.pop())
    assert not groups, "Unclosed control-flow group"

    questions = workflow["WFWorkflowImportQuestions"]
    assert len(questions) == 1, "Exactly one API Key import field is required"
    question = questions[0]
    field = actions[question["ActionIndex"]]["WFWorkflowActionParameters"]
    assert field["CustomOutputName"] == "configuredKey", "Import question targets wrong action"
    assert question["DefaultValue"] == "" and field[question["ParameterKey"]] == "", (
        "Shared template must not contain a credential"
    )
    key_uuid = outputs["API_KEY"]["UUID"]
    for action in actions:
        if action["WFWorkflowActionIdentifier"] != "is.workflow.actions.downloadurl":
            continue
        params = action["WFWorkflowActionParameters"]
        if params.get("WFHTTPMethod") == "POST":
            headers = params["WFHTTPHeaders"]["Value"]["WFDictionaryFieldValueItems"]
            authorization = next(
                h["WFValue"]["Value"] for h in headers
                if h["WFKey"]["Value"]["string"] == "Authorization"
            )
            assert authorization["string"] == "Bearer \ufffc"
            assert key_uuid in str(authorization["attachmentsByRange"])
        else:
            assert "WFHTTPHeaders" not in params, "Do not send credentials to media URLs"

    # Exercise the actual emitted JSON fragments. Incorrect quote escaping can
    # compile successfully yet make every multi-item materialization request fail.
    ids = ["asset_" + "1" * 32, "asset_" + "2" * 32]
    job = "job_" + "3" * 32
    separator = outputs["joinedIDs"]["WFTextCustomSeparator"]
    for selected in (ids[:1], ids):
        body = (
            outputs["materializePrefix"]["WFTextActionText"]
            + job
            + outputs["materializeIDsPrefix"]["WFTextActionText"]
            + separator.join(selected)
            + outputs["materializeSuffix"]["WFTextActionText"]
        )
        assert json.loads(body) == {
            "job_id": job,
            "asset_ids": selected,
            "archive": "auto",
        }

    materialized_uuid = outputs["materialized"]["UUID"]
    assignments = [
        a.get("WFWorkflowActionParameters", {}) for a in actions
        if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.setvariable"
    ]
    assert any(
        p.get("WFVariableName") == "jobResponse"
        and materialized_uuid in str(p.get("WFInput"))
        for p in assignments
    ), "Materialization must refresh the result before checking completion"
    print(f"Validated {len(actions)} actions, control flow, and single/multiple asset JSON.")


if __name__ == "__main__":
    validate(Path(sys.argv[1]))
