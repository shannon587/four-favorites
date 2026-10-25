# Four Favorites

A small tool that uses Qloo's API to connect a person's favorites across
books, film, music, and places, built accessibility-first for voice use.

## What it does

You name one favorite in each of four lanes:

1. a book,
2. a film,
3. a musician or band,
4. a place.

The tool resolves each name to a Qloo entity, combines them into one set of
favorites, and asks Qloo's Insights API what connects to them in every lane.
What comes back is a recommendation list written as plain sentences: the
books, films, music, and places that connect to the favorites you named, each
with its affinity expressed as a match score out of 100, and, where Qloo's
explainability data names one, the favorite each recommendation connects
to most strongly.

## How to run it

You need Python 3 and a Qloo API key for the hackathon API server.

Set the key in your environment (never in a file):

    export QLOO_API_KEY=your-key-here

Interactive mode (the tool asks four short questions, one at a time):

    python3 taste_map.py

Command-line mode (the same answers given up front):

    python3 taste_map.py --book "Dune" --movie "Spirited Away" \
        --artist "Miles Davis" --place "Central Park"

Options:

    --take N    recommendations per lane (default 4)
    --out FILE  also write the finished recommendations to a text file

Any lane can be left blank. If Qloo cannot find a name in its catalog, the
tool says so in plain words and builds the map from the rest.

## Accessibility design choices

Accessibility is the design center of this tool, not a feature added on
top.

- **Linear spoken output.** The entire result is plain sentences, read top
  to bottom. Nothing depends on seeing a table, a chart, a color, or a
  layout. A screen reader or a text-to-speech voice loses nothing.
- **One short question at a time.** Each prompt asks for a single short
  answer, so the whole tool can be driven by voice dictation.
- **Numbers as words a listener can hold.** Affinity scores are spoken as
  "a match of 87 out of 100," never as decimals or percentages buried in
  a grid.
- **Plain failure language.** If a name is not found or a lane comes back
  empty, the tool says exactly that in a sentence and keeps going.
- **No visual-only state.** Confirmations are sentences ("Got it: the book
  Dune."), so a voice user always knows what the tool understood.

## How it uses Qloo

- `GET /search` resolves each spoken name to a Qloo entity ID, per lane
  type (`urn:entity:book`, `urn:entity:movie`, `urn:entity:artist`,
  `urn:entity:place`).
- `GET /v2/insights` with `filter.type` set per lane and
  `signal.interests.entities` set to the combined seed IDs returns the
  cross-domain affinities, with `feature.explainability` enabled so the
  output can name the favorite each recommendation leans on most.
- If Qloo rejects a combined signal, the tool falls back to one seed at a
  time and merges results by best affinity.
- All calls go to `https://hackathon.api.qloo.com` with the key in the
  `X-Api-Key` header, as the hackathon developer guide requires.

See `DEMO-RUN.md` for a full sample run on a fictional persona, and
`DEVPOST-SUBMISSION-DRAFT.md` for the hackathon submission draft.
