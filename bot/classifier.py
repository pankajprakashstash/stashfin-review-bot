"""
classifier.py
=============
Two-pass dynamic classification using Gemini.

Pass 1 — Bucket Discovery:
    Sends all review texts to Gemini and asks it to identify what issue
    categories actually exist this week, with a team-owner tag per bucket.
    Previous week's buckets are passed as a hint so names stay consistent.

Pass 2 — Classification:
    Classifies each review into the discovered buckets (batched).

No hardcoded taxonomy — new product areas and issues are discovered automatically.
"""
from __future__ import annotations
import json
import logging
import time
import google.generativeai as genai
from bot.config import GEMINI_API_KEY, GEMINI_MODEL, BATCH_SIZE

log = logging.getLogger(__name__)
genai.configure(api_key=GEMINI_API_KEY)

# ── Pass 1: Bucket discovery prompt ───────────────────────────────────────────

DISCOVERY_PROMPT = """You are analyzing Google Play Store reviews for StashFin, an Indian fintech app
offering personal loans, EMI, credit line, UPI payments, and bill payments.

Read the {n} reviews below and identify every distinct issue or concern bucket present.

IMPORTANT CONTEXT — read before classifying:
Not all negative reviews reflect a genuine product failure. Some may reflect:
- User misunderstanding of a policy (e.g. non-refundable fee stated in T&C)
- User expectation mismatch (e.g. expected 0% interest but did not read full terms)
- One-sided account where full context is unknown
This does NOT mean ignoring these reviews — they still affect ratings and reflect perception.
But if a cluster of reviews suggests users misunderstood something rather than the product
failing, create a separate bucket called "User Awareness / Expectation Mismatch" for those.

For each bucket return a JSON object with:
  - "name":        short 2-5 word bucket name
                   (e.g. "Upfront Fee / Loan Scam", "UPI Activation Failure",
                   "App Crash / Bug", "High Interest Rate", "User Awareness / Expectation Mismatch")
  - "team_tag":    which internal team primarily owns this. Pick ONE:
                   Tech | Product | Risk | CX | Payments | Ops | Compliance
  - "description": one sentence — the pattern shared across reviews in this bucket
  - "count":       approximate number of reviews in this bucket

CONSISTENCY RULES:
If the following buckets appeared last week, reuse the same name if the same issue appears.
Only create a new name if it is genuinely a different issue.
{prev_buckets_hint}

LANGUAGE NOTE: Reviews may be in English, Hindi, or Hinglish.
"farzi/fraud/froud" = scam, "kat liya" = deducted, "wapas nahi" = not refunded,
"nahi chal raha" = not working, "band karo" = stop this, "pata nahi tha" = did not know.

Return ONLY a valid JSON array of bucket objects. No markdown, no explanation, nothing else.

REVIEWS:
{reviews_text}"""


# ── Pass 2: Classification prompt ─────────────────────────────────────────────

CLASSIFY_PROMPT = """Classify each numbered review into exactly one of the buckets listed below.

BUCKETS (discovered from this week's reviews):
{buckets_list}

For each review return a JSON object with:
  - "id":          integer (the review number, 1-based)
  - "bucket":      exact bucket name from the list above (copy exactly)
  - "sentiment":   "Negative" | "Neutral" | "Positive"
  - "root_cause":  max 12 words — the specific failure or misunderstanding in THIS review.
                   Be concrete. Not "user is unhappy" but "paid ₹475 fee, no loan given, no refund".
                   For awareness issues: "user unaware fee is non-refundable per T&C".

RULES:
1. Pick the bucket whose description best matches the review's core complaint.
2. Sentiment: Positive if text reads positively despite low star.
   Neutral only if text is genuinely absent or indecipherable.
3. If review touches multiple issues, pick the primary one.
4. Reviews that seem to be user error or policy misunderstanding →
   "User Awareness / Expectation Mismatch" bucket if that bucket was discovered.

Return ONLY a valid JSON array. No markdown, no explanation, nothing else.

REVIEWS TO CLASSIFY:
{reviews_block}"""


# ── Gemini caller with retry ───────────────────────────────────────────────────

