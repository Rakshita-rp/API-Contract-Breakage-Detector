"""
API Contract Breakage Detector
Compares two OpenAPI YAML/JSON specifications and reports likely breaking changes.

Usage:
    python detector.py api_v1.yaml api_v2.yaml
    python detector.py api_v1.yaml api_v2.yaml --output report.json
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Missing dependency. Install it with: pip install -r requirements.txt")
    sys.exit(1)


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def load_spec(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict) or "paths" not in data:
        raise ValueError(f"{file_path} is not a valid-looking OpenAPI document (missing 'paths').")
    return data


def operations(spec):
    result = {}
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() in HTTP_METHODS and isinstance(operation, dict):
                result[(path, method.lower())] = operation
    return result


def resolve_schema(schema, spec):
    """Resolve simple local component references such as #/components/schemas/Student."""
    if not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    if not ref or not ref.startswith("#/"):
        return schema
    current = spec
    try:
        for part in ref[2:].split("/"):
            current = current[part.replace("~1", "/").replace("~0", "~")]
        return current if isinstance(current, dict) else {}
    except (KeyError, TypeError):
        return schema


def response_schema(operation, spec):
    responses = operation.get("responses", {})
    response = responses.get("200") or responses.get("201") or responses.get("default")
    if not isinstance(response, dict):
        return {}
    content = response.get("content", {})
    for media in ("application/json", "application/*", "*/*"):
        if media in content:
            return resolve_schema(content[media].get("schema", {}), spec)
    if content:
        first = next(iter(content.values()))
        return resolve_schema(first.get("schema", {}), spec)
    return {}


def compare_properties(old_schema, new_schema, old_spec, new_spec, location, findings):
    old_schema = resolve_schema(old_schema, old_spec)
    new_schema = resolve_schema(new_schema, new_spec)

    old_type = old_schema.get("type")
    new_type = new_schema.get("type")
    if old_type and new_type and old_type != new_type:
        findings.append({
            "severity": "BREAKING",
            "location": location,
            "change": f"Schema type changed from '{old_type}' to '{new_type}'"
        })

    old_props = old_schema.get("properties", {})
    new_props = new_schema.get("properties", {})
    for name in sorted(set(old_props) - set(new_props)):
        findings.append({
            "severity": "BREAKING",
            "location": f"{location}.{name}",
            "change": "Response property was removed"
        })
    for name in sorted(set(old_props) & set(new_props)):
        old_prop = resolve_schema(old_props[name], old_spec)
        new_prop = resolve_schema(new_props[name], new_spec)
        ot, nt = old_prop.get("type"), new_prop.get("type")
        if ot and nt and ot != nt:
            findings.append({
                "severity": "BREAKING",
                "location": f"{location}.{name}",
                "change": f"Property type changed from '{ot}' to '{nt}'"
            })

    newly_required = set(new_schema.get("required", [])) - set(old_schema.get("required", []))
    for name in sorted(newly_required):
        findings.append({
            "severity": "BREAKING",
            "location": f"{location}.{name}",
            "change": "Property became required"
        })


def compare_specs(old_spec, new_spec):
    findings = []
    old_ops, new_ops = operations(old_spec), operations(new_spec)

    for key in sorted(set(old_ops) - set(new_ops)):
        path, method = key
        findings.append({
            "severity": "BREAKING",
            "location": f"{method.upper()} {path}",
            "change": "Endpoint/operation was removed"
        })

    for key in sorted(set(old_ops) & set(new_ops)):
        path, method = key
        old_op, new_op = old_ops[key], new_ops[key]
        location = f"{method.upper()} {path}"

        def params_by_key(op, spec):
            combined = {}
            # Operation-level parameters override path-level parameters.
            path_item = spec.get("paths", {}).get(path, {})
            for param in list(path_item.get("parameters", [])) + list(op.get("parameters", [])):
                if isinstance(param, dict) and "name" in param and "in" in param:
                    combined[(param["name"], param["in"])] = param
            return combined

        old_params = params_by_key(old_op, old_spec)
        new_params = params_by_key(new_op, new_spec)

        for pkey in sorted(set(old_params) - set(new_params)):
            name, where = pkey
            findings.append({
                "severity": "BREAKING",
                "location": f"{location} parameter '{name}' ({where})",
                "change": "Parameter was removed"
            })

        for pkey in sorted(set(old_params) & set(new_params)):
            name, where = pkey
            old_p, new_p = old_params[pkey], new_params[pkey]
            old_required = bool(old_p.get("required", False))
            new_required = bool(new_p.get("required", False))
            if not old_required and new_required:
                findings.append({
                    "severity": "BREAKING",
                    "location": f"{location} parameter '{name}' ({where})",
                    "change": "Optional parameter became required"
                })
            old_type = old_p.get("schema", {}).get("type")
            new_type = new_p.get("schema", {}).get("type")
            if old_type and new_type and old_type != new_type:
                findings.append({
                    "severity": "BREAKING",
                    "location": f"{location} parameter '{name}' ({where})",
                    "change": f"Parameter type changed from '{old_type}' to '{new_type}'"
                })

        old_resp = response_schema(old_op, old_spec)
        new_resp = response_schema(new_op, new_spec)
        if old_resp and new_resp:
            compare_properties(old_resp, new_resp, old_spec, new_spec,
                               f"{location} response", findings)

    # Added operations are normally backward-compatible.
    for key in sorted(set(new_ops) - set(old_ops)):
        path, method = key
        findings.append({
            "severity": "INFO",
            "location": f"{method.upper()} {path}",
            "change": "New endpoint/operation added (usually non-breaking)"
        })

    return findings


def main():
    parser = argparse.ArgumentParser(description="Compare two OpenAPI specifications.")
    parser.add_argument("old_spec", help="Old/baseline OpenAPI YAML or JSON file")
    parser.add_argument("new_spec", help="New/proposed OpenAPI YAML or JSON file")
    parser.add_argument("--output", help="Optional path to save the report as JSON")
    args = parser.parse_args()

    try:
        old_spec = load_spec(args.old_spec)
        new_spec = load_spec(args.new_spec)
        findings = compare_specs(old_spec, new_spec)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    report = {
        "old_version": old_spec.get("info", {}).get("version", "unknown"),
        "new_version": new_spec.get("info", {}).get("version", "unknown"),
        "breaking_change_count": sum(x["severity"] == "BREAKING" for x in findings),
        "findings": findings,
    }

    print(f"\nAPI Contract Breakage Report: {report['old_version']} -> {report['new_version']}")
    print("=" * 72)
    if not findings:
        print("No differences detected by this basic checker.")
    for index, item in enumerate(findings, 1):
        print(f"{index}. [{item['severity']}] {item['location']}")
        print(f"   {item['change']}")
    print(f"\nTotal findings: {len(findings)}")
    print(f"Potential breaking changes: {report['breaking_change_count']}")

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"JSON report saved to: {args.output}")


if __name__ == "__main__":
    main()
