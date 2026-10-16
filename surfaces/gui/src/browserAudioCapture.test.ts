import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  browserInterviewCaptureSupported,
  createBrowserInterviewCapture,
  encodePcm16Wav,
  resampleLinear,
} from "./browserAudioCapture";

function readAscii(bytes: Uint8Array, offset: number, length: number) {
  return String.fromCharCode(...bytes.slice(offset, offset + length));
}

describe("browser audio conversion", () => {
  it.each([48_000, 44_100])(
    "resamples %i Hz input to 16 kHz",
    (inputRate) => {
      const input = Float32Array.from(
        { length: inputRate },
        (_, index) => index / inputRate,
      );

      const output = resampleLinear(input, inputRate);

      expect(output).toHaveLength(16_000);
      expect(output[0]).toBeCloseTo(0);
      expect(output[8_000]).toBeCloseTo(0.5, 3);
      expect(output[15_999]).toBeCloseTo(1, 3);
    },
  );

  it("clamps Float32 samples into signed PCM16", () => {
    const wav = encodePcm16Wav(
      new Float32Array([-2, -1, -0.5, 0, 0.5, 1, 2]),
    );
    const view = new DataView(
      wav.buffer,
      wav.byteOffset,
      wav.byteLength,
    );

    expect(
      Array.from({ length: 7 }, (_, index) =>
        view.getInt16(44 + index * 2, true),
      ),
    ).toEqual([-32768, -32768, -16384, 0, 16384, 32767, 32767]);
  });

  it("writes a 16 kHz mono PCM16 WAV header and exact data length", () => {
    const wav = encodePcm16Wav(new Float32Array([0, 0.25, -0.25]));
    const view = new DataView(
      wav.buffer,
      wav.byteOffset,
      wav.byteLength,
    );

    expect(readAscii(wav, 0, 4)).toBe("RIFF");
    expect(view.getUint32(4, true)).toBe(wav.byteLength - 8);
    expect(readAscii(wav, 8, 4)).toBe("WAVE");
    expect(readAscii(wav, 12, 4)).toBe("fmt ");
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint32(28, true)).toBe(32_000);
    expect(view.getUint16(32, true)).toBe(2);
    expect(view.getUint16(34, true)).toBe(16);
    expect(readAscii(wav, 36, 4)).toBe("data");
    expect(view.getUint32(40, true)).toBe(6);
    expect(wav.byteLength).toBe(50);
  });
});

class FakeAudioWorkletNode {
  static latest: FakeAudioWorkletNode | null = null;
  readonly connect = vi.fn();
  readonly disconnect = vi.fn();
  readonly port = {
    onmessage: null as ((event: MessageEvent) => void) | null,
  };

  constructor() {
    FakeAudioWorkletNode.latest = this;
  }

  emit(data: unknown) {
    this.port.onmessage?.({ data } as MessageEvent);
  }
}

class FakeAudioContext {
  static latest: FakeAudioContext | null = null;
  readonly sampleRate = 48_000;
  readonly destination = {};
  readonly audioWorklet = { addModule: vi.fn(async () => undefined) };
  readonly source = {
    connect: vi.fn(),
    disconnect: vi.fn(),
  };
  readonly createMediaStreamSource = vi.fn(() => this.source);
  readonly close = vi.fn(async () => undefined);

  constructor() {
    FakeAudioContext.latest = this;
  }
}

