# FitFindr — planning.md

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items matching a free-text description, with optional size and price filters, and returns results ranked by keyword relevance to the description.

**Input parameters:**
- `description` (str): Free-text keywords describing what the user wants (e.g., "vintage graphic tee"). Used to score listings by keyword overlap with the listing's title, description, category, and style tags.
- `size` (str | None): Size to filter by (e.g., "M"). Matching is a case-insensitive substring match, so a query for "M" also matches a listing size of "S/M". If None, no size filtering is applied.
- `max_price` (float | None): Maximum price (inclusive). If None, no price filtering is applied.

**What it returns:**
A list of listing dicts, sorted by relevance score (highest first). Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. A listing's score is the count of description words that appear anywhere in its title, description, category, or style tags. Listings with a score of 0 are dropped entirely. Returns `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
The planning loop checks if the returned list is empty. If so, it builds a message that restates the parsed description, size, and price filter, suggests removing the size/price filter or rewording the description, sets `session["error"]` to that message, and returns the session immediately. `suggest_outfit` and `create_fit_card` are never called.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted item and the user's wardrobe, calls the Groq LLM (llama-3.3-70b-versatile) to suggest 1–2 complete outfit combinations using the new item alongside specific named pieces from the wardrobe.

**Input parameters:**
- `new_item` (dict): A listing dict from `search_listings` (the item the user is considering). Its title, description, category, colors, style_tags, and condition are included in the prompt.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts (each with `name`, `category`, `colors`, `style_tags`, and optional `notes`). May be empty.

**What it returns:**
A non-empty string with outfit suggestions, 3-5 sentences. If `wardrobe['items']` is non-empty, the suggestions reference specific named wardrobe pieces and how to style them with the new item (tucked, layered, rolled, etc.). If the wardrobe is empty, the response is general styling advice for the new item — what it pairs well with and what vibe it suits — rather than an empty string or exception.

**What happens if it fails or returns nothing:**
The tool branches on `wardrobe['items']` before calling the LLM: an empty wardrobe gets a different prompt (general styling advice) instead of failing or returning an empty string. The agent always has a non-empty string to pass to `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, casual Instagram/TikTok-style caption (2-4 sentences) for the thrifted item and outfit, using the Groq LLM at a higher temperature so repeated calls on the same input produce different wording.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`.
- `new_item` (dict): The listing dict for the thrifted item — its `title`, `price`, and `platform` are referenced in the caption.

**What it returns:**
A 2-4 sentence string written in first person, casual tone, mentioning the item name, price, and platform each once, and capturing the outfit's vibe in specific terms (e.g. "laid-back streetwear," "90s grunge"). Temperature is set to 1.0 so the same inputs produce noticeably different captions across calls.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the function returns a descriptive error string ("Couldn't generate a fit card — no outfit suggestion was provided. Try running suggest_outfit first.") instead of calling the LLM or raising an exception. In the planning loop, this case can't actually occur on the happy path because `suggest_outfit` always returns a non-empty string — this guard exists as a defensive check on the function's own contract.

---

### Additional Tools (if any)

None for the required submission.

---

## Planning Loop

**How does your agent decide which tool to call next?**

`run_agent()` runs a fixed sequence of steps, but the sequence terminates early based on the result of `search_listings`:

1. Initialize a fresh session dict via `_new_session()`.
2. Parse the raw query string with `_parse_query()` (regex-based — see below) into `description`, `size`, and `max_price`. Store in `session["parsed"]`.
3. Call `search_listings(description, size, max_price)`. Store the result in `session["search_results"]`.
4. **Branch point**: check `if not session["search_results"]`.
   - If true (empty list): build a specific error message naming the parsed description/size/price, store it in `session["error"]`, and `return session` immediately. Steps 5-7 are skipped entirely.
   - If false (one or more results): continue to step 5.
5. Set `session["selected_item"] = session["search_results"][0]` (top-ranked result).
6. Call `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])`. Store result in `session["outfit_suggestion"]`.
7. Call `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])`. Store result in `session["fit_card"]`. Return session.

The loop "knows it's done" either when `session["error"]` is set (early termination after step 4) or when `session["fit_card"]` has been populated (step 7, normal completion). `session["error"]` is the single flag the rest of the application (e.g. `app.py`) checks to decide which of these two outcomes occurred.

**Query parsing (regex, not LLM):**
`_parse_query()` extracts:
- `max_price`: regex `\$(\d+(?:\.\d+)?)` — first dollar amount found (e.g. "under $30" → 30.0).
- `size`: first tries an explicit `size\s+([A-Za-z0-9/]+)` pattern (e.g. "size M", "size 8"); if not found, falls back to scanning words for a standalone size token (XS, S, M, L, XL, XXL, XXS).
- `description`: the original query with the matched price phrase, size phrase/token, and a small list of filler words ("looking for", "under", "in", "a", "the", etc.) stripped out, then whitespace/punctuation cleaned up.

