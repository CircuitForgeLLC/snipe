# Red Flags

Red flags appear as pills on listing cards when Snipe detects a concern. Each flag is independent — a listing can have multiple flags at once.

## Hard red flags

These override the composite score display with a strong visual warning.

### `zero_feedback`
Seller has received zero feedback. Score is capped at 35.

### `new_account`
Account registered within the last 7 days. Extremely high fraud indicator for high-value listings.

### `established_bad_actor`
Feedback ratio below 80% with 20 or more reviews. A sustained pattern of negative feedback from an established seller.

## Soft flags

Shown as warnings — not automatic disqualifiers, but worth investigating.

### `account_under_30_days`
Account is less than 30 days old. Less severe than `new_account` but worth noting for high-value items.

### `low_feedback_count`
Fewer than 10 feedback ratings total. Seller is new to eBay or rarely transacts.

### `suspicious_price`
Listing price is more than 50% below the market median from recent completed sales.

!!! note
    This flag is suppressed automatically when the search returns a heterogeneous price range — for example, a search that mixes laptop generations spanning $200–$2,000. In that case, the median is not meaningful and flagging would produce false positives.

### `duplicate_photo`
The same image (by perceptual hash) appears on another listing. Common in scams where photos are lifted from legitimate listings.

### `scratch_dent_mentioned`
The title or description contains keywords indicating cosmetic damage, functional problems, or evasive language:

- Damage: *scratch, dent, crack, chip, broken, damaged*
- Functional: *untested, for parts, parts only, as-is, not working*
- Evasive: *read description, see description, sold as-is*

### `long_on_market`
The listing has been seen 5 or more times over 14 or more days without selling. A listing that isn't moving may be overpriced or have undisclosed problems.

### `significant_price_drop`
The current price is more than 20% below the price when Snipe first saw this listing. Sudden drops can indicate seller desperation — or a motivated seller — depending on context.

## Triple Red

When a listing hits all three of these simultaneously:

- `new_account` OR `account_under_30_days`
- `suspicious_price`
- `duplicate_photo` OR `zero_feedback` OR `established_bad_actor` OR `scratch_dent_mentioned`

The card gets a **pulsing red border glow** to make it impossible to miss in a crowded results grid.