describe("browser audio capture", () => {
  const trackStop = vi.fn();
  const getUserMedia = vi.fn();

  beforeEach(() => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: true,
    });
    Object.defineProperty(FakeAudioContext.prototype, "audioWorklet", {
      configurable: true,
      value: {},
    });
    getUserMedia.mockResolvedValue({
      getTracks: () => [{ stop: trackStop }],
    });
    vi.stubGlobal("AudioContext", FakeAudioContext);
    vi.stubGlobal("AudioWorkletNode", FakeAudioWorkletNode);
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: { getUserMedia },
    });
    vi.stubGlobal(
      "URL",
      class extends URL {
        static createObjectURL = vi.fn(() => "blob:worklet");
        static revokeObjectURL = vi.fn();
      },
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    FakeAudioContext.latest = null;
    FakeAudioWorkletNode.latest = null;
  });

  it("detects a secure browser with getUserMedia and AudioWorklet", () => {
    expect(browserInterviewCaptureSupported()).toBe(true);
  });

  it("requests the microphone on start and forwards live levels", async () => {
    const capture = createBrowserInterviewCapture();
    const onLevel = vi.fn();

    expect(getUserMedia).not.toHaveBeenCalled();
    await capture.start(onLevel);
    FakeAudioWorkletNode.latest?.emit({ type: "level", value: 0.6 });

    expect(getUserMedia).toHaveBeenCalledWith({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    expect(onLevel).toHaveBeenCalledWith(0.6);
  });

  it("returns a 16 kHz WAV and releases resources on stop", async () => {
    const capture = createBrowserInterviewCapture();
    await capture.start(vi.fn());
    FakeAudioWorkletNode.latest?.emit({
      type: "samples",
      samples: new Float32Array(4_800).fill(0.25),
    });

    const audio = await capture.stop();
    const bytes = Uint8Array.from(atob(audio.data_base64), (value) =>
      value.charCodeAt(0),
    );

    expect(audio.mime).toBe("audio/wav");
    expect(readAscii(bytes, 0, 4)).toBe("RIFF");
    expect(new DataView(bytes.buffer).getUint32(24, true)).toBe(16_000);
    expect(trackStop).toHaveBeenCalled();
    expect(FakeAudioContext.latest?.source.disconnect).toHaveBeenCalled();
    expect(FakeAudioWorkletNode.latest?.disconnect).toHaveBeenCalled();
    expect(FakeAudioContext.latest?.close).toHaveBeenCalled();
    expect(FakeAudioWorkletNode.latest?.port.onmessage).toBeNull();
  });

  it("cancels without audio and releases resources", async () => {
    const capture = createBrowserInterviewCapture();
    await capture.start(vi.fn());

    await expect(capture.cancel()).resolves.toBeUndefined();

    expect(trackStop).toHaveBeenCalled();
    expect(FakeAudioContext.latest?.close).toHaveBeenCalled();
  });

  it("stops a stream that arrives after capture was cancelled", async () => {
    let resolveStream: (stream: MediaStream) => void = () => {
      throw new Error("Expected a pending getUserMedia request.");
    };
    getUserMedia.mockReturnValueOnce(
      new Promise<MediaStream>((resolve) => {
        resolveStream = resolve;
      }),
    );
    const capture = createBrowserInterviewCapture();
    const starting = capture.start(vi.fn());

    await capture.cancel();
    resolveStream({
      getTracks: () => [{ stop: trackStop }],
    } as unknown as MediaStream);

    await expect(starting).rejects.toThrow("cancelled");
    expect(trackStop).toHaveBeenCalled();
  });

  it("rejects repeated start, stop before start, and empty audio", async () => {
    const capture = createBrowserInterviewCapture();

    await expect(capture.stop()).rejects.toThrow("not recording");
    await capture.start(vi.fn());
    await expect(capture.start(vi.fn())).rejects.toThrow(
      "already recording",
    );
    await expect(capture.stop()).rejects.toThrow("empty audio");
  });

  it.each(["NotAllowedError", "SecurityError", "NotFoundError"])(
    "preserves %s microphone errors for UI mapping",
    async (name) => {
      getUserMedia.mockRejectedValueOnce(
        new DOMException("microphone failed", name),
      );

      await expect(
        createBrowserInterviewCapture().start(vi.fn()),
      ).rejects.toHaveProperty("name", name);
    },
  );

  it("signals the caller at the five-minute limit", async () => {
    vi.useFakeTimers();
    const capture = createBrowserInterviewCapture();
    const onLimitReached = vi.fn();
    await capture.start(vi.fn(), onLimitReached);

    await vi.advanceTimersByTimeAsync(300_000);

    expect(onLimitReached).toHaveBeenCalledTimes(1);
  });
});
