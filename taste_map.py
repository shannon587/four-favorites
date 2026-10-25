#!/usr/bin/env python3
"""Four Favorites.

A small, accessibility-first command-line tool that uses the Qloo Taste AI
API to map one person's taste across four lanes: books, film, music, and
places.

You name one favorite in each lane. The tool resolves each name to a Qloo
entity, uses the whole set as a taste signal, and asks Qloo what fits that
taste in every lane. The result is printed as plain sentences, top to
bottom, so it can be read aloud by a screen reader or followed by ear with
nothing lost. There are no tables, no charts, and nothing that only works
if you can see it.

Input works two ways:
  1. Answer four short prompts, one at a time (friendly to voice dictation).
  2. Pass answers on the command line, e.g.
       --book "Dune" --movie "Spirited Away" --artist "Miles Davis" \
       --place "Central Park"

The Qloo API key is read from the QLOO_API_KEY environment variable at
runtime. It is never stored in this file or in any output.
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

BASE_URL = os.environ.get("QLOO_BASE_URL", "https://hackathon.api.qloo.com")

LANES = [
    ("book", "book", "urn:entity:book", "Name a book you love."),
    ("movie", "film", "urn:entity:movie", "Name a film you love."),
    ("artist", "musician or band", "urn:entity:artist",
     "Name a musician or band you love."),
    ("place", "place", "urn:entity:place",
     "Name a place you love, like a cafe, a park, or a landmark."),
]

ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth",
            "Seventh", "Eighth", "Ninth", "Tenth"]


def api_get(path, params, api_key):
    """One GET call to the Qloo API. Returns (status, parsed_json_or_text)."""
    query = urllib.parse.urlencode(params)
    url = BASE_URL.rstrip("/") + path + "?" + query
    req = urllib.request.Request(url, headers={"X-Api-Key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(body)
        except json.JSONDecodeError:
            return err.code, body
    except urllib.error.URLError as err:
        return 0, str(err)


def search_entity(name, entity_type, api_key):
    """Resolve a spoken name to the best-matching Qloo entity, or None."""
    status, data = api_get("/search",
                           {"query": name, "types": entity_type},
                           api_key)
    if status != 200 or not isinstance(data, dict):
        return None
    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    return {"id": top.get("entity_id"),
            "name": top.get("name"),
            "disambiguation": top.get("disambiguation", "")}


def insights(target_type, signal_ids, api_key, take):
    """Ask Qloo what fits the taste signal in one lane.

    Tries the combined signal first. If Qloo rejects the combined set,
    falls back to one seed at a time and merges, keeping the best
    affinity per entity. Returns a list of result entities, best first.
    """
    def one_call(ids):
        return api_get("/v2/insights",
                       {"filter.type": target_type,
                        "signal.interests.entities": ",".join(ids),
                        "feature.explainability": "true",
                        "take": take},
                       api_key)

    status, data = one_call(signal_ids)
    if status == 200 and isinstance(data, dict):
        return (data.get("results") or {}).get("entities") or []

    merged = {}
    for seed_id in signal_ids:
        status, data = one_call([seed_id])
        if status != 200 or not isinstance(data, dict):
            continue
        for ent in (data.get("results") or {}).get("entities") or []:
            key = ent.get("entity_id")
            aff = ((ent.get("query") or {}).get("affinity")) or 0
            if key not in merged or aff > (merged[key][0] or 0):
                merged[key] = (aff, ent)
    ranked = sorted(merged.values(), key=lambda pair: pair[0] or 0,
                    reverse=True)
    return [ent for _, ent in ranked[:take]]


def short_note(entity):
    """A one-sentence spoken note about a result, when Qloo provides one.

    Qloo returns short descriptions in several languages. The English one
    is the one a voice user needs, so it is picked out explicitly.
    """
    props = entity.get("properties") or {}
    text = ""
    descs = props.get("short_descriptions") or []
    for entry in descs:
        if not isinstance(entry, dict):
            continue
        langs = entry.get("languages") or []
        if "en" in langs or entry.get("language") == "en":
            text = entry.get("value", "")
            break
    if not text:
        text = props.get("short_description") or ""
    if not text:
        text = props.get("description") or ""
    text = " ".join(str(text).split())
    if not text:
        return ""
    # Keep it to the first sentence so it stays easy to hear.
    for sep in (". ", "! ", "? "):
        if sep in text:
            text = text.split(sep)[0] + "."
            break
    if len(text) > 220:
        text = text[:217].rstrip() + "..."
    return text


def affinity_words(entity):
    aff = (entity.get("query") or {}).get("affinity")
    if isinstance(aff, (int, float)):
        return " Qloo rates the match at %d out of 100." % round(aff * 100)
    return ""


def strongest_link(entity, seeds_by_id):
    """If explainability names a clear strongest seed, say which one.

    Qloo returns query.explainability["signal.interests.entities"] as a
    list of {"entity_id": ..., "score": ...} entries.
    """
    expl = (entity.get("query") or {}).get("explainability") or {}
    entries = []
    if isinstance(expl, dict):
        raw = expl.get("signal.interests.entities") or []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and "entity_id" in item:
                    entries.append((item["entity_id"],
                                      item.get("score") or 0))
    if not entries:
        return ""
    entries.sort(key=lambda pair: pair[1], reverse=True)
    best_id, best_score = entries[0]
    if best_score >= 0.3 and best_id in seeds_by_id:
        seed = seeds_by_id[best_id]
        return " This one connects most strongly to %s." % seed["spoken"]
    return ""


def main():
    parser = argparse.ArgumentParser(
        description="Map a person's taste across books, film, music, "
                    "and places, in plain spoken sentences.")
    parser.add_argument("--book")
    parser.add_argument("--movie")
    parser.add_argument("--artist")
    parser.add_argument("--place")
    parser.add_argument("--take", type=int, default=4,
                        help="recommendations per lane (default 4)")
    parser.add_argument("--out", help="also write the taste map to this file")
    args = parser.parse_args()

    api_key = os.environ.get("QLOO_API_KEY", "")
    if not api_key:
        print("I need a Qloo API key to run. Set the QLOO_API_KEY "
              "environment variable and try again.")
        return 1

    given = {"book": args.book, "movie": args.movie,
             "artist": args.artist, "place": args.place}
    interactive = not any(given.values())

    lines = []
    def say(text=""):
        lines.append(text)
        print(text)

    say("Welcome to Taste Map.")
    say("Tell me one favorite in each of four lanes, and I will map how "
        "your taste connects across books, film, music, and places.")
    say("You can leave any lane blank.")

    seeds = []          # resolved seed entities, in lane order
    seeds_by_id = {}    # entity_id -> seed info, for explainability notes
    for key, label, etype, prompt in LANES:
        name = given[key]
        if interactive:
            try:
                name = input(prompt + " ").strip()
            except EOFError:
                name = ""
        if not name:
            say("Skipping the %s lane." % label)
            continue
        found = search_entity(name, etype, api_key)
        if not found or not found["id"]:
            say("I could not find %s in Qloo's catalog, so I will leave "
                "that one out." % name)
            continue
        spoken = "the %s %s" % (label, found["name"])
        if found["disambiguation"] and \
                found["disambiguation"].strip().lower() != \
                str(found["name"]).strip().lower():
            spoken += " (%s)" % found["disambiguation"]
        found["spoken"] = spoken
        found["lane"] = label
        seeds.append(found)
        seeds_by_id[found["id"]] = found
        say("Got it: %s." % spoken)

    if not seeds:
        say("With no favorites to start from, I cannot build a map yet. "
            "Give me at least one and try again.")
        return 0

    signal_ids = [s["id"] for s in seeds]
    say("")
    say("Here is your taste map, built from %d favorite%s."
        % (len(seeds), "" if len(seeds) == 1 else "s"))

    lane_titles = {"book": "Books that fit your taste.",
                   "film": "Films that fit your taste.",
                   "musician or band": "Music that fits your taste.",
                   "place": "Places that fit your taste."}
    for key, label, etype, _prompt in LANES:
        results = insights(etype, signal_ids, api_key, args.take)
        results = [r for r in results
                   if r.get("entity_id") not in seeds_by_id]
        say("")
        say(lane_titles[label])
        if not results:
            say("Qloo did not return anything for this lane from your "
                "favorites, so there is nothing to add here.")
            continue
        for i, ent in enumerate(results[:args.take]):
            ordinal = ORDINALS[i] if i < len(ORDINALS) else "Next"
            name = str(ent.get("name", "Untitled")).rstrip()
            ending = "" if name.endswith((".", "!", "?")) else "."
            sentence = "%s: %s%s" % (ordinal, name, ending)
            note = short_note(ent)
            if note:
                sentence += " " + note
            sentence += affinity_words(ent)
            sentence += strongest_link(ent, seeds_by_id)
            say(sentence)

    say("")
    say("That is the map. Every line of it came from Qloo's taste data, "
        "matched against the favorites you named.")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
