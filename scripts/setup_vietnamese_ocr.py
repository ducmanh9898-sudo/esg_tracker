"""Fetch official Tesseract language data into this project, not system folders."""
from hashlib import sha256
import json
from pathlib import Path
import urllib.request
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / 'data/models/tesseract'
    folder.mkdir(parents=True, exist_ok=True)
    system_data = Path('C:/Program Files/Tesseract-OCR/tessdata')
    for relative in ('osd.traineddata', 'configs/tsv', 'configs/pdf'):
        source = system_data / relative
        destination = folder / relative
        if source.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    models = []
    for language in ('vie', 'eng'):
        url = f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{language}.traineddata'
        path = folder / f'{language}.traineddata'
        if not path.exists():
            with urllib.request.urlopen(url, timeout=90) as response:
                raw = response.read()
            if len(raw) < 100000:
                raise ValueError('Unexpected model response.')
            path.write_bytes(raw)
        models.append({'language': language, 'source': url, 'sha256': sha256(path.read_bytes()).hexdigest()})
    (folder / 'models.json').write_text(json.dumps(models, indent=2), encoding='utf-8')
    print(json.dumps(models, indent=2))


if __name__ == '__main__':
    main()
