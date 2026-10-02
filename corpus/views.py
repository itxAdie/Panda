"""Views: the conversational answer surface.

One question in, sourced facts out. Two rules govern everything here:

  1. Every returned fact carries its source URL, its raw quote and its as_of date.
  2. A query with no supporting evidence returns a coverage disclosure that says
     what was searched. It never says the property or condition does not exist.
"""

import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from corpus import query as Q
from corpus.resolver import Resolver

# Seeded from real pages the corpus actually contains. Shown as clickable chips so a
# first-time user can see the shape of a question without reading instructions.
EXAMPLES = [
    "10 marla allocation under 55 lac in DHA Phase 10",
    "balloting status in DHA Phase 10",
    "4 marla affidavit in DHA Phase 9 Town",
    "fees in DHA Phase 6",
]


@require_GET
def search_page(request):
    """The landing page: the hero.

    Tab counts come from the corpus, never from a literal, so a type with nothing
    stored reports 0 instead of quietly disappearing.
    """
    rows = Q.type_counts()
    coverage = Q.coverage_of(None)
    tabs = [{"key": "__all", "label": "All", "count": sum(r["count"] for r in rows)}] + rows
    return render(request, "corpus/search.html", {
        "tabs": tabs,
        "coverage": coverage,
        "examples": EXAMPLES,
    })


@require_POST
@csrf_exempt
def search_api(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "expected JSON body"}, status=400)
    text = (payload.get("q") or "").strip()
    if not text:
        return JsonResponse({"error": "empty query"}, status=400)

    fact_type = payload.get("type") or None
    resolver = Resolver()
    q, facts, coverage = Q.search(text, resolver=resolver, fact_type=fact_type)

    if not facts:
        body = Q.no_evidence_answer(q, coverage)
        body["query"] = text
        body["active_type"] = fact_type or "__all"
        body["parsed"] = {
            "place_ref": q.place_ref,
            "place": q.place.canonical_name if q.place else None,
            "size_marla": q.size_marla,
            "file_type": q.file_type,
            "budget_pkr": q.budget_pkr,
            "notes": q.notes,
        }
        return JsonResponse(body, status=200)

    return JsonResponse({
        "kind": "evidence",
        "query": text,
        "parsed": {
            "place_ref": q.place_ref,
            "place": q.place.canonical_name if q.place else None,
            "size_marla": q.size_marla,
            "file_type": q.file_type,
            "budget_pkr": q.budget_pkr,
            "notes": q.notes,
        },
        "count": len(facts),
        "active_type": fact_type or "__all",
        "facts": [Q.serialize_fact(f) for f in facts],
        "coverage": coverage,
    })


@require_GET
def health(request):
    return HttpResponse("ok")