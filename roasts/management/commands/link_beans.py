from django.core.management.base import BaseCommand
from roasts.models import Roast, BeanInfo


def _match_bean_info(display_name, beans_str):
    """Same matching logic used in parser.py."""
    if not display_name:
        return None
    # Exact match
    match = BeanInfo.objects.filter(name__iexact=display_name).first()
    if match:
        return match
    # Partial match — only if the bean name is unique
    candidates = BeanInfo.objects.filter(name__icontains=display_name)
    if candidates.count() == 1:
        return candidates.first()
    # Reverse partial: bean name contains a BeanInfo name
    for bi in BeanInfo.objects.all():
        if bi.name and bi.name.lower() in display_name.lower():
            return bi
    return None


class Command(BaseCommand):
    help = "Re-match existing roasts to BeanInfo records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-match even roasts that already have a bean_info link",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving",
        )

    def handle(self, *args, **options):
        force = options["force"]
        dry_run = options["dry_run"]

        qs = Roast.objects.all()
        if not force:
            qs = qs.filter(bean_info__isnull=True)

        total = qs.count()
        self.stdout.write(f"Processing {total} roast(s)...")

        matched = 0
        unmatched = 0

        for roast in qs:
            bean = _match_bean_info(roast.beans, roast.beans)
            if bean:
                matched += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {roast.uuid}  {roast.beans!r}  ->  {bean.name}"
                    )
                )
                if not dry_run:
                    roast.bean_info = bean
                    fields = ["bean_info"]
                    # Also backfill origin if missing
                    if not roast.origin and bean.origin:
                        roast.origin = bean.origin
                        fields.append("origin")
                    roast.save(update_fields=fields)
            else:
                unmatched += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  {roast.uuid}  {roast.beans!r}  ->  (no match)"
                    )
                )

        verb = "Would match" if dry_run else "Matched"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{verb} {matched} / {total}, unmatched: {unmatched}"
            )
        )