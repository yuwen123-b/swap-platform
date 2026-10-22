# 变更影响分析：3D 生成方案从百炼 Tripo 切换到微软 TRELLIS.2

- 分析时间：2026-10-16 18:46
- 目标：放弃付费的百炼 Tripo，改用 Hugging Face 上微软开源的 TRELLIS.2 Space（免费）生成 GLB
- 依据：**真实探测**（本机 `curl https://microsoft-trellis-2.hf.space/gradio_api/info` 成功返回 14KB schema）+ 真实代码走查
- 当前状态：**仅分析，未改任何代码**

---

## 一、一句话结论

**技术可行，但任务书里有 6 处与实际不符，其中 2 处必须按实际改（否则直接跑不通），1 处会直接影响演示节奏（配额）需要你先知情。**

核心落差：
1. 它不是"一个函数调用"，而是 **5 步有状态的 session 链**（`extract_glb` 甚至不接受图像参数，纯靠服务端会话状态）；
2. 它是"**配额制免费**"而非"无限免费"——**免费账号约 3~5 次/天**，这是与 Tripo 最本质的资源模型差异；
3. 返回值是**本地临时文件**而非 URL，需要落盘（这点反而与现有架构一致）。

其余为可优化项，不阻断。

---

## 二、现状核查（真实代码）

### 2.1 现有 Tripo 链路

| 层 | 文件 | 关键点 |
|---|---|---|
| 服务 | `app/services/three_d_service.py`（330 行） | `_submit_task` → `_wait_task`（轮询 300s）→ `_extract_model_url` → `_download_model` 落盘 → `_update_status` 落库 |
| 路由 | `app/api/v1/model.py` | `POST /generate`（开关硬校验 + 所有者校验 + generating 重复触发保护 + BackgroundTasks）；`GET /{item_id}` |
| 配置 | `app/core/config.py` L88-107 | `model_3d_enabled` / `model_3d_model` / `model_3d_api_url` / `model_3d_texture_quality` / `model_3d_timeout_seconds`(300) / `model_3d_poll_interval_seconds` / `model_3d_download_timeout_seconds` |
| 前端 | `src/views/ItemDetail.vue` L485-631 + `src/components/ModelViewer.vue` | 轮询 `MODEL_MAX_POLLS=120`×3s=360s；`modelFailText()` 有 Tripo 硬编码文案 |
| 详情接口 | `app/api/v1/item.py` L287-301 | 下发 `model_status` / `model_url`(签名) / `model_error`(仅 failed) / `model_3d_enabled` |
| DB | `item` 表 | `model_status` / `model_url` / `model_generated_at` / `model_error`（幂等迁移已就位，**无需改动**） |
| 测试 | `tests/test_model_api.py`（13 例） | 全部针对 **API 层**（403/404/400/后台任务注册），**与 provider 无关** |

### 2.2 必须保留的既有契约（本次不动）

- **降级链**：`model ready → panorama ready → 静态图`（`ItemDetail.vue` 模板 L42-70）
- **状态机**：`none / generating / ready / failed` + `model_error`（失败原因必须继续可见）
- **开关**：`MODEL_3D_ENABLED` 后端硬校验（`model.py` + `three_d_service` 双重）
- **落库口径**：DB 只存**不带签名的相对路径**，读取时现场补 HMAC 签名
- **失败不静默降级**：失败必须显式置 `failed`（历史教训：偷偷降级为文生图重画）

---

## 三、TRELLIS.2 Space 实测核实（非推测）

### 3.1 可达性与身份

| 项 | 实测结果 |
|---|---|
| Space 页面 | `https://huggingface.co/spaces/microsoft/TRELLIS.2` — **存在**，描述 "Create 3D model from a single image" |
| 运行时地址 | `https://microsoft-trellis-2.hf.space` |
| Schema 探测 | ✅ 本机 `GET /gradio_api/info` → **HTTP 200，14118 bytes** |
| 引擎 | Gradio（ZeroGPU 队列式） |

### 3.2 完整 API 端点（实测 schema 解析）

