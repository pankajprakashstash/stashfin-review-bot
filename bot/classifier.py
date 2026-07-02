"""
classifier.py
Sends reviews to Gemini in batches of BATCH_SIZE.
Reviews with no text are auto-classified without using any API quota.
Returns reviews enriched with: category, sub_category, sentiment, root_cause.
"""
from __future__ import annotations
import json
import logging
import time
import google.generativeai as genai
from bot.config import GEMINI_API_KEY, GEMINI_MODEL, BATCH_SIZE

log = logging.getLogger(__name__)
genai.configure(api_key=GEMINI_API_KEY)

TAXONOMY = {
    'Fraud / Scam': [
        'Fee-Then-Reject (No Refund)',
        'General Fraud Accusation',
        'Credit Bureau Reporting Error',
        'Misleading Interest / Marketing',
        'Auto-Debit Set Up Before Approval',
        'Impersonation / Social Engineering',
    ],
    'Fees & Charges': [
        'High Interest Rate',
        'Non-Refundable Processing Fee',
        'Bounce / Overdue Penalty Charged Incorrectly',
    ],
    'EMI / Payment Issues': [
        'Duplicate / Double EMI Deduction',
        'NOC / Loan Closure Delay',
        'Manual Payment Not Reflected',
        'Payment Flow Broken',
    ],
    'Loan Eligibility / Processing': [
        'Stuck Under Review Indefinitely',
        'Eligibility / Approval Confusion',
        'Rejected After Long Wait',
    ],
    'Customer Support': [
        'No Phone / Helpline Access',
        'No Response to Email / Ticket',
        'Bot-Only / Unhelpful Chat',
    ],
    'Technical Issues': [
        'Withdrawal / Transfer Error',
        'App Crash / Not Loading',
        'Device Incompatibility / Login Blocked',
    ],
    'KYC / Verification Issues': [
        'Video KYC — Agent Not Available',
        'Bank / Profile Update Stuck',
    ],
    'Data Privacy / Harassment': [
        'Harassment / Excessive Data Access',
    ],
    'Refund Issues': [
        'Fee Refund Pending',
        'Duplicate Deduction Refund Pending',
    ],
    'Digital Gold / Rewards Issues': [
        'Redemption / Access Blocked',
    ],
    'UI/UX & Feature Feedback': [
        'Feature Removed / UX Complaint',
    ],
    'Other / Vague': [
        'Short Generic Negative',
        'Unspecified Complaint',
    ],
}

TAXONOMY_STR = '\n'.join(
    f'{cat}:\n' + '\n'.join(f'  - {s}' for s in subs)
    for cat, subs in TAXONOMY.items()
)

PROMPT = """You are classifying Google Play Store reviews for StashFin, an Indian fintech lending app (personal loans, EMI, credit line, bill payments).

Reviews may be in English, Hindi, Hinglish, or other Indian languages. Understand all of them.

Classify each numbered review below. Return a JSON array — one object per review.

Each object must have exactly these fields:
- "id": integer (the review number, 1-based)
- "category": string (pick ONE from the taxonomy below)
- "sub_category": string (pick ONE sub-category that matches the category)
- "sentiment": "Negative" | "Neutral" | "Positive"
- "root_cause": string (one sentence — the UNDERLYING system or process failure, not what the user said. E.g. not "user says EMI deducted twice" but "auto-debit lacks idempotency check — manual payment not reconciled before ECS presentment")

TAXONOMY:
{taxonomy}

CLASSIFICATION RULES:
1. Base classification on what the user actually describes, not just emotional words.
2. "frud/froud/farji/scam/fake" alone → Other/Vague unless user describes a specific pattern.
3. Fee paid then loan rejected/stuck with no refund → Fraud / Scam → Fee-Then-Reject (No Refund).
4. EMI deducted twice in one month → EMI / Payment Issues → Duplicate / Double EMI Deduction.
5. App shows error on withdrawal → Technical Issues → Withdrawal / Transfer Error.
6. No customer care number / no response → Customer Support.
7. Video KYC agent not available → KYC / Verification Issues.
8. Sentiment: Positive if text reads positively despite low star. Neutral only if text is absent or completely indecipherable.
9. Hinglish hints: "kat liya/cut ho gaya"=deducted, "wapas nahi"=not refunded, "bekar/ghatiya"=very bad, "farzi"=fake, "bhi nahi mila"=not received.

OUTPUT: Return ONLY a valid JSON array. No markdown, no explanation, nothing else.

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
        if attempt < 3:
            wait = 2 ** (attempt + 1)
            log.warning(f'Gemini error ({e}), retry in {wait}s...')
            time.sleep(wait)
            return _call_gemini(prompt, attempt + 1)
        log.error(f'Gemini failed after 3 retries: {e}')
        raise


def _parse_response(raw: str, batch_size: int) -> list[dict]:
    # Strip markdown fences if Gemini adds them
    raw = raw.strip()
    if raw.startswith('```'):
        raw = '\n'.join(raw.split('\n')[1:])
        raw = raw.rsplit('```', 1)[0].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.error(f'JSON parse failed. Raw: {raw[:300]}')
        return [{'id': i+1, 'category': 'Other / Vague',
                 'sub_category': 'Unspecified Complaint',
                 'sentiment': 'Negative',
                 'root_cause': 'Auto-classification failed — needs manual review'}
                for i in range(batch_size)]


def classify_reviews(reviews: list[dict]) -> list[dict]:
    if not reviews:
        return []

    # Reviews with no text — classify instantly without Gemini
    no_text    = [r for r in reviews if not r['has_text']]
    has_text   = [r for r in reviews if r['has_text']]

    for r in no_text:
        r.update({'category': 'Uncategorized / No Text',
                  'sub_category': 'No Text',
                  'sentiment': 'Neutral',
                  'root_cause': 'User left no review text — star rating only'})

    if not has_text:
        return no_text

    # Batch the text reviews
    batches = [has_text[i:i+BATCH_SIZE] for i in range(0, len(has_text), BATCH_SIZE)]
    log.info(f'Classifying {len(has_text)} text reviews in {len(batches)} batches...')

    for idx, batch in enumerate(batches):
        log.info(f'  Batch {idx+1}/{len(batches)}')
        reviews_block = '\n'.join(
            f'{i+1}. [{r["rating"]}★] {r["text"]}' for i, r in enumerate(batch)
        )
        prompt  = PROMPT.format(taxonomy=TAXONOMY_STR, reviews_block=reviews_block)
        raw     = _call_gemini(prompt)
        results = _parse_response(raw, len(batch))
        res_map = {item['id']: item for item in results if 'id' in item}

        for i, review in enumerate(batch):
            res = res_map.get(i + 1, {})
            cat = res.get('category', 'Other / Vague')
            sub = res.get('sub_category', 'Unspecified Complaint')
            if cat not in TAXONOMY and cat != 'Uncategorized / No Text':
                cat = 'Other / Vague'
                sub = 'Unspecified Complaint'
            review.update({
                'category':    cat,
                'sub_category': sub,
                'sentiment':   res.get('sentiment', 'Negative'),
                'root_cause':  res.get('root_cause', ''),
            })

        if idx < len(batches) - 1:
            time.sleep(2)   # respect free-tier rate limit

    log.info('Classification done.')
    return no_text + has_text
