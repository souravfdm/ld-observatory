"""Daily job: download both KoboToolbox projects (synchronous XLSX exports) and rebuild docs/data.json.

Needs three secrets (GitHub → Settings → Secrets and variables → Actions):
  KOBO_TOKEN      your KoboToolbox API key
  KOBO_NORTH_URL  data_url_xlsx link of the North project's named export
  KOBO_SOUTH_URL  data_url_xlsx link of the South project's named export
If anything goes wrong the old data.json is kept, so the website never breaks.
"""
import os, sys, json, time, tempfile, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
import ld_pipeline

def download(url, token, path):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'Authorization': f'Token {token}', 'User-Agent': 'ld-observatory-updater'})
            with urllib.request.urlopen(req, timeout=180) as r, open(path, 'wb') as f:
                f.write(r.read())
            with open(path, 'rb') as f:
                if f.read(2) != b'PK':
                    raise ValueError('response is not an XLSX file: check the URL and token')
            return
        except Exception as e:
            print(f'  attempt {attempt+1} failed: {e}')
            time.sleep(20 * (attempt + 1))
    sys.exit(f'Could not download {url}')

def main():
    token = os.environ.get('KOBO_TOKEN'); north = os.environ.get('KOBO_NORTH_URL'); south = os.environ.get('KOBO_SOUTH_URL')
    if not (token and north and south):
        sys.exit('Missing secrets: KOBO_TOKEN, KOBO_NORTH_URL and KOBO_SOUTH_URL are required.')
    tmp = tempfile.mkdtemp()
    n, s = os.path.join(tmp, 'north.xlsx'), os.path.join(tmp, 'south.xlsx')
    print('Downloading North…'); download(north, token, n)
    print('Downloading South…'); download(south, token, s)
    try:
        out = ld_pipeline.build(n, s)
    except KeyError as e:
        sys.exit(f'Export format changed: column {e} not found. Use English labels, XLS, "Include groups in headers" OFF (see README).')
    total = sum(out['meta']['households'].values())
    if total < 100:
        sys.exit(f'Only {total} households found: refusing to overwrite the dashboard.')
    dst = os.path.join(os.path.dirname(__file__), '..', 'docs', 'data.json')
    with open(dst, 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f'Updated data.json: {total} households, {out["meta"]["events"]} events.')

if __name__ == '__main__':
    main()
