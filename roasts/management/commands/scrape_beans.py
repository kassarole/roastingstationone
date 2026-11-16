from django.core.management.base import BaseCommand
from django.utils import timezone

from roasts.models import BeanInfo
from roasts.services import sweetmarias, thetaridge


class Command(BaseCommand):
    help = "Scrape green coffee from Sweet Maria's and Theta Ridge into BeanInfo."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **options):
        now = timezone.now()

        # 1. Scrape Sweet Maria's
        self.stdout.write("Scraping Sweet Maria's...")
        sm_products = sweetmarias.fetch_green_coffee()
        self._process_products(sm_products, "sweetmarias", now, dry_run)

        # 2. Scrape Theta Ridge
        self.stdout.write("Scraping Theta Ridge...")
        tr_products = thetaridge.fetch_thetaridge()
        self._process_products(tr_products, "thetaridge", now, dry_run)

    def _process_products(self, products, source_name, now, dry_run):
        self.stdout.write(f"Fetched {len(products)} products from {source_name}.")
        
        seen_ids = set()
        created = updated = 0

        for data in products:
            seen_ids.add(data["shopify_id"])

            if dry_run:
                self.stdout.write(f"  [dry-run] [{source_name}] {data['name']} — ${data['price']}")
                continue

            # Fetch existing to preserve manual entries if the parser returns blank
            existing = BeanInfo.objects.filter(
                shopify_id=data["shopify_id"], source=source_name
            ).first()

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
                "source": source_name,
            }

            # Preserve manual data if the scraper didn't find anything
            # Preserve manual data if the scraper didn't find anything
            parsed_fields = ["origin", "process", "cultivar", "roast_recommendation", "flavor_keywords"]
            for field in parsed_fields:
                if data.get(field):
                    # Enforce a max length of 255 to prevent DB errors
                    defaults[field] = str(data[field])[:255]
                elif existing and getattr(existing, field):
                    pass 
                else:
                    defaults[field] = ""

            obj, was_created = BeanInfo.objects.update_or_create(
                shopify_id=data["shopify_id"],
                source=source_name,
                defaults=defaults,
            )

            if was_created:
                created += 1
            else:
                updated += 1

        if not dry_run:
            # Mark missing items from THIS SPECIFIC SOURCE as unavailable
            BeanInfo.objects.filter(
                source=source_name, shopify_id__isnull=False
            ).exclude(
                shopify_id__in=seen_ids
            ).update(available=False)

            self.stdout.write(self.style.SUCCESS(
                f"[{source_name}] Created {created}, updated {updated}."
            ))