"""Install a wheel into a disposable target and verify its bundled web application."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROBE = r'''
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

target, memory = map(Path, sys.argv[1:])
sys.path.insert(0, str(target))
import paperrule
from fastapi.testclient import TestClient
from paperrule.api.app import create_app

assert Path(paperrule.__file__).resolve().is_relative_to(target.resolve())
bundle = target / 'paperrule' / 'web'
assert (bundle / 'index.html').is_file()
with TestClient(create_app(memory)) as client:
    home = client.get('/')
    assert home.status_code == 200, home.status_code
    assert home.text == (bundle / 'index.html').read_text(encoding='utf-8')
    class AssetParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.assets = []

        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key in {'src', 'href'} and value and value.startswith('/assets/'):
                    self.assets.append(value)

    parser = AssetParser()
    parser.feed(home.text)
    assets = parser.assets
    assert assets, 'No production assets referenced by the installed workbench'
    for asset in assets:
        response = client.get(asset)
        assert response.status_code == 200, (asset, response.status_code)
        assert response.content == (bundle / asset.lstrip('/')).read_bytes()
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/rules').json() == []
    private = memory / 'attachments' / 'synthetic-private.txt'
    private.write_text('Synthetic private evidence.', encoding='utf-8')
    for url in ('/attachments/synthetic-private.txt', '/manifest.json', '/api/missing'):
        assert client.get(url).status_code == 404, url
print(json.dumps({'status': 'passed', 'installed_package': str(target),
                  'bundled_assets_checked': len(assets),
                  'dependency_mode': 'existing interpreter dependencies; not a clean environment'}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    parser.add_argument('--temporary-root', type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    temporary = args.temporary_root.resolve(strict=True)
    env = os.environ.copy()
    env.update(TEMP=str(temporary), TMP=str(temporary), PYTHONDONTWRITEBYTECODE='1',
               PIP_DISABLE_PIP_VERSION_CHECK='1')
    env.pop('PAPERRULE_WEB_ROOT', None)
    with tempfile.TemporaryDirectory(prefix='wheel-smoke-', dir=temporary) as folder:
        root = Path(folder)
        target = root / 'installed'
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index',
                        '--no-compile', '--no-cache-dir', '--target', str(target), str(wheel)],
                       cwd=root, env=env, check=True)
        subprocess.run([sys.executable, '-I', '-B', '-c', PROBE, str(target),
                        str(root / 'synthetic-memory')], cwd=root, env=env, check=True)


if __name__ == '__main__':
    main()
