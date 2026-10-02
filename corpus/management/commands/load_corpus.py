"""Load the hand-authored corpus map from CSV into the database.

The CSVs in data/normalization/ are the source of truth, authored by hand with
evidence. This command is idempotent and re-runnable.
"""

import csv
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction

from corpus.models import (
    EVIDENCE_CONTESTED, EVIDENCE_EVIDENCED, EVIDENCE_UNEVIDENCED,
    Alias, BlockIdentity, Drop, FactTypeCue, Measurement, Place, Society, Source,
)

DATA = Path(__file__).resolve().parents[3] / "data"

SOURCES = [
    # slug, name, url, verified, channel, note
    ("maanestate", "MAAN ESTATE", "https://maanestate.com/", True, "ai_hub",
     "119-line crawl policy, Crawl-delay 10. Pages 403; use published AI hub."),
    ("asasproperties", "ASAS Properties", "https://asaspropertiespk.com/", True, "live", ""),
    ("lahorerealestate", "Lahore Real Estate", "https://lahorerealestate.com/", True, "live", ""),
    ("elegantdha", "Elegant DHA", "https://elegantdha.com/", True, "live", "ToS page is Lorem ipsum placeholder."),
    ("lexform", "LexForm", "https://lex-form.com/", True, "live", ""),
    ("dharealestate", "DHA Real Estate.pk", "https://dharealestate.pk/", True, "live", ""),
    ("mohsinestate", "mohsinestate.com", "https://mohsinestate.com/", True, "live",
     "Allowlists AI UAs; labels same objects both Block and Sector."),
    ("cdbrealestate", "CDB Properties", "https://cdbrealestate.com/", True, "live", ""),
    ("milkiyat", "milkiyat.com", "https://milkiyat.com/", True, "live", "Islamabad-weighted corpus."),
    ("burstforum", "Burstforum", "https://burstforum.com/", True, "live", "Askari 10 only."),
]

STATUS_MAP = {"evidenced": EVIDENCE_EVIDENCED, "contested": EVIDENCE_CONTESTED,
              "unevidenced": EVIDENCE_UNEVIDENCED}


