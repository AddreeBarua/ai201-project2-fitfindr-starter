# FitFindr

A multi-tool AI agent that helps users find secondhand clothing pieces and figure out how to style them. Given a natural language query, FitFindr searches a mock secondhand listings dataset, suggests an outfit combining the find with the user's existing wardrobe, and generates a shareable "fit card" caption — all in one interaction, with state flowing between each step.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Mac/Linux
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key:
GROQ_API_KEY=your_key_here


Run the CLI test (exercises both the happy path and the no-results path):
```bash
python agent.py
```

Run the Gradio interface:
```bash
python app.py
```
Open the URL printed in the terminal (typically `http://127.0.0.1:7860`).

---

## Tool Inventory

### `search_listings(description, size, max_price)`

- **Inputs:**
  - `description` (str) — free-text keywords describing what the user wants (e.g. "vintage graphic tee")
  - `size` (str | None) — size to filter by; case-insensitive substring match (e.g. "M" matches "S/M"); `None` skips size filtering
  - `max_price` (float | None) — maximum price, inclusive; `None` skips price filtering
- **Returns:** a list of listing dicts (`id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`), sorted by relevance — relevance is the count of description words found in the listing's title, description, category, or style tags. Returns `[]` if nothing matches.
- **Purpose:** the entry point of every interaction — turns the user's parsed query into a ranked list of candidate items.

### `suggest_outfit(new_item, wardrobe)`

- **Inputs:**
  - `new_item` (dict) — a listing dict from `search_listings`
  - `wardrobe` (dict) — a wardrobe dict with an `items` key (list of dicts with `name`, `category`, `colors`, `style_tags`, optional `notes`); may be empty
- **Returns:** a non-empty string (3-5 sentences) suggesting 1-2 outfit combinations. If the wardrobe has items, the suggestion names specific wardrobe pieces and how to combine them with the new item. If the wardrobe is empty, the suggestion is general styling advice for the new item.
- **Purpose:** turns a single item into a styling recommendation, personalized to the user's existing clothes when available.

### `create_fit_card(outfit, new_item)`

- **Inputs:**
  - `outfit` (str) — the outfit suggestion string from `suggest_outfit`
  - `new_item` (dict) — the listing dict for the thrifted item
- **Returns:** a 2-4 sentence first-person caption mentioning the item's title, price, and platform once each, written like a real OOTD social post. Returns a fixed error string ("Couldn't generate a fit card — no outfit suggestion was provided. Try running suggest_outfit first.") if `outfit` is empty or whitespace-only.
- **Purpose:** the final, shareable output of the interaction — turns the structured outfit suggestion into something a user could actually post.

---

## Planning Loop

`run_agent(query, wardrobe)` runs a fixed sequence of steps with one conditional branch point:

1. Initialize a session dict (`_new_session`).
2. Parse `query` with `_parse_query()` — a regex-based parser, not an LLM call — into `description`, `size`, and `max_price`.
   - `max_price`: matches `\$(\d+(?:\.\d+)?)` (e.g. "under $30" → 30.0)
   - `size`: first tries `size\s+([A-Za-z0-9/]+)` (e.g. "size M"), then falls back to scanning for a standalone size token (XS/S/M/L/XL/XXL/XXS)
   - `description`: the original query with the matched price/size phrases and filler words ("looking for", "under", "in", "a", "the", etc.) stripped out
3. Call `search_listings(description, size, max_price)`.
4. **Branch:** `if not session["search_results"]:`
   - **Empty** → build a specific error message naming the parsed description/size/price, set `session["error"]`, and `return session` immediately. Steps 5-7 do not run.
   - **Non-empty** → continue.
5. `session["selected_item"] = search_results[0]`.
6. Call `suggest_outfit(selected_item, wardrobe)` → `session["outfit_suggestion"]`.
7. Call `create_fit_card(outfit_suggestion, selected_item)` → `session["fit_card"]`. Return session.

I chose regex over an LLM for query parsing because the example queries follow predictable patterns ("X under $Y", "X in size Y"), and a deterministic parser is faster, free, and easier to test than relying on an LLM to consistently return well-formed JSON. The two LLM-based tools already satisfy the project's agentic requirements without adding a third API dependency just for parsing.

**What happens specifically when `search_listings` returns no results:** the loop does not call `suggest_outfit` or `create_fit_card` at all — both remain `None` in the session. Instead, `session["error"]` is set to a message that restates exactly what was searched for (description, size, and price filter as parsed) and suggests the user either loosen a filter or reword their description. In `app.py`, this message is shown in the "Top listing found" panel, and the other two panels are left empty — the UI itself visibly behaves differently for this case than for the happy path.

---

## State Management

A single `session` dict, created at the start of `run_agent()`, is the source of truth for the entire interaction:

