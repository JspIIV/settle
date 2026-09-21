# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Settle: two people bind to one claim about the world, and evidence names the winner.

Two people disagree about a fact that has not happened yet. One says the exchange
will publish proof of reserves by Friday, the other says it will not. One says the
release shipped, the other says it slipped. Ordinarily settling that needs a
trusted third party, and the trusted third party is the whole problem: it can be
absent, biased, or bought.

Settle replaces the referee with the source. The affirmer opens a claim in plain
words, names one public page where the truth will show, and sets the time it can
be resolved. A second party joins as the denier, taking the other side. After the
time passes, anyone may resolve it: the contract fetches that page itself and a
round of GenLayer validators reads it and decides whether the claim came true. The
winner is named on chain, from the evidence, with neither side and no middleman
able to move the answer.

## What it answers

    winner(id) -> address or none

for a settlement contract to pay out on: an escrow that releases to the winner, a
wager that returns the stake, a market that settles a position. The outcome is a
judgement about a public source, not a party's say-so.

## What it refuses

It resolves only what both sides joined and only after the stated time: an
unresolved or one-sided claim names no winner, and resolving early is refused.
It never decides on silence: a page that cannot be read, or that does not speak to
the claim, is UNCLEAR, and the claim stays open to be resolved again later, never
handed to a side by default. Both parties are bound to their callers, so nobody is
entered into a claim they did not take.

## Where it stops, plainly

It judges what a public page says, not whether the page is honest, and both sides
agree the source when they join. A claim worded loosely can be read two ways; name
a page a third party controls and a claim a stranger could check. It holds no
native value on this network: it names the winner, and a settlement contract reads
winner(id) and moves the money.
"""

from genlayer import *
import json

TRUE = "TRUE"
FALSE = "FALSE"
UNCLEAR = "UNCLEAR"
OUTCOMES = (TRUE, FALSE, UNCLEAR)

OPEN = "OPEN"
JOINED = "JOINED"
RESOLVED = "RESOLVED"

MAX_CLAIM = 400
MAX_URL = 300
MAX_PAGE = 6000
MAX_REASON = 300
MAX_QUOTE = 300

FETCH_FAILED = "__FETCH_FAILED__"


def _now() -> int:
    from datetime import datetime, timezone
    return int(datetime.now(timezone.utc).timestamp())


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _clip(text: str, limit: int) -> str:
    text = str(text).strip()
    return text if len(text) <= limit else text[:limit] + " [...]"


def _whole(value) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return -1


def _url_ok(url: str) -> bool:
    text = str(url).strip()
    if len(text) < 8 or len(text) > MAX_URL or " " in text:
        return False
    return text.startswith("https://") or text.startswith("http://")


def _field(raw: str, name: str, allowed, fallback: str) -> str:
    try:
        text = str(raw).strip()
        obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
        if isinstance(obj, dict):
            said = str(obj.get(name, "")).strip().upper()
            return said if said in allowed else fallback
    except Exception:
        pass
    return fallback


def _text_field(raw: str, name: str, limit: int) -> str:
    try:
        text = str(raw).strip()
        obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
        if isinstance(obj, dict):
            return _clip(str(obj.get(name, "")), limit)
    except Exception:
        pass
    return ""


def _task(claim: str, page: str) -> str:
    return f"""Two people bound themselves to one claim about the world, and named the page below
as where its truth would show. Read the page and decide whether the claim is true.

THE CLAIM, as the two of them agreed to word it:
{claim}

THE PAGE THEY BOTH NAMED AS THE SOURCE:
{page}

Decide one of:
  {TRUE} the page shows the claim is true
  {FALSE} the page was read and the claim is false, or the page shows the opposite
  {UNCLEAR} the page could not be read, or does not settle the claim either way

Judge only what the page actually says. Small differences of wording are fine if
the page settles the same fact. Do not treat an unreachable or unrelated page as
true or false: that is {UNCLEAR}, and the claim is left open rather than handed to
a side.

