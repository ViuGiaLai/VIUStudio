import { parseSrt, serializeToSrt, reviewTranslationImport } from './dist/index.js';
import assert from 'node:assert/strict';
// Failed checks must produce a non-zero exit status in CI.
console.assert = (condition, message) => assert.ok(condition, message);

console.log('--- TEST 1: SRT Parser & Serializer ---');
const sampleSrt = `1
00:00:01,000 --> 00:00:04,500
Hello and welcome to VIUStudio.

2
00:00:05,000 --> 00:00:08,200
This is a local media processing platform.
`;

const parseResult = parseSrt(sampleSrt, 'prj_test');
console.assert(parseResult.cues.length === 2, `Expected 2 cues, got ${parseResult.cues.length}`);
console.assert(parseResult.cues[0].start_ms === 1000, `Expected 1000ms start, got ${parseResult.cues[0].start_ms}`);
console.assert(parseResult.cues[0].end_ms === 4500, `Expected 4500ms end, got ${parseResult.cues[0].end_ms}`);
console.assert(parseResult.errors.length === 0, `Expected 0 errors, got ${parseResult.errors.length}`);

const serialized = serializeToSrt(parseResult.cues);
console.assert(serialized.includes('00:00:01,000 --> 00:00:04,500'), 'Serialized SRT timestamp matches');
console.log('✓ SRT Parser & Serializer passed.');

console.log('\n--- TEST 2: SRT Overlap & Timing Validation ---');
const overlapSrt = `1
00:00:01,000 --> 00:00:05,000
First cue.

2
00:00:04,000 --> 00:00:07,000
Second cue overlapping by 1000ms.
`;
const overlapResult = parseSrt(overlapSrt);
console.assert(overlapResult.errors.length === 1, 'Detected 1 overlap error');
console.log('✓ Timing overlap validation passed.');

console.log('\n--- TEST 3: Translation Import Review Logic (Section 10.3) ---');
const existingCues = parseResult.cues;
const importEntries = [
  {
    id: existingCues[0].id,
    translated_text: 'Xin chào và chào mừng đến với VIUStudio.',
  },
  {
    id: existingCues[1].id,
    translated_text: 'Đây là nền tảng xử lý media cục bộ.',
  },
];

const review = reviewTranslationImport(existingCues, importEntries);
console.assert(review.matchedCount === 2, `Expected matched 2, got ${review.matchedCount}`);
console.assert(review.changedCount === 2, `Expected changed 2, got ${review.changedCount}`);
console.assert(review.missingCount === 0, `Expected missing 0, got ${review.missingCount}`);
console.assert(review.canApply === true, 'Can apply is true');
console.log('✓ Translation Import Review logic passed.');

console.log('\nALL VERIFICATION TESTS PASSED SUCCESSFULLY! 🎉');
