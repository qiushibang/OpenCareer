# 扫描 PDF 简历本地 OCR 设计

## 1. 目标

让用户通过现有“导入简历到求职档案”入口导入文字层为空或不完整的扫描 PDF：

- PDF 和识别页面不离开本机。
- 文字型 PDF 继续使用当前快速提取路径。
- 混合型 PDF 只对文本不足的页面执行 OCR。
- OCR 文本进入现有 Agent 结构化预览和用户逐章节确认流程，不能直接成为已确认事实。
- 识别方法、引擎版本、OCR 页和质量警告可追溯。

首版只支持扫描 PDF，不增加 PNG/JPEG、多图顺序、拍照透视校正、旧版 DOC 或云端
OCR。

## 2. 第一性原理

1. OCR 的产品价值是修复当前 `NO_EXTRACTABLE_TEXT` 失败路径，不是建立第二套简历
   数据模型。
2. PDF 的原生文字层比 OCR 更快、更准确、更容易复现，因此必须优先使用。
3. 一份 PDF 可以同时包含文字页和扫描页，回退粒度必须是页，不能整份重跑。
4. OCR confidence 只描述模型输出，不证明事实正确；正式事实仍必须经过现有用户确认。
5. 简历包含私人信息。首版不得上传第三方、调用 Provider 或在工作区留下页面图片。
6. OCR runtime、模型和页面栅格化扩大了资源与供应链风险，必须先通过独立依赖门禁。

## 3. 已确认产品决策

- 执行边界：本地跨平台 OCR。
- 引擎方向：RapidOCR + ONNX Runtime。
- 触发方式：`pypdf` 逐页提取不足时自动回退。
- 首版输入：仅扫描 PDF。
- 低质量处理：不可读时拒绝；达到最低文本量时进入预览并明确要求重点核对。
- 不提供云端 fallback。

RapidOCR 官方资料说明其默认支持中文和英文、使用 ONNX Runtime 进行跨平台离线部署，
工程代码采用 Apache 2.0；模型版权和再分发条件必须在 Gate 0 单独核对：

- <https://github.com/RapidAI/RapidOCR>
- <https://rapidai.github.io/RapidOCRDocs/>

完整 PaddleOCR 和 Tesseract 5 均为 Apache 2.0，但不作为首版 production engine。
PaddleOCR 的完整 runtime/文档结构能力超出本阶段；Tesseract 要求分别安装引擎与
`chi_sim`/`eng` 语言数据，无法保证源码安装和桌面包的一致可用性：

- <https://pypi.org/project/paddleocr/>
- <https://tesseract-ocr.github.io/tessdoc/Installation.html>

## 4. 数据流

```text
authenticated PDF upload
  → 文件名、MIME、10 MB、加密和 20 页校验
  → pypdf 逐页提取并归一化
  → 每页：
      native text >= 80 chars
        → 选择 native
      native text < 80 chars
        → pypdfium2 内存栅格化
        → RapidOCR/ONNX
        → OCR 文本比 native 更完整时选择 OCR
        → 否则保留 native 并记录警告
  → 按 PDF 页序合并最终文本
  → 质量分级与 provenance
  → 私有 original + staged resume import
  → get_resume_import_text
  → Agent 结构化 proposal
  → 用户逐章节确认
  → Career Vault facts
```

不得把 OCR 直接接入 `confirm_resume_sections`、岗位匹配、定制简历或 Export Service。
这些模块只能读取已经确认的 Career Vault facts。

## 5. 模块边界

### 5.1 `domain/resume.py`

保留文件格式、大小、页数、全文长度和 proposal 校验。PDF 提取改为逐页结果，并通过
注入的 OCR service 处理稀疏页面。

`ExtractedResume` 增加确定性 extraction metadata，但不包含页面位图或 box：

```text
filename
source_kind
text
raw_bytes
extraction_method
extraction_metadata
```

### 5.2 `domain/ocr.py`

只包含无 I/O 结构与纯函数：

- `OcrLine(text, confidence, polygon)`
- `OcrPage(page_number, text, accepted_lines, mean_confidence)`
- polygon 几何排序和同一行稳定排序。
- confidence 字符加权聚合。
- native/OCR 选择。
- warning code 和质量等级计算。

纯函数不得 import RapidOCR、ONNX Runtime、SQLite 或 GUI。

### 5.3 `services/resume_ocr.py`

负责：

- `OcrEngine` Protocol。
- lazy engine factory。
- `pypdfium2` 单页内存栅格化。
- DPI、尺寸、像素、OCR 页数和单并发限制。
- 逐页调用 engine。
- 将引擎异常转换为稳定 Domain error。

