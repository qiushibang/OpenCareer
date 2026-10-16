# 浏览器模拟面试录音设计

## 目标

让浏览器版 `InterviewView` 支持与桌面版一致的中文语音回答：

```text
浏览器麦克风
→ 内存 PCM16 WAV
→ 现有豆包 ASR HTTP 接口
→ 可编辑 transcript
→ 用户确认后提交回答
```

首期只覆盖模拟面试，不扩展普通对话 Composer。

## 成功标准

1. 浏览器安全上下文中显示“开始录音”。
2. 用户点击后才请求麦克风权限。
3. 录音输出严格为 16 kHz、mono、PCM16 WAV。
4. 停止录音后复用现有 `transcribeInterviewAudio()`。
5. transcript 写入可编辑草稿，不自动提交。
6. 录音显示实时波形和计时，支持停止和取消。
7. 单次录音 5 分钟自动停止并识别。
8. 取消、异常、卸载和切题后不保留活动音轨或音频数据。
9. 不在文件、Blob URL、IndexedDB、localStorage 或日志中保存音频。
10. Tauri 桌面录音路径保持可用。

## 方案选择

采用 `AudioWorklet` 直接采集 PCM。

不采用 `MediaRecorder`，因为浏览器通常输出 WebM/Opus，现有后端只接受 WAV；接入
MediaRecorder 会引入 FFmpeg 或新解码依赖。也不采用已废弃且运行在主线程的
`ScriptProcessorNode`。

## 模块边界

### `browserAudioCapture.ts`

负责浏览器录音生命周期：

- 能力检测。
- `getUserMedia()` 权限请求。
- 创建 `AudioContext`、加载 `AudioWorkletProcessor`。
- 接收 Float32 PCM 分片和实时音量。
- 停止、取消和销毁资源。
- 重采样、PCM16 转换、WAV 封装和 Base64 编码。

对外接口：

```ts
export interface InterviewAudioCapture {
  start(onLevel: (level: number) => void): Promise<void>;
  stop(): Promise<CapturedAudio>;
  cancel(): Promise<void>;
}

export function browserInterviewCaptureSupported(): boolean;
export function createBrowserInterviewCapture(): InterviewAudioCapture;
```

同一实例一次只允许一场录音。重复 start、未开始时 stop、工作线程异常和空音频均返回
可识别错误。

### AudioWorklet

工作线程只做两件事：

1. 将输入第一个声道的 Float32 分片复制并发送到主线程。
2. 计算当前分片 RMS 音量并发送 `0..1` level。

它不编码、不访问网络、不持久化数据。

### `interviewAudioCapture.ts`

负责选择运行时适配器：

- Tauri：包装现有 `startInterviewCapture`、`stopInterviewCapture`、
  `cancelInterviewCapture` 和 `getDictationLevel`。
- Browser：包装 `browserAudioCapture.ts`。

`InterviewView` 只依赖统一接口，不再直接判断 `isTauri()`。

### `VoiceRecordingMeter`

改为接收外部 `level`：

```ts
<VoiceRecordingMeter active={recording} level={recordingLevel} />
```

组件只负责波形历史和计时，不再直接调用 Tauri bridge。

## 音频格式

浏览器输入采样率取决于设备，常见为 44.1 kHz 或 48 kHz。停止时使用确定性线性重采样
转换为 16 kHz mono，然后映射到 signed PCM16。

WAV 必须满足：

- RIFF/WAVE。
- `fmt ` PCM format 1。
- 1 channel。
- 16,000 Hz。
- 16 bits。
- byte rate 32,000。
- block align 2。
- `data` 长度与 PCM 字节数一致。

现有后端限制为 300 秒和 20 MB。16 kHz mono PCM16 每分钟约 1.92 MB，5 分钟约
9.6 MB，符合限制。

## 浏览器能力门禁

仅同时满足以下条件时启用：

- `window.isSecureContext === true`。
- `navigator.mediaDevices.getUserMedia` 可用。
- `AudioContext` 或 `webkitAudioContext` 可用。
- `audioWorklet.addModule` 可用。

`localhost` 被主流浏览器视为安全来源。云部署必须使用 HTTPS。

不支持时隐藏录音控制并保留现有文字回答；显示简短说明：

```text
当前浏览器环境不支持安全录音，请使用 HTTPS 或直接输入文字回答。
```

## 用户交互

### 开始

用户点击“开始录音”后请求权限。成功后显示：

- 实时波形。
- `0:00` 起的计时。
- “浏览器正在使用麦克风”。
- “取消录音”和“停止录音”。

### 停止

立即停止音轨和 AudioContext，生成 WAV，按钮显示“正在识别…”，调用现有 ASR。
ASR 成功后 transcript 写入回答框；用户可修改后提交。

### 取消

立即停止所有音频资源并清空 PCM 分片，不调用 ASR。

### 自动停止

达到 300 秒时执行与手动停止相同的流程。计时器只负责触发停止，后端 300 秒校验仍是
最终安全边界。

## 错误映射

- `NotAllowedError` / `SecurityError`：
  `未获得麦克风权限，请在浏览器地址栏允许后重试。`
- `NotFoundError`：
  `未检测到可用麦克风，请连接设备后重试。`
- 不支持或非安全上下文：
  `当前浏览器环境不支持安全录音，请使用 HTTPS 或直接输入文字回答。`
- 空音频、工作线程、编码或 ASR 错误：
  `语音识别失败，请直接输入文字回答。`

所有失败均保留已有草稿。

## 资源与隐私不变量

每个终止路径都必须：

1. `MediaStreamTrack.stop()`。
2. 断开 source 和 worklet node。
3. 关闭 `AudioContext`。
4. 清空 onmessage 和 level callback。
5. 清空 Float32 分片。
6. 清除 5 分钟定时器。

不得：

- 创建音频文件。
- 创建音频 Blob URL。
- 写入浏览器持久化存储。
- 在日志中输出 WAV、PCM 或 Base64。
- 自动提交 ASR transcript。

## TDD

### 纯函数

测试 48 kHz 和 44.1 kHz 输入重采样、PCM16 clamp、WAV header 和 data 长度。

### 浏览器采集

使用 fake `MediaStream`、`AudioContext`、`AudioWorkletNode`：

- start 仅在用户动作调用时请求权限。
- PCM 和 level 正确进入状态。
- stop 生成 WAV 并释放资源。
- cancel 不返回音频且释放资源。
- 拒绝权限映射中文错误。
- 重复 start 和空 stop 被拒绝。

### `InterviewView`

- 非 Tauri 浏览器显示录音按钮。
- 停止后调用现有 ASR 并写入可编辑草稿。
- 取消不调用 ASR。
- 5 分钟自动停止。
- 不支持环境保留文字模式。
- Tauri 现有录音回归保持通过。

## 真实验收

在 `http://localhost:1420`：

1. 进入任一模拟面试问题。
2. 点击开始录音并允许浏览器麦克风。
3. 朗读中文回答，观察波形和计时。
4. 停止后确认网络只发送 WAV Base64 到现有 ASR endpoint。
5. 确认 transcript 可编辑且未自动提交。
6. 取消另一轮录音，确认未调用 ASR。
7. 检查 console 0 error。

云服务器验收需在 HTTPS 域名重复以上步骤。

## 不做事项

- 不实现普通 Composer 浏览器语音。
- 不改变豆包 ASR/TTS Provider。
- 不引入 FFmpeg、WebM/Opus 解码或新 npm 依赖。
- 不改造 OpenWorker 公网鉴权、租户隔离或 Agent 沙箱。
- 不永久保存用户音频。
