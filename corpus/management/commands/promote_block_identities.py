"""Promotion rule: a BlockIdentity may only become verified with 2+ sources.

An identity named by a single publisher is useful but is not corroborated. This
command is the ONLY path to verified=True, and it refuses single-source identities.

Usage:
  python3 manage.py promote_block_identities --report
  python3 manage.py promote_block_identities --apply
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from corpus.models import BlockIdentity


class Command(BaseCommand):
    help = "Promote BlockIdentity rows to verified when >=2 independent sources agree."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Write changes. Without it, this is a dry run.")
        parser.add_argument("--report", action="store_true", help="Print the audit.")

    @transaction.atomic
    def handle(self, *args, **opts):
        apply = opts.get("apply")
        total = BlockIdentity.objects.count()
        promotable = [b for b in BlockIdentity.objects.all() if b.source_count >= 2 and not b.verified]
        blocked = [b for b in BlockIdentity.objects.all() if b.source_count < 2]

        self.stdout.write("")
        self.stdout.write(f"  block identities        {total}")
        self.stdout.write(f"  verified (>=2 sources)  {sum(1 for b in BlockIdentity.objects.all() if b.verified)}")
        self.stdout.write(f"  promotable now          {len(promotable)}")
        self.stdout.write(f"  blocked single-source   {len(blocked)}")
        conflicts = [b for b in BlockIdentity.objects.all() if b.label_conflict]
        self.stdout.write(f"  label conflicts         {len(conflicts)}  (recorded, never interpreted)")
        self.stdout.write("")
        for b in blocked[:8]:
            self.stdout.write(f"    BLOCKED {b}  sources={[s.slug for s in b.sources.all()]}")
        if len(blocked) > 8:
            self.stdout.write(f"    ... and {len(blocked) - 8} more")
        self.stdout.write("")
        if apply:
            for b in promotable:
                b.verified = True
                b.full_clean()   # enforces the promotion rule
                b.save()
            self.stdout.write(self.style.SUCCESS(f"promoted {len(promotable)}"))
        else:
            self.stdout.write("  dry run — pass --apply to promote")