| 端点 | 入参 | 出参 |
|---|---|---|
| `/start_session` | 无 | 无（建会话） |
| `/preprocess_image` | `input`(Image) | `Image Prompt`(Image) |
| `/get_seed` | `randomize_seed`=True, `seed`=0 | `Seed` |
| `/image_to_3d` | `image` + 14 个采样参数（`resolution`='1024' 等，均有默认值） | `3D Asset Preview`(**Html**) |
| `/extract_glb` | `decimation_target`=300000, `texture_size`=2048 | `Extracted GLB`(**Model3d**), `Download GLB` |

> ⚠️ 注意 `/extract_glb` **不接受任何图像参数** —— GLB 完全依赖服务端 session 中 `/image_to_3d` 留下的状态。

### 3.3 官方调用范式（来自 HF 官方文档与示例）

```python
from gradio_client import Client, handle_file

trellis = Client("microsoft/TRELLIS.2")          # 保持同一实例 = 保持同一 session
trellis.predict(api_name="/start_session")
preprocessed = trellis.predict(input=handle_file(image), api_name="/preprocess_image")
trellis.predict(image=handle_file(preprocessed), seed=0, resolution="512", ..., api_name="/image_to_3d")
glb, _ = trellis.predict(decimation_target=300000, texture_size=2048, api_name="/extract_glb")
```

### 3.4 配额（HF 官方文档原文，**最关键的约束**）

| 身份 | ZeroGPU 每日配额 |
|---|---|
| 无 token（匿名共享池） | **2 分钟/天** |
| 免费 HF 账号（带 token） | **3.5 分钟/天** |
| HF Pro | 25 分钟/天 |

一次 1024 分辨率 + 提取 GLB 约消耗 **30~60 秒 GPU**。

→ **免费账号实际可用 ≈ 3~5 次/天**；匿名 ≈ 2~3 次/天，且是共享限流池，高峰期极可能排队失败。

---

## 四、任务书 vs 实际的 6 处落差

| # | 任务书写法 | 实际 | 处理 |
|---|---|---|---|
| **L1** | 实现 `generate_3d_model_from_image(image_url)` 一个函数 | 需 **5 步 session 链**，且必须复用同一 `Client` 实例（服务端有状态） | **必须按实际改**：函数内串起 5 步并做异常归一化 |
| **L2** | "返回生成的 GLB 模型 URL" | `gradio_client` 返回的是**本地临时文件路径**，不是 URL；外链还带 TTL | **必须按实际改**：函数直接**下载/落盘** 到 `uploads/items/{id}/models/model.glb`（与现有 `_download_model` 落盘口径一致） |
| **L3** | "免费的" | 是**配额制免费**（免费账号 3.5min/天 ≈ 3~5 次/天） | **需你知情**：演示够用，但不能像 Tripo 那样无限次；建议保留开关 + 每日次数上限守卫 |
| **L4** | "增加 `TRELLIS_SPACE_URL` 等配置" | 除 Space URL 外，**`HF_TOKEN` 是事实上的准必需项**（否则掉进 2min 匿名池） | 增加 `TRELLIS_HF_TOKEN`（可留空，留空走匿名并给出提示） |
| **L5** | "前端逻辑基本不变" | `ItemDetail.vue::modelFailText()` 里有 Tripo 硬编码：`/not activated/`→"百炼 Tripo 服务未开通"、`/invalid api-?key/`→"DASHSCOPE_API_KEY" | **需小改**：换成 HF 配额/排队/网络语义 |
| **L6** | （未提） | 超时窗口按 Tripo 的 2~4 分钟设计（后端 300s / 前端 360s）；TRELLIS 有**冷启动 + ZeroGPU 排队**，波动 1~6 分钟 | **需拍板**：上调超时（建议后端 600s / 前端 900s） |

### 净收益（顺带简化）

Space 的 `/preprocess_image` **同时接受本地 `path` 与公网 `url`**。因为后端本地就能跑 `gradio_client`，可直接上传本地 JPEG：

- ✅ **`PUBLIC_BASE_URL` / ngrok 隧道不再是 3D 的前置依赖**（少一个极易挂的环节）
- ✅ `_require_ready()` 里的 `public_base_url` 校验可从 3D 链路移除
- ⚠️ 但 `PUBLIC_BASE_URL` 仍被 **360° 外推 / 图像编辑 / 语音识别** 使用，**配置本身不能删**

---

