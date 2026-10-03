"""Verify production asset paths, dimensions, alpha and compressed art budget."""
import json
from pathlib import Path
from PIL import Image
p=Path(__file__).resolve().parents[1]
entries=json.loads((p/'assets/manifest.json').read_text())
for entry in entries:
 image=Image.open(p/'frontend/public/art'/entry['filename'])
 if 'dimensions' in entry: assert image.size==tuple(entry['dimensions']),entry['filename']
 if entry.get('frames'):assert image.width==entry['frames']*entry['frame_size'][0]
assert Image.open(p/'frontend/public/art/courier-idle.png').mode=='RGBA'
size=sum(f.stat().st_size for f in (p/'frontend/public/art').iterdir())
assert size<600*1024,(size,'art budget exceeded')
print(f'PASS {len(entries)} manifest entries; {size} compressed decorative bytes')