测试通过 constructor 注入 fake engine 和 fake renderer。HTTP/MCP 不接受 engine、
模型路径、DPI、阈值、语言或命令参数。

### 5.4 `ocr/rapidocr_engine.py`

唯一 production adapter：

- lazy import 固定版本 RapidOCR 和 ONNX Runtime。
- 固定中英 detection、orientation 和 recognition 模型。
- 返回统一 `OcrLine`。
- 提供 engine version、model IDs 和模型文件 SHA-256。
- 初始化和每次识别均不访问网络。

Adapter 不操作数据库、文件生命周期、Agent、HTTP 或 GUI。

### 5.5 `ResumeService`

- native text、DOCX 和 TXT 路径不初始化 OCR runtime。
- OCR 成功后继续使用原始 PDF bytes 计算 content hash。
- 只有提取和质量门禁通过后才写私有 original 与 staged row。
- stage、重复导入、preview、confirm、软删除和重新导入继续沿用现有事务边界。

## 6. 页级选择和质量规则

固定常量：

```text
MIN_NATIVE_PAGE_CHARS = 80
MIN_OCR_LINE_CONFIDENCE = 0.50
LOW_OCR_CONFIDENCE = 0.85
MIN_OCR_PAGE_CHARS = 40
MIN_RESUME_CHARS = 20          # 现有值
MAX_RESUME_BYTES = 10 MB       # 现有值
MAX_PDF_PAGES = 20             # 现有值
MAX_OCR_PAGES = 10
OCR_DPI = 200
MAX_RENDER_SIDE = 4096
MAX_RENDER_PIXELS = 16_000_000
```

规则：

1. 每页先读取 native text。
2. native text 达到 80 字符，不执行 OCR。
3. native text 少于 80 字符，页面进入 OCR 候选集。
4. OCR line confidence 小于 0.50 时作为噪声丢弃。
5. OCR 归一化文本字符数大于 native 时选择 OCR，否则保留 native。
6. 最终按原 PDF 页序合并；页内顺序由 polygon 的确定性几何规则决定。
7. 最终全文少于 20 字符返回 `NO_EXTRACTABLE_TEXT`。
8. 任一选择的 OCR 页平均 confidence 小于 0.85、文本少于 40 字符，或 OCR 未能
   改善稀疏 native 页时，`review_required=true`。
9. confidence 不在 GUI 显示为“准确率”。GUI 只显示“已使用本地 OCR”和“识别质量
   需重点核对”。

稀疏 native PDF 的降级：

- OCR runtime 不可用或某页推理失败，但所有保留的 native text 合计仍达到 20 字符：
  stage 可以成功，必须 `review_required=true` 并返回稳定 warning。
- native text 不足 20 字符且 OCR runtime 不可用：返回 `OCR_UNAVAILABLE`。
- native text 不足 20 字符且 OCR 执行失败：返回 `OCR_FAILED`。
- 需要 OCR 的页面超过 10 页：始终返回 `OCR_PAGE_LIMIT`，不得静默遗漏后续扫描页。

首版不根据低 confidence 自动改字、调用语言模型修复、删除整行或推导字段。

## 7. 资源和安全

- PDF 继续在 10 MB 和 20 页边界内处理。
- 每页固定 200 DPI；若任一维或像素数超限，按比例缩小到边界内，不提高 DPI。
- 同一时刻只允许一个 OCR inference workflow；页面逐张处理并释放数组。
- 页面位图只存在内存；不得写入 `.local-state`、Career 数据目录、workspace、
  artifacts、日志或测试快照。
- 不持久化 polygon、debug visualization 或原始 OCR engine 返回对象。
- OCR 日志只允许页数、耗时、method 和 warning code；不得记录 OCR 文本、姓名、
  联系方式、private path、upload token 或模型绝对路径。
- 依赖和模型必须随安装固定，运行时断网仍可用。不得从 ModelScope、Hugging Face、
  GitHub 或其他 URL 自动下载模型。
- 模型文件在 build/安装时校验 SHA-256；缺失或不匹配返回 `OCR_UNAVAILABLE`。
- 不执行 PDF 内脚本、附件、链接、外部命令或 embedded file。

## 8. schema v9 与 provenance

`resume_imports` 新增：

```sql
extraction_method TEXT NOT NULL DEFAULT 'native'
  CHECK(extraction_method IN ('native', 'ocr', 'hybrid')),
extraction_metadata_json TEXT NOT NULL DEFAULT '{}'
```

