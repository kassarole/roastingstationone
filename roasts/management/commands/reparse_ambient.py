from django.core.management.base import BaseCommand

from roasts.models import Roast


class Command(BaseCommand):
    help = "Restore ambient_temp from raw['ambientTemp'] (Artisan stores °F)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--uuid", action="append", default=None)
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--tolerance", type=float, default=1e-6)

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]
        tol = opts["tolerance"]

        qs = Roast.objects.all().order_by("id")
        if opts["uuid"]:
            qs = qs.filter(uuid__in=opts["uuid"])
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        total = qs.count()
        self.stdout.write(f"Scanning {total} roast(s)...")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be saved."))

        changed = same = no_raw = no_ambient = 0
        for roast in qs.iterator():
            raw_ambient = (roast.raw or {}).get("ambientTemp")
            if raw_ambient is None:
                no_ambient += 1
                continue

            try:
                new_value = float(raw_ambient)
            except (TypeError, ValueError):
                self.stderr.write(
                    self.style.ERROR(
                        f"[{roast.uuid}] non-numeric ambientTemp={raw_ambient!r}"
                    )
                )
                continue

            old_value = roast.ambient_temp
            matches = (
                old_value is not None
                and abs(old_value - new_value) <= tol
            )
            if matches:
                same += 1
                continue

            changed += 1
            self.stdout.write(
                f"[{roast.uuid}] ambient: {old_value!r} -> {new_value!r} °F"
            )
            if not dry_run:
                roast.ambient_temp = new_value
                roast.save(update_fields=["ambient_temp"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done."))
        self.stdout.write(f"  scanned:           {total}")
        self.stdout.write(f"  {'would change' if dry_run else 'changed'}:        {changed}")
        self.stdout.write(f"  already correct:   {same}")
        self.stdout.write(f"  no ambientTemp:    {no_ambient}")
        if dry_run and changed:
            self.stdout.write(
                self.style.WARNING("\nRe-run without --dry-run to apply.")
            )