I chose regex over an LLM call for parsing because the example queries follow predictable patterns ("X under $Y", "X in size Y", "X size Y"), and a deterministic parser is faster, free, and easier to unit test than relying on an LLM to return well-formed JSON every time. This was a design decision made before any implementation — the LLM-based tools (`suggest_outfit`, `create_fit_card`) already cover the project's "AI agent" requirements, so I didn't want to add a third API dependency (and a new JSON-parsing failure mode) for something a few regex patterns handle reliably.

---

## State Management

**How does information from one tool get passed to the next?**

All state for one interaction lives in a single `session` dict created by `_new_session()` at the start of `run_agent()`. The dict has fixed keys that are populated progressively as the loop runs:

- `query`: the original raw user string (never mutated).
- `parsed`: dict with `description`, `size`, `max_price` from `_parse_query()`.
- `search_results`: full list returned by `search_listings`.
- `selected_item`: the single dict (`search_results[0]`) chosen for the rest of the flow — this is the exact dict object passed as `new_item` to both `suggest_outfit` and `create_fit_card`, so the item the user sees in the "Top listing found" panel is guaranteed to be the same item referenced in the outfit suggestion and fit card.
- `wardrobe`: passed in by the caller (`app.py`) and stored unchanged; passed to `suggest_outfit`.
- `outfit_suggestion`: the string returned by `suggest_outfit`, later passed as `outfit` into `create_fit_card`.
- `fit_card`: final output string.
- `error`: `None` on success, or a string message if the interaction ended early at step 4.

Because every tool call reads its inputs from `session` and writes its output back into `session`, no value is ever re-requested from the user mid-interaction. `app.py`'s `handle_query()` reads the final `session` dict and maps `selected_item`, `outfit_suggestion`, and `fit_card` directly to the three UI output panels (or, if `session["error"]` is set, shows that message in the first panel only).

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (returns `[]`) | The planning loop detects the empty list immediately after the call, builds a message restating the parsed description, size, and price ("No listings found for '...', size X under $Y. Try removing the size or price filter, or rewording your description."), sets `session["error"]` to that message, and returns early — `suggest_outfit` and `create_fit_card` are never called. In `app.py`, this message is shown in the "Top listing found" panel and the other two panels are left empty. |
| suggest_outfit | Wardrobe is empty (`wardrobe["items"] == []`) | The tool checks `wardrobe.get("items", [])` before building its prompt. If empty, it sends a different prompt to the LLM asking for general styling advice for the new item alone (what it pairs with, what vibe it suits, example outfit ideas using generic items like "jeans" or "white sneakers"), and still returns a non-empty string. The planning loop proceeds normally to `create_fit_card` — this is not treated as an error. |
| create_fit_card | Outfit input is missing or incomplete (empty or whitespace-only string) | The tool checks `if not outfit or not outfit.strip()` before calling the LLM. If true, it returns a fixed descriptive string ("Couldn't generate a fit card — no outfit suggestion was provided. Try running suggest_outfit first.") instead of calling the API or raising an exception. This guard protects the function's own contract; in practice `suggest_outfit` always returns a non-empty string, so this path is exercised via direct unit testing rather than through the normal agent flow. |

---

## Architecture
User query (e.g. "vintage graphic tee under $30")

│

▼

_parse_query(query)

│  → {description, size, max_price}

│

▼

Planning Loop (run_agent) ──────────────────────────────────────────────┐

│                                                                    │

├─► search_listings(description, size, max_price)                   │

│       │                                                            │

│       │ search_results = []                                        │

│       ├──► session["error"] = "No listings found for ..."          │

│       │         │                                                  │

│       │         ▼                                                  │

│       │     return session  ─────────────────────────────────────►│ (error branch

│       │                                                            │  terminates here)

│       │ search_results = [item, ...]                               │

│       ▼                                                            │

│   session["selected_item"] = search_results[0]                     │

│       │                                                            │

├─► suggest_outfit(selected_item, wardrobe)                          │

│       │                                                            │

│   session["outfit_suggestion"] = "..."                             │

│       │                                                            │

├─► create_fit_card(outfit_suggestion, selected_item)                │

│       │                                                            │

│   session["fit_card"] = "..."                                      │

│       │                                                            │

│       ▼                                                            │

│   return session  ─────────────────────────────────────────────────┘

│

▼

app.py handle_query()

│

├─ if session["error"]: show error in panel 1, panels 2 & 3 empty

└─ else: panel 1 = selected_item details