迁移必须逐条 `connection.execute()`，不得在事务中使用会隐式提交的
`executescript()`。旧行回填 `native` 和兼容 metadata。

metadata v1 示例中的 engine 值必须来自 Gate 0 生成并纳入版本控制的
`config/ocr-model-manifest.json`，不能由请求或运行时猜测。结构约束：

```json
{
  "type": "object",
  "required": [
    "version", "method", "total_pages", "native_pages",
    "ocr_pages", "ocr_attempted_pages", "quality",
    "review_required", "warning_codes", "engine"
  ],
  "properties": {
    "version": {"const": 1},
    "method": {"enum": ["native", "ocr", "hybrid"]},
    "total_pages": {"type": "integer", "minimum": 1, "maximum": 20},
    "native_pages": {"type": "array", "items": {"type": "integer"}},
    "ocr_pages": {"type": "array", "items": {"type": "integer"}},
    "ocr_attempted_pages": {
      "type": "array",
      "items": {"type": "integer"}
    },
    "mean_confidence": {
      "type": ["number", "null"],
      "minimum": 0,
      "maximum": 1
    },
    "quality": {"enum": ["native", "good", "review"]},
    "review_required": {"type": "boolean"},
    "warning_codes": {"type": "array", "items": {"type": "string"}},
    "engine": {
      "oneOf": [
        {"type": "null"},
        {
          "type": "object",
          "required": ["name", "version", "model_ids", "model_sha256"],
          "properties": {
            "name": {"const": "rapidocr-onnxruntime"},
            "version": {"type": "string", "minLength": 1},
            "model_ids": {
              "type": "array",
              "minItems": 3,
              "maxItems": 3,
              "items": {"type": "string", "minLength": 1}
            },
            "model_sha256": {
              "type": "array",
              "minItems": 3,
              "maxItems": 3,
              "items": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$"
              }
            }
          },
          "additionalProperties": false
        }
      ]
    }
  }
}
```

约束：

- 页码使用从 1 开始的整数，升序且互不重复。
- `mean_confidence` 只在至少选择一页 OCR 时存在。
- native/DOCX/TXT 的 engine 为 `null`，不能伪造 OCR provenance。
- API 不返回模型绝对路径。
- 重复导入相同原始 bytes 复用稳定 import ID，但刷新 extraction metadata；
  OCR engine/model 升级后的重跑必须记录新 provenance。

`profile_versions.source_import_id` 和 `candidate_facts.source_import_id` 继续指向同一
import，无需复制 OCR metadata。

## 9. HTTP、MCP、Skill 与 GUI

### 9.1 HTTP

继续使用：

```text
POST /v1/career/resumes/stage
```

不新增可被客户端配置的 OCR endpoint。stage 成功响应增加：

```text
extraction_method
review_required
warnings
pages.total
pages.ocr
```

stage 响应仍不返回 extracted text、private path、页面图或 upload token 以外的内部
标识。原有 sidecar token 认证保持不变。

### 9.2 MCP 与 Skill

不新增 MCP 工具。`get_resume_import_text(upload_token)` 增加非敏感 extraction
metadata 和 warning：

- Agent 必须把 OCR 文本称为“待确认识别结果”。
- 低质量 warning 必须告诉用户重点核对姓名、联系方式、数字、日期、公司和学校。
- Agent 不得声称 OCR 已验证，不得跳过 preview 或替用户 confirm。
- Agent 不得请求页面图、模型路径或敏感 profile。

更新 `career-resume-import` Skill 和 tests。

### 9.3 GUI

现有 PDF/DOCX importer 保持单入口：

- 上传期间：`正在本地读取简历…`
- OCR 成功：`已使用本地 OCR，内容尚未确认`
- review_required：`部分内容识别质量较低，请重点核对`
- native：不增加 OCR 文案。

GUI 继续自动开启 Career resume-import 会话，但 prompt 增加 method 和 warning code；
不得包含 OCR 文本、手机号、邮箱、private path 或模型路径。用户最终在现有五章节
preview 中确认，不新增第二套事实确认页面。

## 10. 错误契约

| code | 含义 |
|---|---|
| `OCR_UNAVAILABLE` | runtime、固定模型或模型 hash 不可用 |
| `OCR_PAGE_LIMIT` | 需要 OCR 的页面超过 10 页 |
| `OCR_FAILED` | 页面栅格化或 inference 失败，且 native text 不足以安全继续 |
| `NO_EXTRACTABLE_TEXT` | native + OCR 后全文仍少于 20 字符 |
| `FILE_TOO_LARGE` | 维持现有 10 MB 限制 |
| `PDF_PAGE_LIMIT` | 维持现有 20 页限制 |
| `INVALID_INPUT` | 加密、损坏、格式或结构非法 |
| `PERSISTENCE_ERROR` | 私有文件或 SQLite 写入失败 |

