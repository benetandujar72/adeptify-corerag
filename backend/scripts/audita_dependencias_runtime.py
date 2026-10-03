"""Audit dependency coordinates only; never transmit code, configuration or data."""
from __future__ import annotations
import argparse
import importlib.metadata as metadata
import json
import re
from pathlib import Path
import urllib.request
from packaging.requirements import Requirement
from packaging.markers import default_environment
from packaging.utils import canonicalize_name


def installed_inventory(files):
    pending, roots, errors, packages, visited = [], [], [], {}, set()
    for file in files:
        for line in Path(file).read_text(encoding="utf-8-sig").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            requirement = Requirement(line)
            roots.append(str(requirement))
            pending.append(requirement)
    environment = default_environment()
    while pending:
        requirement = pending.pop()
        key = canonicalize_name(requirement.name)
        if requirement.marker and not requirement.marker.evaluate(environment | {"extra": ""}):
            continue
        try:
            distribution = metadata.distribution(requirement.name)
        except metadata.PackageNotFoundError:
            errors.append({"package": requirement.name, "error": "not_installed"})
            continue
        version = distribution.version
        if requirement.specifier and not requirement.specifier.contains(version, prereleases=True):
            errors.append({"package": requirement.name, "version": version,
                           "error": "requirement_mismatch", "required": str(requirement.specifier)})
        packages[key] = {"name": distribution.metadata["Name"], "version": version}
        for extra in set(requirement.extras) | {""}:
            if (key, extra) in visited:
                continue
            visited.add((key, extra))
            for value in distribution.requires or []:
                dependency = Requirement(value)
                if not dependency.marker or dependency.marker.evaluate(environment | {"extra": extra}):
                    # The marker was evaluated for the owning distribution's extra.
                    dependency.marker = None
                    pending.append(dependency)
    return sorted(packages.values(), key=lambda p: p["name"].lower()), roots, errors, environment


def osv(packages):
    findings, errors = [], []
    for start in range(0, len(packages), 100):
        batch = packages[start:start + 100]
        body = {"queries": [{"package": {"ecosystem": "PyPI", "name": p["name"]},
                             "version": p["version"].split("+", 1)[0]} for p in batch]}
        request = urllib.request.Request("https://api.osv.dev/v1/querybatch",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                answers = json.load(response)["results"]
            if len(answers) != len(batch):
                raise ValueError("incomplete_batch")
            for package, answer in zip(batch, answers):
                if answer.get("vulns"):
                    findings.append(package | {"advisories": sorted(v["id"] for v in answer["vulns"])})
        except Exception as exc:
            errors.append({"offset": start, "count": len(batch), "error": type(exc).__name__})
    return findings, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", action="append", default=[])
    parser.add_argument("--pip-report")
    parser.add_argument("--resolved-lock")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if sum([bool(args.requirements), bool(args.pip_report), bool(args.resolved_lock)]) != 1:
        parser.error("choose installed requirements, complete pip report OR resolved UV lock")
    if args.resolved_lock:
        content = Path(args.resolved_lock).read_text(encoding="utf-8")
        if "uv pip compile" not in content or "--python-platform linux" not in content:
            parser.error("expected UV lock explicitly resolved for Linux")
        packages = []
        for line in content.splitlines():
            match = re.match(r"^([A-Za-z0-9_.-]+)==([^\\\s;]+)", line)
            if match:
                packages.append({"name": match[1], "version": match[2]})
            elif line.startswith("ca-core-news-md @ "):
                match = re.search(r"ca_core_news_md-([0-9.]+)-py3-none-any.whl", line)
                if not match:
                    parser.error("model coordinate is not versioned")
                packages.append({"name": "ca-core-news-md", "version": match[1]})
        roots, inventory_errors = [args.resolved_lock], []
        environment = {"target_platform": "Linux", "python_version": "3.11", "torch_backend": "CPU"}
        scope = "complete UV lock resolved with Linux markers, CPU Torch and hashes"
    elif args.pip_report:
        report = json.loads(Path(args.pip_report).read_text(encoding="utf-8-sig"))
        packages = [{"name": p["metadata"]["name"], "version": p["metadata"]["version"]}
                    for p in report["install"]]
        roots, inventory_errors, environment = [], [], report.get("environment", {})
        scope = "resolved pip report (must include --ignore-installed for full closure)"
    else:
        packages, roots, inventory_errors, environment = installed_inventory(args.requirements)
        scope = "installed dependency closure of requested roots and extras; native environment markers"
    findings, network_errors = osv(packages)
    data = {"scope": scope, "environment": environment, "roots": roots,
            "packages": packages, "package_count": len(packages), "findings": findings,
            "inventory_errors": inventory_errors, "network_errors": network_errors,
            "complete": not inventory_errors and not network_errors}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"packages": len(packages), "findings": len(findings),
                      "inventory_errors": len(inventory_errors), "network_errors": len(network_errors)}))
    return 2 if inventory_errors or network_errors else 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
