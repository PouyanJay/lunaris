import { describe, expect, it } from "vitest";
import { captureWav } from "./captureWav";

describe("microphone recording contract", () => {
  it("encodes bounded mono PCM16 WAV from a device's 48kHz stream", async () => {
    const bytes = captureWav([new Float32Array(4800).fill(0.5)], 48000);
    const header = new DataView(bytes);
    expect(new TextDecoder().decode(bytes.slice(0, 4))).toBe("RIFF");
    expect(header.getUint16(22, true)).toBe(1);
    expect(header.getUint32(24, true)).toBe(16000);
    expect(header.getUint16(34, true)).toBe(16);
    expect(header.getUint32(40, true)).toBe(3200);
    expect(bytes.byteLength).toBe(3244);
    expect(header.getInt16(44, true)).toBeCloseTo(16384, 0);
  });
  it("refuses empty, oversized and nonfinite recordings before upload", () => {
    expect(() => captureWav([], 16000)).toThrow();
    expect(() => captureWav([new Float32Array(960001)], 16000)).toThrow();
    expect(() => captureWav([Float32Array.of(NaN)], 16000)).toThrow();
    expect(() => captureWav([Float32Array.of(1)], 0)).toThrow();
  });
  it("preserves the duration of noninteger-rate input and clamps clipped samples", () => {
    const bytes = captureWav([new Float32Array(4410).fill(-2)], 44100);
    const header = new DataView(bytes);
    expect(header.getUint32(40, true)).toBe(3200);
    expect(header.getInt16(44, true)).toBe(-32768);
  });
});