| Key | Set by | Used by |
|---|---|---|
| `query` | input | `_parse_query` |
| `parsed` | `_parse_query` | `search_listings`, error message |
| `search_results` | `search_listings` | branch check, `selected_item` |
| `selected_item` | step 5 | `suggest_outfit`, `create_fit_card`, UI panel 1 |
| `wardrobe` | input | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card`, UI panel 2 |
| `fit_card` | `create_fit_card` | UI panel 3 |
| `error` | branch (if hit) | UI error display |

`selected_item` is the same dict object passed to both `suggest_outfit` and `create_fit_card` — the item the user sees in the "Top listing found" panel is guaranteed to be the item referenced in the outfit suggestion and the fit card, with no re-entry of any kind. Similarly, the exact string returned by `suggest_outfit` is passed unmodified as the `outfit` argument to `create_fit_card`. `app.py`'s `handle_query()` simply reads the final session dict and maps three of its fields to the three UI output panels.

---

## Error Handling

| Tool | Failure mode | Agent response |
|---|---|---|
| `search_listings` | No results match the query | Returns `[]`. The planning loop detects this, builds a message like *"No listings found for 'designer ballgown', size XXS under $5. Try removing the size or price filter, or rewording your description."*, sets `session["error"]`, and returns early. `suggest_outfit`/`create_fit_card` are never called. |
| `suggest_outfit` | Wardrobe is empty (`wardrobe["items"] == []`) | The tool checks this before building its prompt and sends a different prompt asking the LLM for general styling advice for the item alone, still returning a non-empty string. Not treated as an agent-level error — the loop proceeds normally. |
| `create_fit_card` | `outfit` is empty/whitespace | Returns a fixed string ("Couldn't generate a fit card — no outfit suggestion was provided...") instead of calling the LLM or raising. |

**Concrete example from testing:** running the query `"designer ballgown size XXS under $5"` against the example wardrobe produced:
Parsed: {'description': 'designer ballgown', 'size': 'XXS', 'max_price': 5.0}
Error message: No listings found for "designer ballgown", size XXS under $5.
Try removing the size or price filter, or rewording your description.

In the Gradio UI, this error appeared in the "Top listing found" panel, while "Outfit idea" and "Your fit card" remained empty — confirming the agent stopped immediately rather than calling the remaining tools with empty input.

---

## Spec Reflection

**How the spec helped:** writing out the exact filtering/scoring order for `search_listings` (price → size → keyword scoring → drop zero-score → sort) *before* implementing it meant there was no ambiguity about what "ranked by relevance" should mean — it became a precise, testable algorithm rather than something to figure out while coding. Similarly, deciding upfront that `suggest_outfit` needed two distinct prompts (empty vs. populated wardrobe) made the empty-wardrobe requirement a design decision rather than an afterthought bolted on after testing revealed a crash.

**Where implementation diverged from the spec:** the original plan was for `_parse_query`'s `description` field to always be a clean, minimal set of keywords. In practice, longer free-form queries (e.g. "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers...") produce a noisier description string after filler-word stripping, since the filler list can't anticipate every possible phrasing. This didn't break anything — the keyword-overlap scoring in `search_listings` is tolerant of extra words, since it just counts overlaps rather than requiring an exact match — but it means the parser is most precise on short, structured queries (which match the example queries provided) and gracefully degrades, rather than failing, on longer ones.

---

## AI Usage

I used Claude (claude.ai) as an implementation assistant for two parts of the build, after designing the specs, scoring logic, prompt structures, and error-handling rules myself in `planning.md`.

**Instance 1 — `search_listings`:** I had already decided the exact filtering and scoring order (filter by price, then size, then score by keyword overlap against title/description/category/style_tags, drop zero-score listings, sort descending) and gave Claude that spec to implement as Python. I reviewed the generated code against my spec, then tested it with a real query ("vintage graphic tee", size M, max $30) — confirming the top-ranked result matched on the relevant style tags — and with an intentionally impossible query ("designer ballgown", size XXS, max $5) to confirm it returned `[]` without raising.

**Instance 2 — `agent.py` planning loop and `_parse_query`:** I'd written out the full 7-step sequence, the branch condition, and the regex strategy (which fields to extract and in what order to strip them from the description) before asking Claude to implement `run_agent()` and `_parse_query()` to that spec. I reviewed the generated code to confirm it matched my step-by-step description — specifically that it checked `search_results` for emptiness *before* calling `suggest_outfit`, and that `selected_item` was passed by reference into both later tool calls rather than being re-derived. I then ran `python agent.py`'s built-in CLI test and verified the parsed dict, the state-passing, and the early-return error path all matched what I'd specified.

In both cases, the AI tool implemented code to a specification I'd already written; I verified the output against that specification through direct terminal testing before integrating it, and made adjustments where the generated code didn't match (e.g. confirming the empty-wardrobe branch in `suggest_outfit` used a genuinely different prompt rather than just a flag).