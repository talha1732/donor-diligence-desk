# User test script (about 15 to 20 minutes)

Goal: evidence for report section 7 (Impact). The rubric asks for "a real user tried it (a quote,
screenshot, or before-and-after time)". Record real answers only. If something goes wrong, write that down too.

## Who
One person who gives to charity and would plausibly use this: a regular donor, a giving circle member, a
family foundation trustee, or a nonprofit executive director (secondary user: "how would a careful donor
read my filings?").

Ask first: "Can I quote you in a class report, by first name and role only?" Note the answer.

## Setup (before they arrive)
- App running on your laptop: `python backend/run.py`, open http://127.0.0.1:8000.
- A stopwatch (phone).
- Two browser tabs ready for the baseline: https://projects.propublica.org/nonprofits/ and
  https://www.charitynavigator.org/.

## 1. Warm-up questions (2 minutes)
1. How do you decide where to give today? What do you look at?
2. Roughly how much time do you spend checking a charity before a gift?
3. Have you ever opened a charity's Form 990? Why or why not?

## 2. Baseline task, timed (5 minutes max)
"Using these two websites, tell me whether Connecticut Foodshare looks financially healthy, and write down
one question you would ask them before giving."
- Start the stopwatch. Stop when they give an answer or at 5:00.
- Write down: time taken, their answer, their question, anything they could not find.

## 3. App task, timed
"Now use this app. Pick up to three charities you actually care about (or use the featured ones), set your
priorities, and run it."
- Start the stopwatch when they land on the home page. Stop when they have read the memo headline and one
  charity section.
- Do not help unless they are stuck for 30 seconds. Write down every point where they hesitated.
- Screenshot their memo (Cmd+Shift+4) and the run screen.

## 4. After (5 minutes)
Ask them to answer on a 1 to 5 scale, then say why:
1. How useful was the memo for deciding whether to give? (1 = not at all, 5 = very)
2. How much did you trust the numbers? Did you click any source chips?
3. Would you use this before your year-end giving? Would you pay for it, and how much?
4. Which "question for the charity" would you actually ask?
5. What was confusing, missing, or wrong?
6. Compared with the two websites, what did the app do better or worse?

## Record the results here: `docs/evidence/user-test.md`

```
Date/time:
Tester (first name, role, consent to quote yes/no):
How they give today:
Baseline: time ____ min, answer, question, what they could not find:
App: time ____ min, charities run, run_id(s):
Hesitations / confusion:
Scores: useful _/5, trust _/5, would use _/5
Best quote (verbatim):
Changes they asked for:
Screenshots saved as: docs/evidence/user-test-*.png
```
