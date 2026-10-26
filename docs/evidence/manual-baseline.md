# Manual baseline walkthrough: checking one charity the usual way

**What this is.** A task walkthrough done on 2026-10-26 by the project's AI coding assistant in a real browser
(Chrome), following the baseline task in `docs/user-test-script.md`: "Using ProPublica and Charity Navigator,
tell me whether Connecticut Foodshare looks financially healthy, and write down one question you would ask
them before giving." It counts what the free tools show and what a donor would still have to do. **It is not a
user test and does not time a person**; the user test is separate.

## Steps and what each source gives

1. **ProPublica Nonprofit Explorer search** for "Connecticut Foodshare" returns **two organizations with the
   same name** (EIN 06-1063025 and EIN 22-2474771), so the donor first has to work out which one is the food
   bank.
2. **ProPublica organization page** (`projects.propublica.org/nonprofits/organizations/61063025`):
   - About **30 screens long** on a laptop (24,600 pixels at a 1280x800 window), 25,800 characters of text and
     **55 filing and PDF links**.
   - For each fiscal year it shows about **19 extracted figures**: revenue, expenses, net income, net assets,
     ten revenue lines with their share of revenue, three expense lines (executive compensation, professional
     fundraising fees, other salaries) with their share of expenses, and total assets, liabilities and net
     assets, plus key people's pay.
   - It does **not** show: growth over several years, average margin, reserves in months of expenses,
     liabilities as a share of assets, revenue concentration, program-spending share (Form 990 Part IX is not
     extracted), any outcome evidence, or questions to ask.
   - To rebuild the app's financial view for three years, a donor would copy about **24 figures** (eight per
     year) into a spreadsheet and compute about **ten ratios**, then repeat for each charity being compared.
   - The web page already shows **fiscal 2025** (revenue $128,745,294; expenses $131,683,281), while ProPublica's
     free API, which the app uses, has extracted data only through fiscal 2024 (revenue $120.2M; expenses
     $122.9M). The app is a year behind for this charity; the report's limits section discloses this lag.
3. **Charity Navigator profile** (`charitynavigator.org/ein/061063025`): **89%, "Three-Star Charity"**, four
   beacons completed (Accountability & Finance, Impact & Measurement, Leadership & Planning, Culture &
   Compensation) and pass/fail accountability checks from the fiscal 2025 Form 990 (audited statements, no
   loans to officers, website disclosures, and so on). One score for every donor; no weighting to the donor's
   priorities and no questions to ask; the financial detail sits behind further tabs.
4. **The charity's own website** is still needed for outcomes (an annual report and a community impact report
   on ctfoodshare.org).

## The same task in the app

One run on Connecticut Foodshare: about 30 to 80 seconds (median 40 for one charity) and under a cent. It
computes 16 metrics from the filings and flags the 17th, program-spending share, as unavailable, reads up to three website pages, links every figure in its findings to its source, rates the outcome
evidence (level 2 of 4: outputs reported), scores five dimensions weighted to the donor, and lists the
questions to ask (for example what drove the deficits and how much of the work reaches New Haven).

**Charity Navigator 89% versus the app's 68 ("fit with questions").** The two do not contradict each other;
they measure different things. Charity Navigator's score rests heavily on accountability checks and Form 990
Part IX ratios that the free API does not include. The app's lower score reflects two years of deficits and
expenses growing faster than revenue, weighted to the donor's priorities, and it turns those into questions
for the charity rather than a verdict.

Screenshots: `docs/evidence/manual-baseline/propublica-org-page.webp`,
`docs/evidence/manual-baseline/charity-navigator-profile.webp`.
