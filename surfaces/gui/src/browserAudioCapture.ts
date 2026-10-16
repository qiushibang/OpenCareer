import type { CapturedAudio } from "./tauri";

export interface InterviewAudioCapture {
  start(
    onLevel: (level: number) => void,
    onLimitReached?: () => void,
  ): Promise<void>;
  stop(): Promise<CapturedAudio>;
  cancel(): Promise<void>;
}

export function resampleLinear(
  input: Float32Array,
  inputRate: number,
  outputRate = 16_000,
): Float32Array {
  if (inputRate <= 0 || outputRate <= 0) {
    throw new Error("Audio sample rates must be positive.");
  }
  if (input.length === 0) return new Float32Array();
  if (inputRate === outputRate) return input.slice();

  const outputLength = Math.round(
    (input.length * outputRate) / inputRate,
  );
  const output = new Float32Array(outputLength);
  const ratio = inputRate / outputRate;
  for (let index = 0; index < outputLength; index += 1) {
    const position = index * ratio;
    const left = Math.min(Math.floor(position), input.length - 1);
    const right = Math.min(left + 1, input.length - 1);
    const fraction = position - left;
    output[index] =
      input[left] + (input[right] - input[left]) * fraction;
  }
  return output;
}

function writeAscii(
  bytes: Uint8Array,
  offset: number,
  value: string,
) {
  for (let index = 0; index < value.length; index += 1) {
    bytes[offset + index] = value.charCodeAt(index);
  }
}

export function encodePcm16Wav(
  samples: Float32Array,
  sampleRate = 16_000,
): Uint8Array {
  const dataLength = samples.length * 2;
  const bytes = new Uint8Array(44 + dataLength);
  const view = new DataView(bytes.buffer);

  writeAscii(bytes, 0, "RIFF");
  view.setUint32(4, bytes.byteLength - 8, true);
  writeAscii(bytes, 8, "WAVE");
  writeAscii(bytes, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(bytes, 36, "data");
  view.setUint32(40, dataLength, true);

  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    const pcm = sample < 0 ? sample * 32_768 : sample * 32_767;
    view.setInt16(44 + index * 2, Math.round(pcm), true);
  }
  return bytes;
}

const WORKLET_SOURCE = `
class OpenWorkerInterviewCapture extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel || channel.length === 0) return true;
    const samples = channel.slice();
    let sum = 0;
    for (let index = 0; index < samples.length; index += 1) {
      sum += samples[index] * samples[index];
    }
    this.port.postMessage(
      { type: "samples", samples },
      [samples.buffer],
    );
    this.port.postMessage({
      type: "level",
      value: Math.min(1, Math.sqrt(sum / samples.length)),
    });
    return true;
  }
}
registerProcessor("openworker-interview-capture", OpenWorkerInterviewCapture);
`;

type AudioContextConstructor = new () => AudioContext;

function audioContextConstructor(): AudioContextConstructor | null {
  const runtime = globalThis as typeof globalThis & {
    webkitAudioContext?: AudioContextConstructor;
  };
  return (
    (runtime.AudioContext as AudioContextConstructor | undefined) ||
    runtime.webkitAudioContext ||
    null
  );
}

export function browserInterviewCaptureSupported(): boolean {
  const AudioContextClass = audioContextConstructor();
  return Boolean(
    typeof window !== "undefined" &&
      window.isSecureContext &&
      typeof navigator.mediaDevices?.getUserMedia === "function" &&
      AudioContextClass &&
      "audioWorklet" in AudioContextClass.prototype &&
      typeof globalThis.AudioWorkletNode === "function",
  );
}

function joinChunks(chunks: Float32Array[]): Float32Array {
  const length = chunks.reduce(
    (total, chunk) => total + chunk.length,
    0,
  );
  const joined = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    joined.set(chunk, offset);
    offset += chunk.length;
  }
  return joined;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 32_768;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(
      ...bytes.subarray(offset, offset + chunkSize),
    );
  }
  return btoa(binary);
}

export function createBrowserInterviewCapture(): InterviewAudioCapture {
  let stream: MediaStream | null = null;
  let context: AudioContext | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let worklet: AudioWorkletNode | null = null;
  let chunks: Float32Array[] = [];
  let onLevel: ((level: number) => void) | null = null;
  let limitTimer: number | null = null;
  let captureEpoch = 0;
  let starting = false;

  const recording = () =>
    Boolean(stream && context && source && worklet);

  const release = async () => {
    if (limitTimer !== null) {
      window.clearTimeout(limitTimer);
      limitTimer = null;
    }
    if (worklet) {
      worklet.port.onmessage = null;
      worklet.disconnect();
    }
    source?.disconnect();
    stream?.getTracks().forEach((track) => track.stop());
    if (context) {
      await context.close().catch(() => undefined);
    }
    stream = null;
    context = null;
    source = null;
    worklet = null;
    onLevel = null;
    chunks = [];
  };

  return {
    async start(levelCallback, onLimitReached) {
      if (recording() || starting) {
        throw new Error("Audio capture is already recording.");
      }
      if (!browserInterviewCaptureSupported()) {
        throw new Error("Browser audio capture is not supported.");
      }

      const AudioContextClass = audioContextConstructor();
      if (!AudioContextClass) {
        throw new Error("Browser audio capture is not supported.");
      }
      const epoch = captureEpoch + 1;
      captureEpoch = epoch;
      starting = true;
      const ensureCurrent = () => {
        if (captureEpoch !== epoch) {
          throw new Error("Audio capture was cancelled.");
        }
      };
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
        ensureCurrent();
        context = new AudioContextClass();
        if (!context.audioWorklet?.addModule) {
          throw new Error("Browser audio capture is not supported.");
        }
        const moduleUrl = URL.createObjectURL(
          new Blob([WORKLET_SOURCE], {
            type: "text/javascript",
          }),
        );
        try {
          await context.audioWorklet.addModule(moduleUrl);
        } finally {
          URL.revokeObjectURL(moduleUrl);
        }
        ensureCurrent();
        source = context.createMediaStreamSource(stream);
        worklet = new AudioWorkletNode(
          context,
          "openworker-interview-capture",
        );
        chunks = [];
        onLevel = levelCallback;
        worklet.port.onmessage = (event: MessageEvent) => {
          const message = event.data as {
            type?: string;
            samples?: Float32Array;
            value?: number;
          };
          if (
            message.type === "samples" &&
            message.samples instanceof Float32Array
          ) {
            chunks.push(message.samples);
          } else if (
            message.type === "level" &&
            typeof message.value === "number"
          ) {
            onLevel?.(Math.max(0, Math.min(1, message.value)));
          }
        };
        source.connect(worklet);
        worklet.connect(context.destination);
        limitTimer = window.setTimeout(() => {
          limitTimer = null;
          onLimitReached?.();
        }, 300_000);
        starting = false;
      } catch (error) {
        await release();
        starting = false;
        throw error;
      }
    },

    async stop() {
      if (!recording() || !context) {
        throw new Error("Audio capture is not recording.");
      }
      const sampleRate = context.sampleRate;
      const samples = joinChunks(chunks);
      await release();
      if (samples.length === 0) {
        throw new Error("Audio capture contains empty audio.");
      }
      const resampled = resampleLinear(samples, sampleRate);
      return {
        mime: "audio/wav",
        data_base64: bytesToBase64(encodePcm16Wav(resampled)),
      };
    },

    async cancel() {
      captureEpoch += 1;
      await release();
    },
  };
}
