from django.core.management.base import BaseCommand
from django.utils import timezone

from roasts.models import BeanInfo
from roasts.services.sweetmarias import fetch_green_coffee


class Command(BaseCommand):
    help = "Scrape Sweet Maria's green coffee collection into BeanInfo."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **options):
        products = fetch_green_coffee()
        self.stdout.write(f"Fetched {len(products)} green coffees.")

        seen_ids = set()
        created = updated = 0
        now = timezone.now()

        for data in products:
            seen_ids.add(data["shopify_id"])

            if dry_run:
                self.stdout.write(
                    f"  [dry-run] {data['name']} — ${data['price']} "
                    f"({data['origin']}, {data['process']})"
                )
                continue

            # Fetch existing to preserve manual entries if the parser returns blank
            existing = BeanInfo.objects.filter(shopify_id=data["shopify_id"]).first()

            # Determine fields to update. We use the scraped data as defaults,
            # but if the scrape is empty and we have existing manual data, we keep the manual data.
            defaults = {
                "shopify_handle": data["shopify_handle"],
                "name": data["name"],
                "sweetmarias_url": data["sweetmarias_url"],
                "price": data["price"],
                "available": data["available"],
                "body_html": data["body_html"],
                "description": data["description"],
                "tags": data["tags"],
                "variant_prices": data["variant_prices"],
                "last_scraped": now,
            }

            # For these fields, only overwrite if the scrape actually found something
            parsed_fields = ["origin", "process", "roast_recommendation", "flavor_keywords"]
            for field in parsed_fields:
                if data[field]:
                    defaults[field] = data[field]
                elif existing and getattr(existing, field):
                    # Keep the existing manual entry
                    pass
                else:
                    # Both empty, just set to blank
                    defaults[field] = ""

            obj, was_created = BeanInfo.objects.update_or_create(
                shopify_id=data["shopify_id"],
                defaults=defaults,
            )

            if was_created:
                created += 1
            else:
                updated += 1

        if not dry_run:
            # Mark scraped-but-now-missing beans as unavailable.
            BeanInfo.objects.filter(
                shopify_id__isnull=False
            ).exclude(
                shopify_id__in=seen_ids
            ).update(available=False)

            self.stdout.write(self.style.SUCCESS(
                f"Created {created}, updated {updated}."
            ))