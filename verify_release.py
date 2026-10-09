"""Read-only release gate. Findings never print matched credential values."""
from pathlib import PurePosixPath
import argparse
import hashlib
import re
import subprocess

from package_release import release_files

RULES = {
    'provider-key': re.compile(rb'\bsk-[A-Za-z0-9_-]{24,}'),
    'github-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'literal-service-key': re.compile(rb'''(?:BAIDU_MAP_AK|DEEPSEEK_API_KEY|OPENAI_API_KEY)\s*[=:]\s*["'][A-Za-z0-9_-]{20,}["']'''),
    'credential-url': re.compile(rb'https?://[^\s/@:]{1,128}:[^\s/@]{1,256}@'),
}
BLOCKED_PARTS = {'data', '.git', '__pycache__', 'node_modules', 'releases'}
BLOCKED_SUFFIXES = {'.pem', '.key', '.sqlite3', '.db', '.tif', '.tiff', '.log', '.pyc'}
# Reviewed synthetic URL-rejection fixtures only. Both path and exact value hash
# must match; neither the whole test directory nor new credentials are exempt.
SYNTHETIC_URLS = {
    'tests/agent-context.test.mjs': '093866188144b0216fb125431572e8ac2df8980dfeeb6ebeb3d9f3987d1e4c1d',
    'tests/test_agent_evidence.py': 'c604d4eecc9010177eb941b7d66cc680b44732bbfee77bce699072713037e370',
    'tests/test_campus_content.py': 'ec25b8fa54a9d7a878a86e6f38233af24d5d27d184b396136d6d7f0251d33c19',
}


def check(name, raw):
    path = PurePosixPath(name)
    findings = []
    if any(p.lower() in BLOCKED_PARTS for p in path.parts) or path.name.startswith('.env') or path.suffix.lower() in BLOCKED_SUFFIXES:
        findings.append((name, 'private-path', 0))
    if len(raw) >= 100 * 1024 * 1024:
        findings.append((name, 'file-size-limit', 0))
    for rule, pattern in RULES.items():
        for match in pattern.finditer(raw):
            if rule == 'credential-url' and SYNTHETIC_URLS.get(name) == hashlib.sha256(match.group()).hexdigest():
                continue
            findings.append((name, rule, raw[:match.start()].count(b'\n') + 1))
    return findings


def audit(staged=False):
    if staged:
        names = subprocess.check_output(['git', 'ls-files', '-z']).decode('utf-8').split('\0')
        entries = ((name, subprocess.check_output(['git', 'show', ':' + name])) for name in names if name)
    else:
        entries = ((name, path.read_bytes()) for path, name in release_files())
    findings, count, size = [], 0, 0
    for name, raw in entries:
        count += 1
        size += len(raw)
        findings.extend(check(name, raw))
    for name, rule, line in findings:
        print(f'BLOCK {name}:{line} [{rule}]')
    print(f'{"INDEX" if staged else "PACKAGE"}: {count} files; {size} bytes; {len(findings)} findings')
    return int(bool(findings))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Scan the entire Git index, not only changed files')
    raise SystemExit(audit(parser.parse_args().staged))
