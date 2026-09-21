"""Build a local, private-review release. Never uploads or copies runtime data."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parent
CURRENT_OUTPUT = {
    'bnu_campus_web_white_v4.glb', 'bnu_campus_white_v4.blend',
    'bnu_campus_web_v5.glb', 'bnu_campus_web_v6.glb',
    'scene_manifest_white_v4.json', 'scene_manifest_v5.json',
    'scene_manifest_v6.json', 'white_v4_spatial_checks.json',
}
PUBLIC_DIRS = {'assets', 'vendor', 'white', 'reference', 'recognition', 'information'}
SUFFIXES = {'.html', '.js', '.cjs', '.css', '.json', '.png', '.jpg', '.jpeg',
            '.webp', '.svg', '.md', '.txt', '.py', '.ps1', '.cmd', '.map'}

def release_files():
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(p.startswith('.') or p == '__pycache__' for p in rel.parts):
            if rel.as_posix() != '.gitignore':
                continue
        if len(rel.parts) == 1:
            allowed = path.suffix.lower() in SUFFIXES or path.name in {'VERSION', '.gitignore'}
        elif rel.parts[0] == 'output':
            allowed = len(rel.parts) == 2 and path.name in CURRENT_OUTPUT
        else:
            allowed = rel.parts[0] in PUBLIC_DIRS and path.suffix.lower() in SUFFIXES
        if allowed:
            yield path, rel.as_posix()

def main():
    version = (ROOT/'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid VERSION')
    files = list(release_files())
    required = {'index.html', 'white/index.html', 'campus_server.py',
                'assets/campus_assets_white_v4.json', 'output/bnu_campus_web_white_v4.glb'}
    if not required.issubset({name for _, name in files}):
        raise ValueError('Required release files missing')
    destination = ROOT/'releases'
    destination.mkdir(exist_ok=True)
    archive = destination/f'bnu-campus-v{version}.zip'
    manifest = destination/f'bnu-campus-v{version}.manifest.json'
    if archive.exists() or manifest.exists():
        raise FileExistsError('Release already exists; do not overwrite it. Update VERSION first.')
    entries = []
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path, name in files:
            raw = path.read_bytes()
            if len(raw) >= 100 * 1024 * 1024:
                raise ValueError(f'GitHub file size threshold: {name}')
            bundle.writestr(f'bnu-campus-v{version}/{name}', raw)
            entries.append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError('Archive integrity check failed')
    manifest.write_text(json.dumps({'version': version, 'visibility': 'private-review-only',
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'files': entries},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'v{version}: {len(entries)} files; {archive.stat().st_size} bytes; ZIP verified')

if __name__ == '__main__':
    main()
