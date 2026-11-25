import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../morning-review/index.html', import.meta.url), 'utf8');
const source = html.split('<script>')[1].split('// Browser interface')[0];
const { makeReview, parseSettings, acceptResults, pendingBatches, makeBriefInput, parseResponse } =
    vm.runInNewContext(source + '\n({ makeReview, parseSettings, acceptResults, pendingBatches, makeBriefInput, parseResponse })', { URL });

const record = (id, fields = {}) => ({
    id, conversationId: 'thread-' + id, subject: 'Topic ' + id,
    from: { emailAddress: { address: 'sender@example.com' } },
    receivedDateTime: '2026-11-25T10:00:00Z',
    ...fields
});
const feed = (name, records) => ({ feed: name, records, verified_count: records.length });
const archive = (received, sent = [], other = []) => ({
    status: 'verified', checkpoint_utc: '2026-11-25T12:00:00Z', work_account: 'me@example.com',
    feeds: [feed('received', received), feed('sent', sent), ...other]
});
const prepare = (data, overrides = {}) => makeReview(data, {
    history: [], settings: parseSettings(), batchSize: 10, applyRules: false, ...overrides
});
const disposition = id => ({
    id, action: 'no_action', status: '', priority: 'low', summary: 'Informational',
    owner: '', due: '', next_step: ''
});
const response = (batch, ids = batch.expected_ids) => ({
    run_id: batch.run_id, batch_id: batch.batch_id, dispositions: ids.map(disposition)
});

test('94 eligible records leave the omitted middle ID outstanding until retried', () => {
    const plan = prepare(archive(Array.from({ length: 94 }, (_, index) => record('id-' + (index + 1)))));
    assert.equal(plan.coverage.queued, 94);
    const missing = plan.batches[4].expected_ids[2];
    const answers = plan.batches.map(batch => response(batch, batch.expected_ids.filter(id => id !== missing)));
    let accepted = acceptResults(plan, new Map(), answers);
    assert.equal(accepted.size, 93);
    assert.throws(() => makeBriefInput(plan, accepted), /outstanding/);
    const retry = pendingBatches(plan, accepted);
    assert.equal(retry.length, 1);
    assert.equal(retry[0].expected_ids.join(), missing);
    accepted = acceptResults(plan, accepted, response(retry[0]));
    const brief = makeBriefInput(plan, accepted);
    assert.equal(brief.coverage.reviewed, 94);
    assert.equal(brief.coverage.outstanding, 0);
    assert.equal(brief.actions.length, 0);
});

test('a rejected response does not mutate already checked records', () => {
    const plan = prepare(archive([record('a'), record('b')]));
    const [batch] = plan.batches;
    const accepted = acceptResults(plan, new Map(), response(batch, ['a']));
    assert.throws(() => acceptResults(plan, accepted, response(batch, ['b', 'b'])), /Duplicate/);
    assert.throws(() => acceptResults(plan, accepted, response(batch, ['foreign'])), /does not belong/);
    assert.throws(() => acceptResults(plan, accepted, { ...response(batch), run_id: 'another-run' }), /current run_id/);
    assert.equal(accepted.size, 1);
    assert.equal(acceptResults(plan, accepted, response(batch, ['a', 'b'])).size, 2);
});

test('routing is dry-run by default, preserves exceptions, and deduplicates feed overlap', () => {
    const settings = parseSettings({ rules: [{
        id: 'digest', sender: 'SENDER@example.com', subject_contains: 'Digest',
        except_subject_contains: ['action required'], destination: 'Digest'
    }] });
    const first = record('a', { subject: 'Daily digest' });
    const second = record('b', { subject: 'Daily digest: Action required' });
    const data = archive([first, second], [first, record('draft', { isDraft: true })]);
    const dry = prepare(data, { settings });
    assert.equal(dry.coverage.queued, 2);
    assert.equal(dry.coverage.routed, 0);
    assert.equal(dry.audit.find(row => row.id === 'a').rule_id, 'digest');
    const apply = prepare(data, { settings, applyRules: true });
    assert.equal(apply.coverage.routed, 1);
    assert.equal(apply.batches[0].expected_ids.join(), 'b');
});

test('same-thread sent history, Planner, and confirmed decisions are evidence only', () => {
    const current = record('a', { subject: 'REF-123 reconciliation' });
    const planner = feed('planner-assigned', [
        { id: 'task', title: 'REF-123 reconciliation', percentComplete: 50 },
        { id: 'done', title: 'REF-123 reconciliation', percentComplete: 100 }
    ]);
    const history = [
        { id: 'old', thread_id: current.conversationId, direction: 'sent', date: '2026-11-24T10:00:00Z' },
        { id: 'unrelated', thread_id: 'different', direction: 'sent', date: '2026-11-24T10:00:00Z' },
        { id: 'future', thread_id: current.conversationId, direction: 'sent', date: '2026-11-26T10:00:00Z' }
    ];
    const settings = parseSettings({ decisions: [{
        id: 'decision', references: ['REF-123'], action_taken: 'Ask the owner to confirm',
        source_link: 'https://example.com/decision'
    }] });
    const [batch] = prepare(archive([current], [], [planner]), { history, settings }).batches;
    assert.equal(batch.expected_ids.join(), 'a');
    assert.equal(batch.context_by_thread[0].messages.map(row => row.id).join(), 'old');
    assert.equal(batch.planner_context.map(row => row.id).join(), 'task');
    assert.equal(batch.confirmed_precedents[0].id, 'decision');
});

test('invalid archive counts and duplicate source IDs are rejected', () => {
    const invalid = archive([record('a')]);
    invalid.feeds[0].verified_count = 2;
    assert.throws(() => prepare(invalid), /coverage/);
    assert.throws(() => prepare(archive([record('a'), record('a')])), /coverage/);
    assert.equal(parseResponse(String.fromCharCode(96).repeat(3) + 'json\n{"ok":true}\n' +
        String.fromCharCode(96).repeat(3)).ok, true);
});