def _call_gemini(prompt: str, attempt: int = 0) -> str:
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        resp  = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.1)
        )
        return resp.text.strip()
    except Exception as e:
        if attempt < 3:
            wait = 2 ** (attempt + 1)
            log.warning(f'Gemini error: {e} — retrying in {wait}s')
            time.sleep(wait)
            return _call_gemini(prompt, attempt + 1)
        raise


def _parse_json(raw: str, fallback: list) -> list:
    raw = raw.strip()
    if raw.startswith('```'):
        raw = '\n'.join(raw.split('\n')[1:])
        raw = raw.rsplit('```', 1)[0].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f'JSON parse failed: {e} | Raw snippet: {raw[:300]}')
        return fallback


# ── Pass 1: Discover buckets ───────────────────────────────────────────────────

def discover_buckets(reviews: list[dict], prev_buckets: list[dict]) -> list[dict]:
    text_reviews = [r for r in reviews if r.get('has_text')]
    if not text_reviews:
        log.warning('No text reviews — skipping bucket discovery')
        return []

    if prev_buckets:
        hint_lines = '\n'.join(
            f'  - {b["name"]} ({b.get("team_tag", "")})' for b in prev_buckets
        )
        prev_hint = f'Previously seen buckets:\n{hint_lines}'
    else:
        prev_hint = '(First run — no previous buckets to reference)'

    reviews_text = '\n'.join(
        f'{i+1}. [{r["rating"]}★] {r["text"]}' for i, r in enumerate(text_reviews)
    )
    prompt  = DISCOVERY_PROMPT.format(
        n                 = len(text_reviews),
        reviews_text      = reviews_text,
        prev_buckets_hint = prev_hint,
    )
    log.info(f'Pass 1: discovering buckets from {len(text_reviews)} text reviews...')
    raw     = _call_gemini(prompt)
    buckets = _parse_json(raw, fallback=[])

    if not buckets:
        log.warning('Bucket discovery returned nothing — using fallback bucket')
        buckets = [{'name': 'General Complaints', 'team_tag': 'Product',
                    'description': 'Mixed negative feedback', 'count': len(text_reviews)}]

    log.info(f'Pass 1 complete — {len(buckets)} buckets: {[b["name"] for b in buckets]}')
    return buckets


# ── Pass 2: Classify reviews into buckets ─────────────────────────────────────

def classify_reviews(reviews: list[dict], buckets: list[dict]) -> list[dict]:
    no_text = [r for r in reviews if not r.get('has_text')]
    for r in no_text:
        r.update({
            'bucket':     'Uncategorized / No Text',
            'category':   'Uncategorized / No Text',
            'sentiment':  'Neutral',
            'root_cause': 'No review text — star rating only',
            'team_tag':   '',
        })

    has_text = [r for r in reviews if r.get('has_text')]
    if not has_text:
        return no_text

    buckets_list = '\n'.join(
        f'- {b["name"]}: {b.get("description", "")}' for b in buckets
    )
    team_lookup = {b['name']: b.get('team_tag', '') for b in buckets}
    batches     = [has_text[i:i+BATCH_SIZE] for i in range(0, len(has_text), BATCH_SIZE)]

    log.info(f'Pass 2: classifying {len(has_text)} reviews in {len(batches)} batches...')

    for idx, batch in enumerate(batches):
        log.info(f'  Batch {idx+1}/{len(batches)}')
        reviews_block = '\n'.join(
            f'{i+1}. [{r["rating"]}★] {r["text"]}' for i, r in enumerate(batch)
        )
        prompt  = CLASSIFY_PROMPT.format(
            buckets_list  = buckets_list,
            reviews_block = reviews_block,
        )
        raw     = _call_gemini(prompt)
        results = _parse_json(raw, fallback=[])
        res_map = {
            item['id']: item
            for item in results
            if isinstance(item, dict) and 'id' in item
        }

        for i, review in enumerate(batch):
            res    = res_map.get(i + 1, {})
            bucket = res.get('bucket', 'General Complaints')
            review.update({
                'bucket':     bucket,
                'category':   bucket,
                'sentiment':  res.get('sentiment', 'Negative'),
                'root_cause': res.get('root_cause', ''),
                'team_tag':   team_lookup.get(bucket, ''),
            })

        if idx < len(batches) - 1:
            time.sleep(2)

    log.info('Pass 2 complete.')
    return no_text + has_text