错误响应不得包含 OCR 文本、联系方式、绝对路径、模型路径、命令输出、SQL 或堆栈。

## 11. 依赖 Gate 0

在改业务代码前完成独立 spike：

1. 固定候选 RapidOCR、ONNX Runtime 和其直接依赖版本。
2. 验证 Python 3.12 的 macOS arm64/x64 与 Windows x64 wheel。
3. 在干净虚拟环境 import 并识别中英 fixture。
4. 断网后重新识别，确认没有下载请求。
5. 定位所有模型文件，记录 ID、bytes、SHA-256 和许可证/NOTICE，并生成
   `config/ocr-model-manifest.json`。
6. 测量安装增量、首次加载内存、单页/三页耗时。
7. 验证现有 macOS/Windows packaging 能包含 runtime 动态库和模型。

任一项失败时停止 OCR 实施，记录证据并重新评估 engine；不得自动切换云端、系统 OCR
或 Tesseract。Gate 0 通过后才可把依赖加入 root 和 Career package 的 production
dependencies。

## 12. 测试与验收

### 12.1 Domain

- native-only PDF 不实例化 OCR。
- scanned PDF 使用 fake OCR。
- hybrid PDF 只 OCR 稀疏页并保持页序。
- polygon 排序稳定。
- line confidence、字符加权 mean 和 warning 确定性。
- OCR 文本未改善时保留 native。
- 最终少于 20 字符拒绝。
- encrypted、damaged、21 页、11 OCR 页和超大页面安全失败。

### 12.2 Service、Migration 与 Repository

- v8 → v9 原子迁移；故障无残留且可重试。
- 旧 row 回填 native。
- extraction metadata create/reuse/soft-delete/reimport 正确。
- OCR 成功前不写 private original 或 staged row。
- 相同原始 bytes 幂等复用 ID。
- OCR provenance 不进入 masked profile 敏感字段或错误。

### 12.3 HTTP、MCP、Skill 与 GUI

- stage 非对象 JSON、坏 base64 和稳定 OCR errors。
- stage 响应不含 text/path/model path。
- `get_resume_import_text` 返回 text + provenance，但不含页面图。
- Skill 强制“待确认识别结果”和五章节确认。
- GUI native 无 OCR 文案；OCR/review 两级中文反馈。
- prompt 只包含 upload token、文件名、format、method 和 warning code。

### 12.4 真实离线验收

使用不含真实用户信息的本地 fixtures：

1. 中文扫描 PDF。
2. 中英混合扫描 PDF。
3. 一页 native + 一页 scanned 的 hybrid PDF。
4. 低质量/倾斜 fixture。

断网运行：

```text
专用 importer
→ stage
→ get_resume_import_text
→ Agent proposal
→ 用户逐章节确认
→ Career Vault
```

验证：

- 不产生网络请求。
- 不产生页面图片或 debug 文件。
- original bytes/hash 与上传一致。
- provenance、OCR 页码和 warning 正确。
- 低质量内容未自动确认。
- 删除测试简历后 private original 清理，事实保留遵守既有软删除规则。

### 12.5 对抗审查

重点检查：

- OCR 或错误日志泄漏 PII。
- 模型自动下载或 telemetry。
- PDF 页面尺寸/页数/内存放大。
- OCR confidence 被表述为事实准确率。
- 低质量文字绕过用户确认。
- OCR metadata 伪造、跨 import 混用或重复导入污染。
- Windows/macOS packaging 缺模型或动态库。

## 13. Gate 顺序

1. Gate 0：依赖、模型、许可、离线与 packaging spike。
2. Gate A：OCR Domain、fake engine、逐页回退和资源门禁。
3. Gate B：schema v9、Repository、Service 与 provenance。
4. Gate C：HTTP、MCP response、Skill 和 GUI。
5. Gate D：真实中英/hybrid 离线 OCR。
6. Gate E：全量回归、真实浏览器和对抗审查。

Gate E 通过前不得开始扩充招聘来源。

## 14. 明确不做

- PNG/JPEG 图片简历和多图排序。
- 手机拍照透视、阴影、背景和手写增强。
- 云端 OCR 或 Provider vision fallback。
- 表格/双栏语义重建、版式复刻和 VLM 文档理解。
- OCR 文本自动修正、事实自动确认或跨简历合并。
- 允许用户配置模型、路径、DPI、语言或阈值。
