import { expect, test } from "vitest";
import { concat, encodeWav, resample } from "../lib/audio";

test("resampling averages windows down to 16 kHz", () => {
  const input = new Float32Array(48000).map((_, i) => (i % 3) / 2);
  const output = resample(input, 48000);
  expect(output.length).toBe(16000);
  expect(output[0]).toBeCloseTo(0.5);
  expect(() => resample(input, 8000)).toThrow();
});

test("WAV encoding writes a 16 kHz mono 16-bit PCM header and clamps samples", () => {
  const view = new DataView(encodeWav(new Float32Array([0, 1, -1, 2])));
  const text = (offset: number) => String.fromCharCode(...new Uint8Array(view.buffer, offset, 4));
  expect([text(0), text(8), text(12), text(36)]).toEqual(["RIFF", "WAVE", "fmt ", "data"]);
  expect(view.getUint16(20, true)).toBe(1);
  expect(view.getUint16(22, true)).toBe(1);
  expect(view.getUint32(24, true)).toBe(16000);
  expect(view.getUint16(34, true)).toBe(16);
  expect(view.getUint32(40, true)).toBe(8);
  expect([view.getInt16(46, true), view.getInt16(48, true), view.getInt16(50, true)]).toEqual([32767, -32768, 32767]);
});

test("chunks are joined in order", () => {
  expect([...concat([new Float32Array([1, 2]), new Float32Array([3])])]).toEqual([1, 2, 3]);
});