## 五、变更方案设计

### 5.1 后端（核心）

**新增 `app/services/trellis_client.py`** —— 只负责"图 → 本地 GLB 文件"，不碰 DB：

```
generate_glb(local_image_path: Path, dest: Path) -> None
  ├─ Client(space_url, hf_token=... or None)     # 惰性 import gradio_client
  ├─ /start_session
  ├─ /preprocess_image(input=handle_file(path))
  ├─ /get_seed(randomize_seed=True, seed=0)
  ├─ /image_to_3d(image=..., seed=..., resolution=config)   # 失败/超时 → RuntimeError
  ├─ /extract_glb(decimation_target=..., texture_size=...)
  └─ shutil.copy(返回的本地临时文件 → dest)，校验非空 + GLB 魔数(b'glTF')
```

异常归一化（**必须**）：`gradio_client` 的报错是英文堆栈/`ValueError`/`httpx` 超时，需转成可读中文，例如：
- 配额耗尽 / `exceeded your GPU quota` → "TRELLIS 免费 GPU 配额今日已用尽，请明天再试或使用 Pro 账号"
- 队列超时 → "TRELLIS 生成队列繁忙，请稍后重试"
- 网络不可达 → "无法连接 Hugging Face Space，请检查网络或 HF_ENDPOINT 配置"

**改造 `app/services/three_d_service.py`**：
- 保留：`is_enabled` / `model_url` / `sign_model_url` / `_update_status` / `_load_source_url` / `run_generate` / `get_model`（**状态机与落库口径零改动**）
- 删除：`_submit_task` / `_wait_task` / `_extract_model_url`（Tripo 专属）
- 替换：`_download_model` 改为从**本地临时文件**拷入 `dest`
- 改造：`_require_ready()` → 校验 `model_3d_enabled` + Space 可达性前置（**不再校验 `dashscope_api_key` / `public_base_url`**）
- 复用：`ensure_local_jpeg()`（**保留**，用于把 WEBP/PNG 统一成 JPEG，TRELLIS 同样偏好标准图）

### 5.2 配置（`config.py` + `.env` + `.env.example`）

```ini
# 新增
MODEL_3D_PROVIDER=trellis                        # 决策点 D1 决定是否保留 tripo 分支
TRELLIS_SPACE_URL=https://microsoft-trellis-2.hf.space
TRELLIS_HF_TOKEN=                                # 留空=匿名(2min/天)；填免费账号 token=3.5min/天
TRELLIS_RESOLUTION=1024                          # 512 更快省配额 / 1024 更精细
TRELLIS_GLB_DECIMATION_TARGET=300000
TRELLIS_GLB_TEXTURE_SIZE=2048
MODEL_3D_TIMEOUT_SECONDS=600                     # 决策点 D3

# 移除（Tripo 专属）
MODEL_3D_MODEL / MODEL_3D_API_URL / MODEL_3D_TEXTURE_QUALITY
```

`.env.example` 的「★★ 排查手册 ★★」整段替换为 TRELLIS 版（配额、token、冷启动、镜像）。

### 5.3 依赖

- 新增 **`gradio_client`**（`pyproject.toml` + `uv.lock`）
- 连带：`httpx` / `huggingface_hub` / `tomlkit` / `packaging`（`websockets` 项目已有 17.1）
- ✅ 全部免费、无付费依赖；Python 3.12.10 满足 `gradio_client` 要求（≥3.10）

### 5.4 前端（小改，非"基本不变"）

| 文件 | 改动 |
|---|---|
| `src/views/ItemDetail.vue` | ① `modelFailText()` 双语映射换为 HF 语义；② `MODEL_MAX_POLLS` 120→300（900s，对齐后端 600s 兜底）；③ 提示语 "约 2-4 分钟" → "约 1-6 分钟（含排队）" |
| `src/components/ModelViewer.vue` | **零改动**（继续加载本地签名的 `model.glb`） |
| `src/api/model.js` | **零改动** |

### 5.5 测试

- `tests/test_model_api.py`：**预期零回归**（13 例全在 API 层）
- **新增** `tests/test_three_d_service.py`：mock `gradio_client.Client`，覆盖 5 步链、异常归一化、落盘校验、`_require_ready` 前置
- 基线：pytest **512 passed** → 预计 **525+**