panel 2 = outfit_suggestion

panel 3 = fit_card

---

## AI Tool Plan

I designed the tool specs, scoring logic, prompt structure, error-handling rules, and the agent diagram above before writing any code, then used Claude (claude.ai) as an implementation assistant for two parts of the build — each time giving it a fully-specced piece rather than an open-ended request, and checking the output against my own spec before running it.

**Milestone 3 — Individual tool implementations:**
For `search_listings`, I had already decided the filtering order (price, then size, then keyword scoring against title/description/category/style_tags, drop zero-score items, sort descending) — I gave Claude that exact spec and had it write the loop/comprehension code. I tested it against a real query ("vintage graphic tee", size M, max $30) and confirmed the top result matched on the relevant style tags, and against an intentionally impossible query to confirm it returned `[]` without raising.

For `suggest_outfit`, I'd decided the two-branch design myself (empty wardrobe → general advice prompt, non-empty wardrobe → bulleted wardrobe context with named-piece suggestions) and specified that wardrobe items should be formatted as bullets including colors/style_tags/notes so the model has enough to work with. Claude wrote the prompt-building and API call code to that spec. I tested both branches directly — confirming the empty-wardrobe response gave general advice without crashing on `wardrobe['items'] == []`, and the populated-wardrobe response named specific pieces from the example wardrobe (e.g. "baggy straight-leg jeans," "chunky white sneakers").

For `create_fit_card`, I specified the empty-outfit guard (return a fixed string, don't call the API) and the temperature setting (1.0, higher than Tool 2's 0.7) to satisfy the "sound different each time" requirement. I ran it twice on identical inputs and confirmed the captions varied while each still mentioned the item name, price, and platform exactly once; I also confirmed the empty-outfit guard returned the fixed string instead of an API call.

**Milestone 4 — Planning loop and state management:**
I'd already written out the 7-step sequence and the error-branch behavior in the Planning Loop section above, plus the regex strategy for `_parse_query` (which fields to extract and in what order to strip them from the description). I gave Claude that spec plus the architecture diagram and had it implement `run_agent()` and `_parse_query()` to match.

I verified the result by running `python agent.py`'s built-in CLI test: the parsed dict for "looking for a vintage graphic tee under $30" came back as `{'description': 'vintage graphic tee', 'size': None, 'max_price': 30.0}` as expected; `selected_item` was confirmed to be the same object passed into `suggest_outfit` and then `create_fit_card` (no re-entry); and the no-results query ("designer ballgown size XXS under $5") set a specific error message and left `outfit_suggestion`/`fit_card` as `None`, confirming the early-return branch worked. I implemented `handle_query()` in `app.py` against the same spec and confirmed via the Gradio UI that both the happy path (all three panels populated) and the no-results path (error in panel 1, others empty) behaved as designed.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
`_parse_query()` extracts `max_price = 30.0` from "$30", finds no explicit size token, and produces a description string with the price phrase and common filler words stripped out. `search_listings(description, size=None, max_price=30.0)` is called.

*(Note: shorter, more structured queries like "vintage graphic tee under $30" produce cleaner descriptions; longer free-form queries like this example produce a noisier description string, but the keyword-overlap scoring still surfaces the "Y2K Baby Tee — Butterfly Print" as the top result because it matches "vintage", "graphic tee", and related style tags.)*

**Step 2:**
`search_listings` returns a non-empty list ranked by relevance. The top result, "Y2K Baby Tee — Butterfly Print" ($18.00, depop, size S/M, style tags: y2k/vintage/graphic tee/cottagecore), is stored as `session["selected_item"]`. Since the list isn't empty, the loop continues — `suggest_outfit` is called next with this item and the user's wardrobe (example wardrobe, which includes "baggy straight-leg jeans" and "chunky white sneakers").

**Step 3:**
`suggest_outfit` returns an outfit suggestion that specifically references the user's baggy straight-leg jeans and chunky white sneakers, suggesting the tee be tucked in for contrast, with an alternative layering option using a crewneck sweatshirt and combat boots. This string is stored in `session["outfit_suggestion"]` and passed to `create_fit_card` along with `selected_item`.

**Step 4:**
`create_fit_card` generates a casual first-person caption mentioning "Y2K Baby Tee — Butterfly Print", "$18", and "Depop" once each, describing the tucked-tee-and-jeans look with an emoji. This is stored in `session["fit_card"]`. The loop returns the completed session.

**Final output to user:**
The Gradio UI shows three populated panels: "Top listing found" (the Y2K Baby Tee with its price, platform, size, condition, colors, and style tags), "Outfit idea" (the styling suggestion referencing the user's jeans and sneakers), and "Your fit card" (the shareable caption). No error message is shown.