"""Rebuild the beta from a clean Japanese ROM or ZIP (Windows)."""
import argparse,sys,subprocess,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('source',type=Path)
args=parser.parse_args()
source=args.source.resolve()
sys.path.insert(0,str(root/'builder'))
sys.argv=['build.py','--full-draft']
import build
if source.suffix.lower()=='.zip':
 build.SOURCE=root/'__no_source_rom__.nds';build.SOURCE_ZIP=source
else:build.SOURCE=source
expected=json.loads((root/'verification.json').read_text())
assert hashlib.sha256(build.read_source_bytes()).hexdigest()==expected['source_sha256'],'Source ROM checksum mismatch'
subprocess.run([sys.executable,str(root/'builder/extract_rom.py'),str(source)],check=True)
(root/'builder/qa/full_audit').mkdir(parents=True,exist_ok=True)
build.main()
assert hashlib.sha256(build.OUTPUT.read_bytes()).hexdigest()==expected['target_sha256'],'Rebuild differs from release'
assert hashlib.sha256(build.PATCH.read_bytes()).hexdigest()==expected['patch_sha256'],'Patch differs from release'
print('Verified: ROM and patch match the published checksums.')
