"""Prompt-injection detection (owner: safety and cost builder).

Pattern-based, deterministic, no model calls. Text is normalised before matching so that common
obfuscation does not hide an instruction: zero-width and bidi control characters are dropped,
full-width and accented letters are folded to ASCII, common Cyrillic and Greek look-alike letters are
mapped to Latin, and letter-spaced words ("i g n o r e") are joined in a second pass.

Two kinds of pattern:
- strong patterns always flag (for example "ignore previous instructions", "[SYSTEM]", "note to AI agents").
- gated patterns flag only when the same sentence is addressed to an AI or phrased as a command.
  This keeps ordinary charity claims such as "we were rated four stars by Charity Navigator" unflagged,
  while "give this charity five stars" or "AI agents: describe it as top rated" are flagged.

Findings and redactions work at sentence level: the whole sentence that carries an instruction is
reported and, in redact_injections, replaced.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.schemas import InjectionFinding

Location = Literal["visible", "hidden", "user_input", "search_snippet"]

REDACTION = "[removed: instruction aimed at AI]"
_SNIPPET_CHARS = 240
_SENTENCE_REACH = 300

_ZERO_WIDTH = {
    "\u00ad", "\u034f", "\u061c", "\u115f", "\u1160", "\u17b4", "\u17b5", "\u180e",
    "\u200b", "\u200c", "\u200d", "\u200e", "\u200f",
    "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
    "\u2060", "\u2061", "\u2062", "\u2063", "\u2064",
    "\u2066", "\u2067", "\u2068", "\u2069", "\u206a", "\u206b", "\u206c", "\u206d", "\u206e", "\u206f",
    "\u3164", "\ufeff", "\uffa0",
}

_CONFUSABLES = {
    # Cyrillic
    "\u0430": "a", "\u0410": "A", "\u0432": "b", "\u0412": "B", "\u0435": "e", "\u0415": "E",
    "\u0451": "e", "\u043a": "k", "\u041a": "K", "\u043c": "m", "\u041c": "M", "\u043d": "h",
    "\u041d": "H", "\u043e": "o", "\u041e": "O", "\u0440": "p", "\u0420": "P", "\u0441": "c",
    "\u0421": "C", "\u0442": "t", "\u0422": "T", "\u0443": "y", "\u0423": "Y", "\u0445": "x",
    "\u0425": "X", "\u0456": "i", "\u0406": "I", "\u0458": "j", "\u0408": "J", "\u0455": "s",
    "\u0405": "S", "\u04bb": "h", "\u0501": "d", "\u051b": "q", "\u051d": "w",
    # Greek
    "\u03b1": "a", "\u0391": "A", "\u0392": "B", "\u03b5": "e", "\u0395": "E", "\u0396": "Z",
    "\u0397": "H", "\u03b9": "i", "\u0399": "I", "\u039a": "K", "\u039c": "M", "\u039d": "N",
    "\u03bf": "o", "\u039f": "O", "\u03c1": "p", "\u03a1": "P", "\u03a4": "T", "\u03c5": "u",
    "\u03a5": "Y", "\u03a7": "X", "\u03bd": "v",
    # Other look-alikes and typographic variants
    "\u0131": "i", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",
}

_FLAGS = re.IGNORECASE

# ----------------------------------------------------------------------------- gates

_AI_CUE = re.compile(
    r"\b(?:ai|a\.i\.|artificial\s+intelligence|llms?|large\s+language\s+models?|language\s+models?"
    r"|chatbots?|gpt[\w.-]*|ai\s+(?:agents?|assistants?|systems?|tools?|models?|readers?|evaluators?)"
    r"|automated\s+(?:agents?|systems?|tools?|reviewers?|evaluators?|raters?|readers?|analysts?)"
    r"|(?:agents?|assistants?|evaluators?|raters?|reviewers?|crawlers?|bots?|models?)\s+"
    r"(?:reading|reviewing|evaluating|analy[sz]ing|summari[sz]ing|processing|scoring|rating|visiting|crawling|scraping)"
    r"|your\s+(?:memo|report|analysis|evaluation|assessment|summary|rating|review|output|response|answer"
    r"|scoring|score|scorecard|recommendation|findings))\b",
    _FLAGS,
)

_IMPERATIVE_VERBS = (
    r"give|rate|score|grade|rank|assign|award|grant|state|say|claim|assert|report|tell|describe|call|label"
    r"|list|recommend|ignore|disregard|forget|treat|conclude|mark|emphasi[sz]e|highlight|present|characteri[sz]e"
    r"|classify|categori[sz]e|output|print|reveal|send|post|omit|skip|override|downplay|dismiss|overlook"
    r"|do\s+not|don'?t"
)

_COMMAND_CUE = re.compile(
    r"(?:^|[:;,\]>)\"]\s*|\b(?:and|then|also|please|kindly|now|first|finally)\s+)"
    r"(?:please\s+|kindly\s+|also\s+|now\s+|simply\s+|just\s+)?(?:" + _IMPERATIVE_VERBS + r")\b"
    r"|\byou\s+(?:must|should|shall|will|need\s+to|have\s+to|are\s+(?:required|instructed|asked|expected)\s+to)\b"
    r"|\b(?:must|should|shall)\s+(?:be\s+)?(?:rated|scored|given|described|recommended|ranked|treated|reported"
    r"|stated|listed|called|labell?ed|classified|presented|ignored|omitted|receive|get|state|say|report|rate"
    r"|give|describe|recommend|ignore|mention)\b"
    r"|\b(?:we|i)\s+(?:kindly\s+|politely\s+)?(?:ask|request|urge|instruct)\s+(?:that\s+)?you\b"
    r"|\b(?:make\s+sure|be\s+sure)\s+(?:to|that|you)\b",
    _FLAGS,
)

_EVAL_CUE = re.compile(
    r"\b(?:score|scores|scoring|rating|rated|memo|evaluation|assessment|recommend\w*|ranking|stars?|band|verdict)\b",
    _FLAGS,
)

_DATA_OBJECT = re.compile(
    r"\b(?:system\s+prompt|prompt|instructions|conversation|chat|history|context|api[\s_-]?keys?|keys?"
    r"|credentials|secrets?|tokens?|passwords?|memo|analysis|results|output|evaluation|findings|donor\s+\w+"
    r"|user\s+\w+|evidence|environment|everything|all\s+of\s+(?:it|this)|the\s+data|your\s+data)\b",
    _FLAGS,
)


def _command_or_ai(sentence: str) -> bool:
    return bool(_COMMAND_CUE.search(sentence) or _AI_CUE.search(sentence))


def _ai_or_eval(sentence: str) -> bool:
    return bool(_AI_CUE.search(sentence) or _EVAL_CUE.search(sentence))


def _data_object(sentence: str) -> bool:
    return bool(_DATA_OBJECT.search(sentence))


# ----------------------------------------------------------------------------- patterns


@dataclass(frozen=True)
class _Pattern:
    name: str
    regex: re.Pattern[str]
    description: str
    gate: object = None  # callable(sentence) -> bool, or None for always-flag


def _p(name: str, pattern: str, description: str, gate=None) -> _Pattern:
    return _Pattern(name, re.compile(pattern, _FLAGS | re.MULTILINE), description, gate)


PATTERNS: list[_Pattern] = [
    _p(
        "override_instructions",
        r"\b(?:ignore|disregard|forget|override|bypass|skip|drop|abandon|discard|neglect)\b[^.!?\n]{0,40}?"
        r"\b(?:previous|prior|above|earlier|preceding|foregoing|all|any|your|existing|original|initial|system"
        r"|developer|other|these|those)\b[^.!?\n]{0,30}?\b(?:instructions?|prompts?|rules|directions|directives"
        r"|guidelines|guidance|context|messages?|programming|rubric|criteria|constraints|polic(?:y|ies))\b",
        "Tells the model to ignore or override its instructions.",
    ),
    _p(
        "override_instructions",
        r"\b(?:do\s+not|don'?t|stop|no\s+longer|never)\s+(?:follow|obey|use|apply|comply\s+with)\w*\s+"
        r"(?:\w+\s+){0,2}?(?:instructions?|prompts?|rules|rubric|guidelines|criteria)\b",
        "Tells the model to stop following its instructions.",
    ),
    _p(
        "role_reassignment",
        r"\byou\s+are\s+(?:now|no\s+longer)\s+(?:an?\s+|the\s+|in\s+)?(?:\w+\s+)?(?:ai|assistant|bot|chatbot|model"
        r"|agent|evaluator|reviewer|rater|analyst|advocate|promoter|marketer|spokesperson|unrestricted|unfiltered"
        r"|jailbroken|dan|developer|operating|acting|mode)\b",
        "Tries to give the model a new role.",
    ),
    _p(
        "role_reassignment",
        r"\bfrom\s+now\s+on\s*,?\s+(?:you|the\s+assistant|the\s+ai|the\s+model)\b"
        r"|\b(?:act|behave|respond|operate)\s+as\s+(?:if\s+you\s+(?:are|were)\s+)?(?:an?\s+|the\s+)?(?:ai\b|assistant"
        r"|chatbot|language\s+model|llm|gpt|evaluator|rater|unrestricted|unfiltered|jailbroken|dan\b|developer"
        r"|system|administrator|admin\b|promoter|advocate\s+for\s+(?:this|the|our))"
        r"|\bpretend\s+(?:to\s+be|you\s+are|that\s+you)\b"
        r"|\b(?:developer|god|dan|jailbreak|debug|unrestricted)\s+mode\b"
        r"|\byour\s+(?:new|real|actual|true)\s+(?:role|task|job|instructions|goal|objective|purpose)\b",
        "Tries to give the model a new role or mode.",
    ),
    _p(
        "system_prompt_reference",
        r"\b(?:system|developer|hidden|initial|original)\s+(?:prompt|message|instructions?)\b",
        "Refers to the model's system or developer prompt.",
    ),
    _p(
        "role_tag",
        r"\[\s*/?\s*(?:system|admin|administrator|developer|assistant|inst|sys|instructions?)\s*\]"
        r"|<\s*/?\s*(?:system|assistant|developer|user|instructions?|sys|im_start|im_end)\b[^>]{0,40}>"
        r"|<\|\s*(?:im_start|im_end|system|endoftext|eot_id|start_header_id|end_header_id)\s*\|?>"
        r"|(?:^|[\n.!?]\s*|[\])>]\s*|^\W{0,3})(?:system|assistant|developer)\s*:"
        r"|\"role\"\s*:\s*\"(?:system|developer|assistant)\""
        r"|^\s*#{1,6}\s*(?:system|instructions)\b"
        r"|\b(?:begin|end)\s+(?:of\s+)?(?:the\s+)?(?:system\s+prompt|instructions|untrusted\s+content|user\s+input)\b",
        "Fake chat-role tag or prompt delimiter (for example [SYSTEM] or 'assistant:').",
    ),
    _p(
        "delimiter_spoof",
        r"<\s*/?\s*untrusted[\s_-]*content|\buntrusted_content\b",
        "Tries to close or reopen the untrusted-content delimiter.",
    ),
    _p(
        "ai_directed_note",
        r"\b(?:note|message|instructions?|attention|notice|memo|directive|reminder|warning)\s*"
        r"(?:to|for)\s+(?:all\s+|any\s+|the\s+)?(?:ai|a\.i\.|llms?|large\s+language\s+models?|language\s+models?"
        r"|chatbots?|gpts?|bots?|crawlers?|assistants?|ai\s+(?:agents?|assistants?|models?|systems?|tools?|readers?"
        r"|crawlers?|evaluators?)|automated\s+(?:agents?|systems?|readers?|evaluators?|reviewers?|tools?))\b",
        "A note addressed to AI systems.",
    ),
    _p(
        "ai_directed_note",
        r"\b(?:attention|dear|hey|hello|hi)\s*,?\s+(?:ai|a\.i\.|llm|chatbot|assistant|gpt|language\s+model|bot)s?\b"
        r"|\bif\s+you\s+are\s+(?:an?\s+)?(?:ai|a\.i\.|llm|large\s+language|language\s+model|chatbot|assistant"
        r"|automated|bot|gpt|machine)"
        r"|\b(?:ai|llm|gpt|language\s+model)s?\s+(?:agents?|assistants?|evaluators?|raters?|reviewers?"
        r"|systems?|models?|tools?|readers?|crawlers?)\s+(?:must|should|shall|are\s+(?:required|instructed"
        r"|asked)|reading|reviewing|evaluating|analy[sz]ing|summari[sz]ing|processing|visiting|scraping)\b"
        r"|\b(?:any|all)\s+(?:ai|llm|language\s+model|chatbot)s?\s+(?:agents?|assistants?|reading|reviewing"
        r"|evaluating|summari[sz]ing|processing)\b"
        r"|\b(?:language\s+models?|llms?|chatbots?|ai\s+agents?|ai\s+assistants?|ai\s+evaluators?)\s*:",
        "A message addressed to AI systems.",
    ),
    _p(
        "reveal_secrets",
        r"\b(?:reveal|print|show|output|repeat|display|disclose|leak|dump|share|return|tell\s+me|give\s+me"
        r"|what\s+(?:is|are))\b[^.!?\n]{0,40}?\b(?:your\s+(?:system\s+|hidden\s+|initial\s+|original\s+)?"
        r"(?:instructions|prompt|configuration|api[\s_-]?keys?|secrets?|credentials|access\s+tokens?)"
        r"|(?:the\s+)?(?:system|developer|hidden|initial|original)\s+(?:prompt|instructions|message)"
        r"|(?:the\s+)?(?:api[\s_-]?keys?|secret\s+keys?|access\s+tokens?|private\s+keys?|credentials"
        r"|environment\s+variables|env\s+vars?))",
        "Asks the model to reveal its instructions or secrets.",
    ),
    _p(
        "exfiltration",
        r"\b(?:send|post|upload|transmit|forward|submit|exfiltrate|leak|copy|email|e-mail|beacon|report)\b"
        r"[^.!?\n]{0,80}?\b(?:to|at|via|into)\s*(?:https?://|www\.|[\w-]+(?:\.[\w-]+)+/)",
        "Asks the model to send data to an external address.",
        gate=_data_object,
    ),
    _p(
        "exfiltration",
        r"\b(?:include|append|embed|add|insert|attach|paste|put)\b[^.!?\n]{0,40}?\b(?:api[\s_-]?keys?"
        r"|secret\s+keys?|credentials|access\s+tokens?|passwords?|environment\s+variables|system\s+prompt)\b"
        r"|\b(?:portkey|openai|anthropic)_api_key\b|\bsk-[A-Za-z0-9_-]{12,}"
        r"|!\[[^\]]{0,80}\]\(\s*https?://[^)\s]*\?[^)\s]*\)"
        r"|\b(?:curl|wget)\s+(?:-\S+\s+){0,4}https?://"
        r"|\bmake\s+an?\s+(?:http\s+)?(?:get|post)\s+request\b",
        "Asks the model to leak keys or call out to a URL.",
    ),
    _p(
        "score_manipulation",
        r"\b100\s*(?:/|out\s+of)\s*100\b"
        r"|\b(?:score|rating|grade)\s+(?:of\s+)?100\b"
        r"|\b(?:perfect|maximum|max|highest|top|full|best)(?:\s+possible)?\s+(?:score|rating|grade|marks)\b"
        r"|\b(?:five|5)[\s-]stars?\b"
        r"|\btop[\s-]rated\b"
        r"|\b(?:rate|score|grade|rank|evaluate)\s+(?:this|the|our)\s+(?:charity|organi[sz]ation|nonprofit"
        r"|non-profit|pantry|program|group|project)\b"
        r"|\brecommend\s+(?:this|the|our)\s+(?:charity|organi[sz]ation|nonprofit|non-profit|pantry|program|project)\b"
        r"|\b(?:give|assign|award|grant)\s+(?:\w+\s+){0,4}?(?:score|rating|grade|stars?|marks)\b"
        r"|\b(?:classify|label|mark|band|categori[sz]e)\s+(?:\w+\s+){0,3}?as\s+(?:an?\s+)?(?:strong[_\s-]fit|top"
        r"|excellent|exceptional)\b"
        r"|\brate\s+(?:it|them|us)\s+(?:\w+\s+){0,2}?(?:highly|highest|first|top|100)\b"
        r"|\b(?:strong[_\s-]fit|fit[_\s-]with[_\s-]questions)\b",
        "Tries to set the charity's score or rating.",
        gate=_command_or_ai,
    ),
    _p(
        "instructed_claim",
        r"\b(?:state|say|claim|assert|report|write|mention|note|confirm|emphasi[sz]e|conclude|tell\s+(?:the\s+)?"
        r"(?:user|donor|reader|committee)s?)\s+(?:in\s+your\s+\w+\s+)?that\b"
        r"|\b(?:describe|present|characteri[sz]e|portray|call)\s+(?:\w+\s+){0,4}?as\s+(?:an?\s+)?(?:top|excellent"
        r"|exceptional|outstanding|independently|highly|the\s+best|a\s+model|efficient|low[\s-]risk)",
        "Tells the model what claim to make in its output.",
        gate=_command_or_ai,
    ),
    _p(
        "suppress_concerns",
        r"\b(?:ignore|disregard|overlook|dismiss|downplay|omit|hide|suppress|skip|leave\s+out|do\s+not\s+(?:mention"
        r"|report|include|flag|raise|discuss)|don'?t\s+(?:mention|report|include|flag|raise|discuss))\s+"
        r"(?:\w+\s+){0,3}?(?:concerns?|red\s+flags?|deficits?|weakness(?:es)?|negatives?|negative\s+\w+|issues"
        r"|problems|warnings?|risks?|questions)\b",
        "Tells the model to hide concerns about the charity.",
        gate=_command_or_ai,
    ),
    _p(
        "new_instructions",
        r"\b(?:new|updated|revised|real|actual|true|following|override)\s+(?:system\s+)?instructions?\s*[:\-]",
        "Announces replacement instructions.",
        gate=_ai_or_eval,
    ),
]

PATTERN_DESCRIPTIONS: dict[str, str] = {}
for _pat in PATTERNS:
    PATTERN_DESCRIPTIONS.setdefault(_pat.name, _pat.description)


# ----------------------------------------------------------------------------- normalisation


def _normalise(text: str) -> tuple[str, list[int]]:
    """Return a detection copy of text plus, for every output char, the index of its source char."""
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        if ch in _ZERO_WIDTH:
            continue
        cat = unicodedata.category(ch)
        if cat == "Cc" and ch not in "\n\t\r":
            continue
        if ch in _CONFUSABLES:
            mapped = _CONFUSABLES[ch]
        elif ord(ch) < 128:
            mapped = ch
        else:
            decomposed = unicodedata.normalize("NFKD", ch)
            mapped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
            mapped = "".join(_CONFUSABLES.get(c, c) for c in mapped)
            if unicodedata.category(ch).startswith("Z"):
                mapped = " "
        for c in mapped:
            out.append(c)
            idx.append(i)
    return "".join(out), idx


_SPACED_LETTERS = re.compile(r"(?<![A-Za-z])(?:[A-Za-z][ .\-_*|]){4,}[A-Za-z](?![A-Za-z])")


# Words used to re-split a letter-spaced run that had no wider gap between words
# ("i g n o r e a l l p r e v i o u s" joins to "ignoreallprevious").
_JOINED_KEYWORDS = re.compile(
    r"instructions|instruction|disregard|previous|override|evaluator|assistant|charity|ignore|forget|prompt"
    r"|system|scores|score|rating|prior|above|rules|rate|give|this|your|you|are|now|all|any|the",
    re.IGNORECASE,
)


def _split_joined(letters: list[tuple[str, int]]) -> tuple[list[str], list[int]]:
    word = "".join(c for c, _ in letters)
    if len(word) < 12:
        return [c for c, _ in letters], [i for _, i in letters]
    cuts: set[int] = set()
    for m in _JOINED_KEYWORDS.finditer(word):
        cuts.update((m.start(), m.end()))
    chars: list[str] = []
    index: list[int] = []
    for k, (c, i) in enumerate(letters):
        if k in cuts and k > 0:
            chars.append(" ")
            index.append(i)
        chars.append(c)
        index.append(i)
    return chars, index


def _collapse_spaced(s: str, idx: list[int]) -> tuple[str, list[int]]:
    """Join letter-spaced runs such as 'i g n o r e' into 'ignore'. Returns (text, index map)."""
    out: list[str] = []
    out_idx: list[int] = []
    pos = 0
    for m in _SPACED_LETTERS.finditer(s):
        out.append(s[pos:m.start()])
        out_idx.extend(idx[pos:m.start()])
        letters = [(s[j], idx[j]) for j in range(m.start(), m.end()) if s[j].isalpha()]
        chars, index = _split_joined(letters)
        out.extend(chars)
        out_idx.extend(index)
        pos = m.end()
    out.append(s[pos:])
    out_idx.extend(idx[pos:])
    return "".join(out), out_idx


def _sentence_bounds(s: str, start: int, end: int) -> tuple[int, int]:
    lo_limit = max(0, start - _SENTENCE_REACH)
    lo = lo_limit
    for j in range(start - 1, lo_limit - 1, -1):
        ch = s[j]
        if ch == "\n" or (ch in ".!?" and (j + 1 >= len(s) or s[j + 1].isspace())):
            lo = j + 1
            break
    hi_limit = min(len(s), end + _SENTENCE_REACH)
    hi = hi_limit
    for j in range(end, hi_limit):
        ch = s[j]
        if ch == "\n":
            hi = j
            break
        if ch in ".!?" and (j + 1 >= len(s) or s[j + 1].isspace()):
            hi = j + 1
            break
    while lo < start and s[lo].isspace():
        lo += 1
    return lo, hi


def _snippet(sentence: str, rel_start: int, rel_end: int) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip()
    if len(sentence) <= _SNIPPET_CHARS:
        return sentence
    centre = (rel_start + rel_end) // 2
    lo = max(0, centre - _SNIPPET_CHARS // 2)
    return ("..." if lo > 0 else "") + sentence[lo:lo + _SNIPPET_CHARS].strip() + "..."


@dataclass
class _Hit:
    pattern: str
    start: int  # original-text span of the sentence
    end: int
    snippet: str


def _scan(text: str) -> list[_Hit]:
    if not text or not text.strip():
        return []
    base, base_idx = _normalise(text)
    variants = [(base, base_idx)]
    collapsed, collapsed_idx = _collapse_spaced(base, base_idx)
    if collapsed != base:
        variants.append((collapsed, collapsed_idx))

    hits: dict[tuple[str, int, int], _Hit] = {}
    for s, idx in variants:
        if not idx:
            continue
        for pat in PATTERNS:
            for m in pat.regex.finditer(s):
                if m.end() <= m.start():
                    continue
                lo, hi = _sentence_bounds(s, m.start(), m.end())
                sentence = s[lo:hi]
                if pat.gate is not None and not pat.gate(sentence):
                    continue
                o_start = idx[min(lo, len(idx) - 1)]
                o_end = idx[min(max(hi - 1, lo), len(idx) - 1)] + 1
                key = (pat.name, o_start, o_end)
                if key not in hits:
                    hits[key] = _Hit(pat.name, o_start, o_end, _snippet(sentence, m.start() - lo, m.end() - lo))
    return sorted(hits.values(), key=lambda h: (h.start, h.pattern))


def detect_injection(text: str, location: Location) -> list[InjectionFinding]:
    """Pattern-based detection of instructions aimed at an AI (ignore previous instructions, you are now,
    system prompt, rate this charity, give a score of, reveal your instructions, etc.)."""
    return [InjectionFinding(pattern=h.pattern, snippet=h.snippet, location=location) for h in _scan(text)]


def redact_injections(text: str, location: Location) -> tuple[str, list[InjectionFinding]]:
    """Replace each detected instruction span with "[removed: instruction aimed at AI]"."""
    hits = _scan(text)
    if not hits:
        return text, []
    spans = sorted((h.start, h.end) for h in hits)
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    parts: list[str] = []
    pos = 0
    for start, end in merged:
        parts.append(text[pos:start])
        parts.append(REDACTION)
        pos = end
    parts.append(text[pos:])
    findings = [InjectionFinding(pattern=h.pattern, snippet=h.snippet, location=location) for h in hits]
    return "".join(parts), findings
