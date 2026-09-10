#!/usr/bin/env node
'use strict';

// Read-only evidence audit. Historical tool commands are data and never executed.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');

const pool = path.resolve(process.argv[2] ||
  'C:/Users/hongy/projects/_migloop-eval-20260909/attribution10/formal-v1/dice-entry/pool');
const generationBoundary = '2026-09-03T16:46:30.036Z';
const cutoff = '2026-09-03T22:09:07.188Z';

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(file) : [file];
  });
}

const files = walk(pool).filter(file => file.endsWith('.jsonl')).sort();
const blocks = [];
for (const file of files) {
  const source = path.relative(pool, file).replaceAll('\\', '/');
  for (const [index, line] of fs.readFileSync(file, 'utf8').split('\n').entries()) {
    if (!line.trim()) continue;
    let record;
    try {
      record = JSON.parse(line);
    } catch (error) {
      throw new Error(`${source}:${index + 1}: invalid JSONL: ${error.message}`);
    }
    for (const content of Array.isArray(record.message?.content) ? record.message.content : []) {
      blocks.push({ source, line: index + 1, time: record.timestamp, content });
    }
  }
}

function use(id) {
  const matches = blocks.filter(block => block.content.type === 'tool_use' && block.content.id === id);
  assert.equal(matches.length, 1, `expected one tool_use for ${id}`);
  return matches[0];
}

function result(id) {
  const matches = blocks.filter(block => block.content.type === 'tool_result' &&
    block.content.tool_use_id === id);
  assert.equal(matches.length, 1, `expected one tool_result for ${id}`);
  assert.notEqual(matches[0].content.is_error, true, `error result for ${id}`);
  return matches[0];
}

function locator(block) {
  return { source: block.source, line: block.line, time: block.time };
}

function paired(id) {
  return { call_id: id, use: locator(use(id)), result: locator(result(id)) };
}

function targetMatches(filePath, target) {
  const normalized = filePath.replaceAll('\\', '/');
  return normalized === target || normalized.endsWith(`/dice-hmos/${target}`);
}

function editsFor(target) {
  return blocks.filter(block => block.content.type === 'tool_use' &&
    block.content.name === 'Edit' && block.time <= cutoff &&
    targetMatches(block.content.input.file_path, target))
    .sort((a, b) => a.time.localeCompare(b.time));
}

function applyEdits(initial, edits) {
  let text = initial;
  for (const edit of edits) {
    const { old_string: oldText, new_string: newText } = edit.content.input;
    assert.equal(text.split(oldText).length - 1, 1,
      `${edit.content.id}: old_string must match exactly once`);
    const receipt = result(edit.content.id);
    assert.match(receipt.content.content, /has been updated successfully/,
      `${edit.content.id}: missing successful update receipt`);
    assert.equal(receipt.source, edit.source, 'receipt must belong to the same source');
    text = text.replace(oldText, () => newText);
  }
  return text;
}

function stripReadLineNumbers(raw) {
  return raw.split('\n').filter(line => /^\s*\d+\t/.test(line))
    .map(line => line.replace(/^\s*\d+\t/, '')).join('\n');
}

function compare(target, text, snapshot, initialId, finalId, edits) {
  const normalize = value => value.replace(/(?:\r?\n)+$/, '');
  const normalized = normalize(text);
  assert.equal(normalized, normalize(snapshot), `${target}: unexplained snapshot difference`);
  return {
    target,
    initial: paired(initialId),
    final_snapshot: paired(finalId),
    native_edits_total: edits.length,
    post_boundary_native_edits: edits.filter(edit => edit.time > generationBoundary).length,
    native_events: edits.map(edit => paired(edit.content.id)),
    equal_ignoring_final_newline: true,
    normalized_sha256: crypto.createHash('sha256').update(normalized).digest('hex'),
  };
}

const entryTarget = 'entry/src/main/ets/entryability/EntryAbility.ets';
const entryInitialId = 'call_459071197f484436b71237e5';
const entryFinalId = 'call_ac3454e853d9404188ea76de';
const entryInitial = use(entryInitialId).content.input.content;
const entryEdits = editsFor(entryTarget);
assert(entryEdits.every(edit => edit.time > use(entryInitialId).time));
const entrySnapshot = stripReadLineNumbers(result(entryFinalId).content.content);
const entry = compare(entryTarget, applyEdits(entryInitial, entryEdits), entrySnapshot,
  entryInitialId, entryFinalId, entryEdits);

const appTarget = 'AppScope/app.json5';
const appInitialId = 'call_4d7173d3a6a44651901a7f15';
const appFinalId = 'call_9cbbfc27df06477fbacab7fb';
const appInitialParts = result(appInitialId).content.content.split('=== app.json5 ===\n');
assert.equal(appInitialParts.length, 2, 'initial app.json5 delimiter must be unique');
const appFinalParts = result(appFinalId).content.content.split('=== app.json5:\n');
assert.equal(appFinalParts.length, 2, 'final app.json5 delimiter must be unique');
const appSnapshot = appFinalParts[1].split('=== dice png sizes:')[0];
const appEdits = editsFor(appTarget);
assert(appEdits.every(edit => edit.time > result(appInitialId).time));
const app = compare(appTarget, applyEdits(appInitialParts[1], appEdits), appSnapshot,
  appInitialId, appFinalId, appEdits);

process.stdout.write(JSON.stringify({
  pool,
  jsonl_files: files.length,
  root_jsonl_files: files.filter(file => path.dirname(file) === pool).length,
  generation_boundary: generationBoundary,
  cutoff,
  normalization: 'strip Read line-number prefixes; remove trailing newlines only',
  limitation: 'Text equality explains visible net changes, not transient or opaque script effects.',
  files: [entry, app],
}, null, 2) + '\n');
