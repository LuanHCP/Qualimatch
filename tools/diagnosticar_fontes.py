from qualimatch.database import init_db
from qualimatch.local_sync import get_sources, sync_source

init_db()
for s in get_sources():
    print(f"\n{s['contractor']} / {s['kind']}")
    print(' caminho:', s['path'])
    print(' existe :', s['exists'])
    if s['path'] and s['exists']:
        print(sync_source(s['contractor'], s['kind'], True))
