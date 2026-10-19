"""Read-only timings of the local database queries; no document contents printed."""
import cProfile
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qualimatch import queries, management
from qualimatch.database import backend_name

print('Database:', backend_name(), flush=True)
checks = {
    'dashboard': queries.dashboard,
    'certificates': lambda: queries.list_certificates(limit=25),
    'certificate_filters': queries.certificate_filter_options,
    'contractor_pending': queries.contractor_pending_measurements,
    'notifications': lambda: management.notification_summary({'role': 'ADMIN'}),
}
for name, fn in checks.items():
    profile = cProfile.Profile()
    start = time.perf_counter()
    profile.runcall(fn)
    print(f'{name}: {time.perf_counter() - start:.3f}s', flush=True)
    if '--profile' in sys.argv:
        pstats.Stats(profile).strip_dirs().sort_stats('cumulative').print_stats(8)
