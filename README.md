# Settle

**Two people bind to one claim about the world, and evidence names the winner.** A settlement primitive for GenLayer.

Two people disagree about a fact that has not happened yet. One says the exchange will publish proof of reserves by Friday, the other says it will not. Settling that ordinarily needs a trusted third party, and the trusted third party is the whole problem: it can be absent, biased, or bought.

Settle replaces the referee with the source.

## How it works

1. **`open(claim, source_url, resolve_after)`** — the caller takes the **affirming** side: a claim in plain words, one public page where its truth will show, and a unix timestamp before which it cannot be resolved. Bound to `gl.message.sender_address`.
2. **`join(id)`** — a second caller takes the **denying** side, bound as the denier.
3. **`resolve(id)`** — open to anybody, only after the time. The contract **fetches the page itself** and a GenLayer round reads it: `TRUE` gives the win to the affirmer, `FALSE` to the denier, `UNCLEAR` (unreadable or off-topic) leaves the claim open to be resolved again later.
4. **`winner(id)`** — the address a settlement contract pays.

Reads: `get(id)`, `size()`, `page(start, count)`.

## Why it needs GenLayer

Whether a public page "settles a claim" is a judgement over real-world text that no ordinary contract can make and no single referee should be trusted to make. GenLayer validators each fetch the page and reach consensus on one categorical field, so the winner is named from evidence, with neither side able to move the answer.

## What it refuses

- **Only resolves what both sides joined, and only after the time.** A one-sided or too-early claim names no winner; resolving early is refused.
- **Never decides on silence.** A page that cannot be read, or does not speak to the claim, is `UNCLEAR`; the claim stays open, never handed to a side by default.
- **Binds both parties to their callers.** Nobody is entered into a claim they did not take, and the affirmer cannot also deny.

## Live

- **Contract (GenLayer Asimov):** `0x10b5C0B611ffF6721f70ca63C4eC13a2E4D481B7`
- Explorer: https://explorer-asimov.genlayer.com/address/0x10b5C0B611ffF6721f70ca63C4eC13a2E4D481B7

## Proven on Asimov

`scripts/prove.mjs`, `results/proved.json` (padv affirms, ppub denies):
- "the advisory has been published" against a page that says PUBLISHED → **TRUE** → affirmer wins.
- "the Foundation has launched a public token sale" against a page that denies any token → **FALSE** → denier wins.
- a claim whose `resolve_after` is in the future → `resolve` refused, the claim stays `JOINED`.

## Try it

```
genlayer call 0x10b5C0B611ffF6721f70ca63C4eC13a2E4D481B7 size
genlayer call 0x10b5C0B611ffF6721f70ca63C4eC13a2E4D481B7 get --args '"0"'
```

Reproduce: `AT=0x10b5C0B611ffF6721f70ca63C4eC13a2E4D481B7 PADV=<pw> PPUB=<pw> node scripts/prove.mjs` (after `npm i`).

## Where it stops, plainly

It judges what a public page says, not whether the page is honest, and both sides agree the source when they join. A claim worded loosely can be read two ways; name a page a third party controls and a claim a stranger could check. It holds no native value on this network: it names the winner, and a settlement contract reads `winner(id)` and moves the money.

## Licence

AGPL-3.0-or-later.