Reply with bare JSON and nothing else:
{{"outcome": "{TRUE}" or "{FALSE}" or "{UNCLEAR}",
  "quote": "the sentence on the page that decided it, or empty",
  "reason": "one sentence naming what decided it"}}"""


class Settle(gl.Contract):
    """Two-sided claims about the world, each settled by the page both sides named."""

    # str(id) -> the claim as JSON.
    items: TreeMap[str, str]
    ids: DynArray[str]

    def __init__(self) -> None:
        pass

    @gl.public.write
    def open(self, claim: str, source_url: str, resolve_after: str) -> str:
        """Open a claim you assert is true, the page it will show on, and when it can be resolved.

        The caller takes the affirming side. A denier joins the other side before it
        can be resolved. resolve_after is a unix timestamp; the claim cannot be
        settled until then, so neither side can rush a source that is not final yet.
        """
        affirmer = gl.message.sender_address.as_hex.lower()
        text = _clip(claim, MAX_CLAIM)
        link = str(source_url).strip()
        after = _whole(resolve_after)
        if not text:
            return json.dumps({"ok": False, "error": "state the claim in plain words"})
        if not _url_ok(link):
            return json.dumps({"ok": False, "error": "give an http(s) source URL the claim can be settled at"})
        if after < 0:
            return json.dumps({"ok": False, "error": "give resolve_after as a unix timestamp, or 0 for any time"})

        cid = str(len(self.ids))
        record = {
            "id": cid,
            "affirmer": affirmer,
            "denier": "",
            "opened_at": _now_iso(),
            "claim": text,
            "source_url": link,
            "resolve_after": after,
            "status": OPEN,
            "outcome": "",
            "winner": "",
            "loser": "",
            "reason": "",
            "quote": "",
            "resolved_at": "",
        }
        self.items[cid] = json.dumps(record)
        self.ids.append(cid)
        return json.dumps({"ok": True, "id": cid, "status": OPEN})

    @gl.public.write
    def join(self, claim_id: str) -> str:
        """Take the denying side of an open claim. The caller is bound as the denier."""
        cid = str(claim_id).strip()
        stored = self.items.get(cid, None)
        if stored is None:
            return json.dumps({"ok": False, "error": "no claim with that id"})
        record = json.loads(stored)
        if record["status"] != OPEN:
            return json.dumps({"ok": False, "error": "this claim is already " + record["status"].lower(),
                               "status": record["status"]})
        denier = gl.message.sender_address.as_hex.lower()
        if denier == record["affirmer"]:
            return json.dumps({"ok": False, "error": "the affirmer cannot also take the denying side"})
        record["denier"] = denier
        record["status"] = JOINED
        self.items[cid] = json.dumps(record)
        return json.dumps({"ok": True, "id": cid, "status": JOINED})

    @gl.public.write
    def resolve(self, claim_id: str) -> str:
        """After the time, fetch the source and name the winner. Open to anybody.

        The page is fetched by the contract itself inside the round, so neither side
        supplies the answer. TRUE gives it to the affirmer, FALSE to the denier,
        UNCLEAR leaves the claim open to be resolved again later.
        """
        cid = str(claim_id).strip()
        stored = self.items.get(cid, None)
        if stored is None:
            return json.dumps({"ok": False, "error": "no claim with that id"})
        record = json.loads(stored)
        if record["status"] == RESOLVED:
            return json.dumps({"ok": False, "error": "already resolved",
                               "outcome": record["outcome"], "winner": record["winner"]})
        if record["status"] != JOINED:
            return json.dumps({"ok": False, "error": "no one has taken the other side yet",
                               "status": record["status"]})
        if _now() < int(record["resolve_after"]):
            return json.dumps({"ok": False, "error": "too early; this claim cannot be resolved until its time",
                               "resolve_after": record["resolve_after"], "now": _now()})

        # Copy into locals before the round. Nothing inside the block reads self
        # and nothing inside it raises.
        claim = record["claim"]
        url = record["source_url"]

        def look() -> str:
            page = ""
            try:
                got = gl.nondet.web.render(url)
                page = got if isinstance(got, str) else getattr(got, "body", "")
                if isinstance(page, (bytes, bytearray)):
                    page = page.decode("utf-8", "replace")
                page = _clip(str(page), MAX_PAGE)
            except Exception:
                page = FETCH_FAILED
            if not page or page == FETCH_FAILED:
                return json.dumps({"outcome": UNCLEAR, "quote": "",
                                   "reason": "the source page could not be read"})
            try:
                return str(gl.nondet.exec_prompt(_task(claim, page)))
            except Exception as error:
                return json.dumps({"outcome": UNCLEAR, "quote": "",
                                   "reason": _clip("the prompt failed: " + str(error), MAX_REASON)})

        raw = gl.eq_principle.prompt_comparative(
            look,
            principle=(
                f"Both answers must carry the same value in the field named outcome, one of "
                f"{TRUE}, {FALSE} or {UNCLEAR}. That single field decides who wins money in a "
                "settlement built on this, so two readers differing on it are not wording a "
                "judgement differently, they disagree about whether the claim came true. The "
                "quote and the reason are not compared, and the two readers will not have fetched "
                "byte-identical copies of the page."
            ),
        )

        outcome = _field(raw, "outcome", OUTCOMES, "")
        if not outcome:
            return json.dumps({"ok": False,
                               "error": "the round produced no outcome this contract recognises",
                               "round_said": _clip(str(raw), 400)})

        record["reason"] = _text_field(raw, "reason", MAX_REASON)
        record["quote"] = _text_field(raw, "quote", MAX_QUOTE)
        record["outcome"] = outcome
        if outcome == TRUE:
            record["status"] = RESOLVED
            record["winner"] = record["affirmer"]
            record["loser"] = record["denier"]
            record["resolved_at"] = _now_iso()
        elif outcome == FALSE:
            record["status"] = RESOLVED
            record["winner"] = record["denier"]
            record["loser"] = record["affirmer"]
            record["resolved_at"] = _now_iso()
        # UNCLEAR leaves it JOINED, to be resolved again when the source settles.
        self.items[cid] = json.dumps(record)
        return json.dumps({"ok": True, "id": cid, "outcome": outcome,
                           "status": record["status"], "winner": record["winner"],
                           "reason": record["reason"]})

    # ------------------------------------------------------------------ reads

    @gl.public.view
    def winner(self, claim_id: str) -> str:
        """The address a settlement contract pays, or none until the claim is resolved."""
        cid = str(claim_id).strip()
        stored = self.items.get(cid, None)
        if stored is None:
            return json.dumps({"exists": False, "resolved": False, "winner": ""})
        record = json.loads(stored)
        return json.dumps({"exists": True, "id": cid,
                           "resolved": record["status"] == RESOLVED,
                           "outcome": record["outcome"], "winner": record["winner"]})

    @gl.public.view
    def get(self, claim_id: str) -> str:
        """The whole claim, including the deciding quote and reason once resolved."""
        cid = str(claim_id).strip()
        stored = self.items.get(cid, None)
        if stored is None:
            return json.dumps({"exists": False})
        return stored

    @gl.public.view
    def size(self) -> str:
        """How many claims are open, joined and resolved."""
        opened = 0
        joined = 0
        resolved = 0
        for position in range(len(self.ids)):
            record = json.loads(self.items[self.ids[position]])
            state = record["status"]
            if state == OPEN:
                opened += 1
            elif state == JOINED:
                joined += 1
            elif state == RESOLVED:
                resolved += 1
        return json.dumps({"total": len(self.ids), "open": opened,
                           "joined": joined, "resolved": resolved})

    @gl.public.view
    def page(self, start: str, count: str) -> str:
        """A slice of the claims, newest first, for a frontend to render."""
        total = len(self.ids)
        begin = _whole(start)
        want = _whole(count)
        if begin < 0:
            begin = 0
        if want < 1:
            want = 20
        if want > 50:
            want = 50
        out = []
        seen = 0
        position = total - 1 - begin
        while position >= 0 and seen < want:
            out.append(json.loads(self.items[self.ids[position]]))
            position -= 1
            seen += 1
        return json.dumps({"total": total, "start": begin, "count": len(out), "items": out})
