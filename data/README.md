# data/

This directory is **intentionally empty in the public repository** to keep
real tender documents private.

## Why is it empty?

Real tender / bid PDFs and the internal CK Excel sheet contain
company names, prices, and product details that may be considered
business-sensitive.

## How to obtain sample data for demo / e2e tests

1. Run `python tests/generate_fixtures.py` to produce the
   **synthetic** `tender.pdf` and `bid.pdf` files used by
   `tests/test_smoke.py` and the demo CLI.
2. Place real PDFs into `data/` if you have legal permission to share them.

## Regenerate the checklist

The 61-row 直投 CK table is regenerated from the source Excel on every run:

```
python -m tenderguard.cli parse   --excel data/source/售前CK.xlsx   --output data/normalized/direct_tender_checks_v3.json
```

(You need to obtain the Excel from your own business source.)
