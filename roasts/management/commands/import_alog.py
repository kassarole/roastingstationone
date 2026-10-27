from pathlib import Path
from django.core.management.base import BaseCommand
from roasts.parser import parse_alog


class Command(BaseCommand):
    help = "Bulk-import .alog files from a directory"

    def add_arguments(self, parser):
        parser.add_argument("path", type=str)
        parser.add_argument("--recursive", action="store_true")

    def handle(self, *args, **options):
        root = Path(options["path"])
        pattern = "**/*.alog" if options["recursive"] else "*.alog"
        files = list(root.glob(pattern))
        self.stdout.write(f"Found {len(files)} file(s)")

        for f in files:
            try:
                with f.open("rb") as fh:
                    roast = parse_alog(fh)
                self.stdout.write(self.style.SUCCESS(f"OK  {f.name} -> {roast}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"ERR {f.name}: {e}"))
