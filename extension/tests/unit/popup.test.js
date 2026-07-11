const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const popupSource = fs.readFileSync(path.join(__dirname, '../../src/popup.js'), 'utf8');

test('popup previews forget scope before bounded execution', () => {
  const preview = popupSource.indexOf("daemonRequest('/forget', {domain: currentDomain, dry_run: true})");
  const confirmation = popupSource.indexOf('if (!confirm(`Forget ${preview.counts?.documents || 0} document(s)');
  const execution = popupSource.indexOf("daemonRequest('/forget', {domain: currentDomain, max_records: selectedRecords})");

  assert.notEqual(preview, -1);
  assert.notEqual(confirmation, -1);
  assert.notEqual(execution, -1);
  assert.ok(preview < confirmation);
  assert.ok(confirmation < execution);
});