def _rows(name):
    p = DATA / "normalization" / name
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class Command(BaseCommand):
    help = "Load the hand-authored entity map from data/normalization/*.csv"

    @transaction.atomic
    def handle(self, *args, **opts):
        for slug, name, url, verified, channel, note in SOURCES:
            Source.objects.update_or_create(slug=slug, defaults=dict(
                name=name, base_url=url, verified=verified, channel=channel, notes=note))

        # societies first, then phases/blocks/sectors (parents may precede children)
        ent = _rows("entity.csv")
        by_id = {}
        for e in ent:
            society_slug = "soc_dha_lahore"
            cid = e["canonical_id"]
            if cid == "soc_dha_lahore":
                society_slug = "soc_dha_lahore"
            soc, _ = Society.objects.get_or_create(
                slug=society_slug,
                defaults={"canonical_name": "DHA Lahore", "city": "Lahore"})
            by_id[cid] = (soc, None)

        # societies other than DHA
        soc_by_level = {}
        for cid, (soc, _) in by_id.items():
            row = next(r for r in ent if r["canonical_id"] == cid)
            if row["level"] == "society" and cid != "soc_dha_lahore":
                s, _ = Society.objects.get_or_create(
                    slug=cid, defaults={"canonical_name": row["canonical_name"], "city": row["city"]})
                soc_by_level[cid] = s

        # two passes so parents exist before children
        for _ in range(3):
            for e in ent:
                cid = e["canonical_id"]
                if cid in by_id and by_id[cid][1] is not None:
                    continue
                if e["level"] == "society":
                    soc = soc_by_level.get(cid) or Society.objects.first()
                else:
                    # society scope comes from the topmost non-null ancestor
                    anc = (e.get("parent_id") or "").strip()
                    soc = Society.objects.get(slug="soc_dha_lahore")
                    for _ in range(4):
                        if anc in soc_by_level:
                            soc = soc_by_level[anc]
                            break
                        arow = next((r for r in ent if r["canonical_id"] == anc), None)
                        if arow is None:
                            break
                        anc = (arow.get("parent_id") or "").strip()
                parent = None
                pid = (e.get("parent_id") or "").strip()
                if pid and pid in by_id and by_id[pid][1] is not None:
                    parent = by_id[pid][1]
                elif pid and pid in by_id:
                    continue
                status = STATUS_MAP.get(e.get("evidence_status", ""), EVIDENCE_EVIDENCED)
                place, _ = Place.objects.update_or_create(
                    society=soc, canonical_name=e["canonical_name"],
                    defaults=dict(level=e["level"], parent=parent,
                                  evidence_url=e.get("evidence_url", ""),
                                  evidence=e.get("evidence", ""),
                                  evidence_status=status,
                                  is_contested=(status == EVIDENCE_CONTESTED)))
                by_id[cid] = (soc, place)

        def _place_for_entity(target):
            """Resolve an entity.csv row to its Place, honouring society scope."""
            if target is None:
                return None
            if target["level"] == "society":
                return Place.objects.filter(
                    society__slug=target["canonical_id"],
                    canonical_name=target["canonical_name"]).first()
            soc_slug = target["parent_id"] if target.get("parent_id") in soc_by_level else "soc_dha_lahore"
            return Place.objects.filter(
                society__slug=soc_slug, canonical_name=target["canonical_name"],
                level=target["level"]).first()

        for a in _rows("alias.csv"):
            target = next((r for r in ent if r["canonical_id"] == a["canonical_id"]), None)
            place = _place_for_entity(target)
            if place is None:
                self.stderr.write(f"  !! alias target missing: {a['alias_text']} -> {a['canonical_id']}")
                continue
            Alias.objects.update_or_create(alias_text=a["alias_text"], place=place, defaults=dict(
                evidence=a.get("evidence", ""), evidence_url=a.get("evidence_url", ""),
                confirmed=a.get("confirmed", "").lower() == "true"))

        for d in _rows("drop.csv"):
            src_slug = (d.get("source_id") or "").split(";")[0].strip()
            src = Source.objects.filter(slug=src_slug).first()
            Drop.objects.update_or_create(alias_text=d["alias_text"], defaults=dict(
                reason=d.get("reason", ""), source=src,
                evidence_state=d.get("evidence_state", "confirmed"),
                evidence_note=d.get("evidence_note", "")))

        for m in _rows("measurement.csv"):
            Measurement.objects.update_or_create(source_form=m["source_form"], defaults=dict(
                dimension=m["dimension"], canonical_value=m["canonical_value"],
                unit=m.get("unit", ""), notes=m.get("notes", "")))

        from corpus.validators import reset_cue_cache
        for c in _rows("fact_type_cues.csv"):
            FactTypeCue.objects.update_or_create(
                fact_type=c["fact_type"], cue=c["cue"],
                defaults=dict(group=c["group"],
                              corpus_count=int(c.get("corpus_count") or 0),
                              proven_in_corpus=c["proven_in_corpus"] == "yes"))
        reset_cue_cache()

        # block identities: flat (phase, letter), source-scoped, never hierarchical
        for b in _rows("block_identity.csv"):
            phase = Place.objects.filter(canonical_name__iexact=b["phase"], level="phase").first()
            if phase is None:
                self.stderr.write(f"  !! block identity phase missing: {b['phase']}")
                continue
            # Corpus fixtures use short source codes; Source uses full slugs.
            CODE = {"lre": "lahorerealestate", "moh": "mohsinestate", "cdb": "cdbrealestate",
                    "dha": "dharealestate", "burst": "burstforum", "milk": "milkiyat",
                    "asas": "asasproperties", "elegant": "elegantdha", "lex": "lexform",
                    "maan": "maanestate"}
            srcs = []
            for x in b["sources"].split(";"):
                slug = CODE.get(x.strip(), x.strip())
                src = Source.objects.filter(slug=slug).first()
                if src is None:
                    self.stderr.write(f"  !! unknown source slug {slug!r} in block_identity.csv")
                else:
                    srcs.append(src)
            count = len(srcs)
            bi, _ = BlockIdentity.objects.update_or_create(
                phase=phase, letter=b["letter"],
                defaults=dict(labels_observed=b["labels_observed"],
                              source_count=count,
                              single_source=(count < 2),
                              verified=(count >= 2),
                              occurrences=int(b.get("occurrences") or 0)))
            bi.sources.set(srcs)

        self.stdout.write(self.style.SUCCESS(
            f"loaded sources={Source.objects.count()} societies={Society.objects.count()} "
            f"places={Place.objects.count()} aliases={Alias.objects.count()} "
            f"drops={Drop.objects.count()} measurements={Measurement.objects.count()} "
            f"block_identities={BlockIdentity.objects.count()} "
            f"cues={FactTypeCue.objects.count()}"))