---

## 六、风险与应对

| 风险 | 等级 | 应对 |
|---|---|---|
| **GPU 配额耗尽**（3~5 次/天） | 🔴 高 | 保留开关；演示前**先预热 1 次**确认配额；建议加每日次数守卫；`.env.example` 写死配额说明 |
| **ZeroGPU 冷启动 + 排队** | 🟠 中 | 超时上调（600/900s）；失败文案区分"排队"与"真失败"；演示前预热 |
| **hf.space 国内网络不稳** | 🟠 中 | 本机实测可达（200）；加 `HF_ENDPOINT` 配置项兜底。**注意**：镜像主要代理模型权重下载，**Space 推理流量不一定走镜像**，需真实测试 |
| **GLB 体积**（30 万面 + 2K 贴图，估 10~20MB） | 🟡 低 | 现有 `ModelViewer` 已有进度条；可通过 `decimation_target` 下调 |
| **`gradio_client` 版本漂移**（Space 重构端点） | 🟡 低 | 端点名写进配置（`TRELLIS_*_ENDPOINT`）便于应急；异常归一化会暴露真实原因 |

---

## 七、需要你拍板的 5 个决策点

| # | 问题 | 建议 |
|---|---|---|
| **D1** | 彻底删除 Tripo，还是保留 `MODEL_3D_PROVIDER=trellis\|tripo` 双 provider？ | **建议保留双分支**（默认 trellis）。理由：① 配额耗尽时可一键回退；② 现有 Tripo 代码/文档/测试资产不白费；③ 删除是不可逆的。**但任务书说"放弃/移除 Tripo"——若你坚持彻底删除，我照办** |
| **D2** | `TRELLIS_HF_TOKEN` 是否必须？ | **建议可留空**（留空走匿名，2min/天，能跑但配额更低），同时强烈建议你提供一个免费账号 token |
| **D3** | 超时窗口是否上调？ | **建议上调**：后端 300→600s，前端 360→900s（ZeroGPU 排队不可控） |
| **D4** | 是否移除 3D 链路的 `PUBLIC_BASE_URL` 依赖？ | **建议移除**（改本地上传），但配置项本身保留给 360°/图像编辑用 |
| **D5** | 前端失败文案是否改写？ | **建议改写**（Tripo 的"未开通"提示在 HF 场景下会误导） |

---

## 八、影响面清单（文件级）

**后端（改 5 / 增 1）**
- 🆕 `app/services/trellis_client.py`
- ✏️ `app/services/three_d_service.py`（provider 分派 / 去掉 Tripo 调用 / 落盘来源变更）
- ✏️ `app/core/config.py`（3D 配置段重写）
- ✏️ `.env` / `.env.example`
- ✏️ `pyproject.toml` + `uv.lock`（+gradio_client）
- ✏️ `app/services/image_utils.py`、`app/api/v1/item.py`（仅注释措辞）

**前端（改 1 / 0 增）**
- ✏️ `src/views/ItemDetail.vue`（文案 + 轮询上限 + 提示语）

**测试（增 1）**
- 🆕 `tests/test_three_d_service.py`；`tests/test_model_api.py` 预期零回归

**文档**
- 🆕 本文件；后续 `docs/验证清单-3D方案切换TRELLIS.md`

**不动**：DB schema、`model.py` / `model.js`、`ModelViewer.vue`、降级链、状态机、`PUBLIC_BASE_URL` 配置项本身

---

## 九、验证计划（确认后执行）

1. `uv add gradio_client` → `uv sync` → import 自检
2. **真实链路 1 次**（消耗配额，先与你确认后执行）：任取一件物品 → 生成 GLB → 落盘 → `glTF` 魔数校验 → 前端加载出模型
3. `pytest`（预计 ≥525 passed）
4. `vite build`
5. CDP 真机回归：失败文案 / 生成中浮层 / 生成→失败转变 / 非所有者无入口（沿用 `_probe_3d/verify_fix.py` 思路，**用 DB 状态驱动，尽量少花配额**）
6. 输出《验证清单-3D方案切换TRELLIS.md》，数据还原基线

---

**等你确认 D1~D5 后，我直接开始改代码。**
