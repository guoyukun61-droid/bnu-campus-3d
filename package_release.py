"""Build a local, private-review release. Never uploads or copies runtime data."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parent
CURRENT_OUTPUT = {
    'bnu_campus_web_white_v7.glb', 'bnu_campus_white_v7.blend', 'main-repair-v7.json',
    'bnu_campus_web_white_v6.glb', 'bnu_campus_white_v6.blend', 'scene_manifest_white_v6.json',
    'bnu_campus_web_white_v5.glb', 'bnu_campus_white_v5.blend', 'scene_manifest_white_v5.json',
    'bnu_campus_web_white_v4.glb', 'bnu_campus_white_v4.blend',
    'bnu_campus_web_v5.glb', 'bnu_campus_web_v6.glb',
    'scene_manifest_white_v4.json', 'scene_manifest_v5.json',
    'scene_manifest_v6.json', 'white_v4_spatial_checks.json',
}
PUBLIC_DIRS = {'assets', 'vendor', 'white', 'reference', 'recognition', 'information', 'contribute', 'backend', 'docs', 'tests', 'app'}
SUFFIXES = {'.html', '.js', '.cjs', '.mjs', '.css', '.json', '.png', '.jpg', '.jpeg',
            '.webp', '.svg', '.md', '.txt', '.py', '.ps1', '.cmd', '.map'}
NOTICE_NAMES = {'LICENSE', 'LICENCE', 'NOTICE', 'COPYING'}


def permitted(rel):
    if any(p.startswith('.') or p == '__pycache__' for p in rel.parts):
        return rel.as_posix() == '.gitignore'
    if len(rel.parts) == 1:
        return rel.suffix.lower() in SUFFIXES or rel.name in {'VERSION'} | NOTICE_NAMES
    if rel.parts[0] == 'output':
        return len(rel.parts) == 2 and rel.name in CURRENT_OUTPUT
    return rel.parts[0] in PUBLIC_DIRS and (rel.suffix.lower() in SUFFIXES or rel.name.upper() in NOTICE_NAMES)

def release_files():
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if permitted(rel):
            yield path, rel.as_posix()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='', help='Keep an earlier local draft; create a separately named reviewed archive')
    args = parser.parse_args()
    if args.revision and not re.fullmatch(r'[a-z0-9-]+', args.revision):
        raise ValueError('Invalid archive revision')
    version = (ROOT/'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid VERSION')
    files = list(release_files())
    required = {'index.html', 'white/index.html', 'campus_server.py',
                'assets/campus_assets_white_v6.json', 'output/bnu_campus_web_white_v6.glb',
                'app/explore/index.html', 'output/bnu_campus_web_white_v7.glb', 'vendor/three/LICENSE'}
    if not required.issubset({name for _, name in files}):
        raise ValueError('Required release files missing')
    destination = ROOT/'releases'
    destination.mkdir(exist_ok=True)
    stem = f'bnu-campus-v{version}' + (f'-{args.revision}' if args.revision else '')
    archive = destination/f'{stem}.zip'
    manifest = destination/f'{stem}.manifest.json'
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
