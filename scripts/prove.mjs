// Prove Settle end to end on GenLayer Asimov.
//
//   AT=0x... PADV=<padv pw> PPUB=<ppub pw> node scripts/prove.mjs
//
// padv affirms, ppub denies. Two claims settled from their source, plus the two
// refusals that matter (resolving before the time, and both sides bound):
//   - "the advisory has been published", source says PUBLISHED -> TRUE  -> affirmer wins
//   - "the Foundation has launched a public token sale", source denies it -> FALSE -> denier wins
//   - a claim whose resolve_after is in the future -> resolve refused, stays JOINED
import { Wallet } from 'ethers';
import { createClient, createAccount } from 'genlayer-js';
import { testnetAsimov } from 'genlayer-js/chains';
import fs from 'fs';
import os from 'os';
import path from 'path';
import url from 'url';

const AT = process.env.AT;
const PADV = process.env.PADV || '';
const PPUB = process.env.PPUB || '';
if (!AT || !PADV || !PPUB) { console.error('set AT, PADV and PPUB'); process.exit(1); }

const ROOT = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');
const KS = path.join(os.homedir(), '.genlayer', 'keystores');
async function acct(file, pw) {
  const w = await Wallet.fromEncryptedJson(fs.readFileSync(path.join(KS, file), 'utf8'), pw);
  return { addr: w.address.toLowerCase(), client: createClient({ chain: testnetAsimov, account: createAccount(w.privateKey) }) };
}
const padv = await acct('padv.json', PADV);   // affirmer
const ppub = await acct('ppub.json', PPUB);   // denier
const anybody = createClient({ chain: testnetAsimov });

const RAW = 'https://raw.githubusercontent.com/JspIIV/settle/master/docs/';
const PAST = '1700000000';
const FUTURE = String(Math.floor(Date.now() / 1000) + 100000);
const BET_TRUE = { claim: 'The GLSA-2026-001 security advisory has been published.', url: RAW + 'advisory-published.txt' };
const BET_FALSE = { claim: 'The Foundation has launched a public token sale.', url: RAW + 'no-token-sale.txt' };

const out = [];
const say = l => { console.log(l); out.push(l); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const transient = e => /-32005|-32006|-32029|-32603|at capacity|rate limit|gas rate|reverted.*consensus|consensus.*reverted|backpressure|fetch failed|timeout|502|503|429|ECONNRESET/i
  .test(String(e?.details || e?.shortMessage || e?.message || e));

const read = async (fn, args = []) => JSON.parse(await anybody.readContract({ address: AT, functionName: fn, args }));
async function write(who, fn, args) {
  for (let a = 1; ; a++) {
    try { return await who.client.writeContract({ address: AT, functionName: fn, args, value: 0n }); }
    catch (e) { if (!transient(e) || a >= 8) throw e; say(`  (${fn} transient, wait ${8 * a}s)`); await sleep(8000 * a); }
  }
}
async function pollGet(id, done, label) {
  for (let i = 0; i < 40; i++) {
    await sleep(12000);
    let r; try { r = await read('get', [id]); } catch { continue; }
    if (done(r)) { say(`  ${label} (${(i + 1) * 12}s)`); return r; }
  }
  throw new Error('timed out polling ' + label);
}
async function opened(before) {
  for (let i = 0; i < 20; i++) { const s = await read('size'); if (s.total > before) return String(s.total - 1); await sleep(4000); }
  throw new Error('claim not opened');
}

say('Settle, proven on GenLayer Asimov');
say('  contract ' + AT);
say('  affirmer (padv) ' + padv.addr);
say('  denier   (ppub) ' + ppub.addr);
say('');

// bet 0: true -> affirmer wins
let n = (await read('size')).total;
await write(padv, 'open', [BET_TRUE.claim, BET_TRUE.url, PAST]);
const id0 = await opened(n);
await write(ppub, 'join', [id0]);
await pollGet(id0, r => r.status === 'JOINED', 'bet0 joined');
say('resolving bet0 (advisory published)...');
await write(padv, 'resolve', [id0]);
const r0 = await pollGet(id0, r => r.status === 'RESOLVED', 'bet0 resolved');
say('  outcome ' + r0.outcome + ' -> winner ' + (r0.winner === padv.addr ? 'affirmer' : r0.winner === ppub.addr ? 'denier' : r0.winner));
say('  reason: ' + (r0.reason || '(none)'));
say('');

// bet 1: false -> denier wins
n = (await read('size')).total;
await write(padv, 'open', [BET_FALSE.claim, BET_FALSE.url, PAST]);
const id1 = await opened(n);
await write(ppub, 'join', [id1]);
await pollGet(id1, r => r.status === 'JOINED', 'bet1 joined');
say('resolving bet1 (fake token sale)...');
await write(padv, 'resolve', [id1]);
const r1 = await pollGet(id1, r => r.status === 'RESOLVED', 'bet1 resolved');
say('  outcome ' + r1.outcome + ' -> winner ' + (r1.winner === padv.addr ? 'affirmer' : r1.winner === ppub.addr ? 'denier' : r1.winner));
say('  reason: ' + (r1.reason || '(none)'));
say('');

// bet 2: future resolve_after -> resolve refused
n = (await read('size')).total;
await write(padv, 'open', [BET_TRUE.claim, BET_TRUE.url, FUTURE]);
const id2 = await opened(n);
await write(ppub, 'join', [id2]);
await pollGet(id2, r => r.status === 'JOINED', 'bet2 joined');
say('trying to resolve bet2 before its time...');
await write(padv, 'resolve', [id2]);
await sleep(6000);
const r2 = await read('get', [id2]);
say('  bet2 status after early resolve: ' + r2.status);
say('');

const w0 = await read('winner', [id0]);
const w1 = await read('winner', [id1]);
const size = await read('size');
say('winner(bet0)=' + (w0.winner === padv.addr ? 'affirmer' : 'denier') + ' ; winner(bet1)=' + (w1.winner === ppub.addr ? 'denier' : 'affirmer'));
say('register: ' + JSON.stringify(size));

const checks = [
  ['a true claim resolves TRUE', r0.outcome === 'TRUE'],
  ['and the affirmer wins it', r0.winner === padv.addr],
  ['a false claim resolves FALSE', r1.outcome === 'FALSE'],
  ['and the denier wins it', r1.winner === ppub.addr],
  ['winner() names the right side for a settlement to pay', w0.winner === padv.addr && w1.winner === ppub.addr],
  ['resolving before the time is refused, the claim stays joined', r2.status === 'JOINED'],
  ['the register counts two resolved and one still joined', size.resolved === 2 && size.joined === 1],
];
say('');
for (const [label, ok] of checks) say((ok ? '  ok   ' : ' FAIL  ') + label);
const failed = checks.filter(([, ok]) => !ok);
say('');
say(failed.length ? `${failed.length} of ${checks.length} checks failed` : `${checks.length} checks. The evidence named the winner, and the clock held.`);

fs.mkdirSync(path.join(ROOT, 'results'), { recursive: true });
fs.writeFileSync(path.join(ROOT, 'results', 'proved.json'), JSON.stringify({
  proved_at: new Date().toISOString(), network: 'genlayer testnet asimov', contract: AT,
  true_claim: r0, false_claim: r1, early: r2, winner: { bet0: w0, bet1: w1 }, size,
  checks: checks.map(([label, ok]) => ({ label, ok })), transcript: out,
}, null, 2));
say('Written to results/proved.json');
process.exit(failed.length ? 1 : 0);
