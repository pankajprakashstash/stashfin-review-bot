"""
classifier.py — Two-pass dynamic classification using Gemini.
Pass 1: discover 5-7 broad umbrella issue buckets (not granular sub-issues).
Pass 2: classify all reviews into those buckets in batches.
Reviews with no text are auto-tagged — zero API cost.
"""
from __future__ import annotations
import json
import logging
import time
import google.generativeai as genai
from bot.config import GEMINI_API_KEY, GEMINI_MODEL, BATCH_SIZE

log = logging.getLogger(__name__)
genai.configure(api_key=GEMINI_API_KEY)

DISCOVERY_SAMPLE = 30

DISCOVERY_PROMPT = """You are analyzing Google Play Store reviews for StashFin, an Indian fintech
app (personal loans, EMI, credit line, UPI payments, bill payments).

Read the {n} reviews and identify the MAIN issue categories present.

IMPORTANT RULES FOR BUCKET CREATION:
1. Create maximum 6-7 broad umbrella buckets — NOT granular sub-issues.
   GOOD examples: "Fraud / Fee Scam", "Customer Support", "App Technical Issues",
                  "High Interest & Charges", "Loan Processing Issues", "Payment Issues"
   BAD examples: "Payment Processing Failure", "Auto-Debit Mandate Problems",
                 "Loan Account Status Discrepancy" — these are too granular, merge them.
2. Merge similar issues into one bucket. EMI problems + auto-debit + payment failures
   → all go into ONE "Payment Issues" bucket.
3. Loan disbursement + loan approval + loan status → all "Loan Processing Issues".
4. App crashes + UI bugs + technical errors → "App Technical Issues".
5. If a bucket would have fewer than 3 reviews, merge it into the closest bigger bucket.
6. Only create a "User Awareness / Expectation Mismatch" bucket if clearly
   the user misunderstood a policy (not a product failure).

For each bucket return a JSON object:
  "name"        — 2-4 word broad name
  "team_tag"    — ONE of: Tech | Product | Risk | CX | Payments | Ops | Compliance
  "description" — one sentence — the shared root cause pattern
  "count"       — approximate count

CONSISTENCY — reuse names from previous weeks:
{prev_hint}

LANGUAGE: Reviews may be English, Hindi, Hinglish. Understand all.

Return ONLY valid JSON array. No markdown.

REVIEWS:
{reviews_text}"""

CLASSIFY_PROMPT = """Classify each numbered review into exactly one of these buckets:
{buckets_list}

For each review return:
  "id"         — integer (1-based)
  "bucket"     — exact bucket name from the list
  "sentiment"  — "Negative" | "Neutral" | "Positive"
  "root_cause" — max 10 words — the specific issue in THIS review
                 (e.g. "paid Rs 475 fee, loan rejected, no refund")

RULES:
1. Pick the best-matching broad bucket. Do not create new buckets.
2. Positive = text reads positively despite low star. Neutral = no text/indecipherable.

Return ONLY valid JSON array. No markdown.

REVIEWS:
{reviews_block}"""


def _call_gemini(prompt: str, attempt: int = 0) -> str:
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        resp  = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.1)
        )
        return resp.text.strip()
    except Exception as e:
        err = str(e).lower()
        if '429' in str(e) or 'quota' in err or 'exhausted' in err or 'resource_exhausted' in err:
            log.error('Gemini quota exhausted — resets daily at midnight PT')
            raise
        if attempt < 2:
            wait = 3 * (attempt + 1)
            log.warning(f'Gemini error: {e} — retry in {wait}s')
            time.sleep(wait)
            return _call_gemini(prompt, attempt + 1)
        raise


def _parse(raw: str, fallback: list) -> list:
    raw = raw.strip()
    if raw.startswith('```'):
        raw = '\n'.join(raw.split('\n')[1:]).rsplit('```', 1)[0].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f'JSON parse error: {e} | raw: {raw[:200]}')
        return fallback


def discover_buckets(reviews: list[dict], prev_buckets: list[dict]) -> list[dict]:
    text_reviews = [r for r in reviews if r.get('has_text')]
    if not text_reviews:
        return [{'name': 'General Complaints', 'team_tag': 'Product',
                 'description': 'Mixed negative feedback', 'count': 0}]

    sample    = text_reviews[:DISCOVERY_SAMPLE]
    prev_hint = ('Previously seen buckets — reuse these names where same issue appears:\n' +
                 '\n'.join(f'  - {b["name"]}' for b in prev_buckets)
                 ) if prev_buckets else '(First run — no previous buckets)'

    reviews_text = '\n'.join(f'{i+1}. [{r["rating"]}★] {r["text"]}'
                              for i, r in enumerate(sample))
    prompt = DISCOVERY_PROMPT.format(n=len(sample),
                                      reviews_text=reviews_text,
                                      prev_hint=prev_hint)
    log.info(f'Pass 1: discovering broad buckets from {len(sample)} reviews...')
    buckets = _parse(_call_gemini(prompt), fallback=[])

    if not buckets:
        buckets = [{'name': 'General Complaints', 'team_tag': 'Product',
                    'description': 'Mixed negative feedback',
                    'count': len(text_reviews)}]

    log.info(f'Pass 1 done: {len(buckets)} buckets — {[b["name"] for b in buckets]}')
    return buckets


def classify_reviews(reviews: list[dict], buckets: list[dict]) -> list[dict]:
    no_text  = [r for r in reviews if not r.get('has_text')]
    has_text = [r for r in reviews if r.get('has_text')]

    for r in no_text:
        r.update({'bucket': 'Uncategorized / No Text',
                  'category': 'Uncategorized / No Text',
                  'sentiment': 'Neutral',
                  'root_cause': 'No text — star rating only',
                  'team_tag': ''})

    if not has_text:
        return no_text

    buckets_list = '\n'.join(
        f'- {b["name"]}: {b.get("description", "")}' for b in buckets
    )
    team_lookup = {b['name']: b.get('team_tag', '') for b in buckets}
    batches     = [has_text[i:i+BATCH_SIZE]
                   for i in range(0, len(has_text), BATCH_SIZE)]

    log.info(f'Pass 2: classifying {len(has_text)} reviews in {len(batches)} batches...')
    for idx, batch in enumerate(batches):
        log.info(f'  Batch {idx+1}/{len(batches)}')
        block   = '\n'.join(f'{i+1}. [{r["rating"]}★] {r["text"]}'
                             for i, r in enumerate(batch))
        prompt  = CLASSIFY_PROMPT.format(buckets_list=buckets_list,
                                          reviews_block=block)
        results = _parse(_call_gemini(prompt), fallback=[])
        res_map = {item['id']: item
                   for item in results
                   if isinstance(item, dict) and 'id' in item}

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
            time.sleep(1)

    log.info('Pass 2 done.')
    return no_text + has_text
