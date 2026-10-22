# Tripo 3D 生成探针报告（第四轮：✅ 成功）

- 执行时间：2026-10-14 15:47:48–15:51:01
- 探针类型：真实调用（非 mock）
- 输入图：item 55《复古胶片相机》原图 → JPEG 600×400 → `PUBLIC_BASE_URL` 签名 URL
- 结果：**SUCCEEDED，GLB 下载成功（40.8 MB，144 万面）**

---

## 一、探针结果

| 项目 | 结果 |
|---|---|
| HTTP 状态码 | **200** |
| task_id | `e3cc0ff3-bed9-405b-8e4c-cd3b877819d1` |
| 轮询终态 | **SUCCEEDED**（10 次轮询） |
| 耗时 | 提交→终态 **145.4s**（15:47:49 → 15:50:12） |
| GLB 可下载 | ✅ **是**：`pbr_model_url` → HTTP 200，**42,828,600 bytes（40.8 MB）**，magic=`glTF` |
| 预览渲染图 | ✅ `rendered_image_url` → HTTP 200，217,285 bytes（实际 PNG 512×512） |
| base_model_url | 未返回（`pbr=true` 默认，只返回 PBR 模型） |
| request_id | `eb5123f8-a729-98c6-877d-31162db9a766` |

调用参数：`Tripo/Tripo-H3.1`，`input.image=公网签名URL`，`parameters={texture_quality:standard, geometry_quality:standard}`

## 二、GLB 有效性验证

| 项目 | 结果 |
|---|---|
| magic / version | `glTF` v2 ✅，声明长度与实际一致（42,828,600 B） |
| generator | `https://tripo3d.ai` |
| 结构 | scenes=1 / nodes=1 / **meshes=1** / materials=1 / **textures=3（PBR 贴图组）** / images=3 |
| **三角面数** | **≈ 1,444,464（144 万面）** —— 符合 H3.1 standard 几何上限（150 万面） |
| 预览图 | PNG 512×512 RGBA，已转存 `preview.png` |

## 三、生成效果（人工比对）

**生成的正是原图那台 Polaroid OneStep2 拍立得相机，还原度很高**：

- ✅ 造型正确：方盒机身、镜头凸出、取景器、快门红钮、相纸仓
- ✅ 贴图细节保留：「One Step 2」「Polaroid」文字清晰可辨，机身彩虹条完整还原
- ✅ PBR 质感：白色塑料光泽自然
- ⚠️ 小瑕疵：背面文字镜像反写（`ITV99 CAMERA`）—— 单图生 3D 的常见现象，仅背面视角可见

## 四、三轮失败的原因复盘（重要）

**开通生效延迟**。时间线：

| 时间 | 事件 |
|---|---|
| 15:20–15:37 | 前三轮探针全部 FAILED「product is not activated」（此时用户已在控制台点开通，但**尚未生效**） |
| ~15:36 | 用户确认「已开通 / 刚刚开通」 |
| **15:47** | 第四轮探针 → **SUCCEEDED** |

→ **结论：百炼控制台开通 Tripo 后需要约 10 分钟生效**，期间调用报 `The product is not activated`。前三轮的 403/FAILED 全部是同一原因，与 Workspace、Key、代码无关（用户账号只有默认空间，通用域就是正确路径）。

## 五、对正式实现的 3 条工程提示

1. **40.8 MB 的 GLB 对前端太重**：H3.1 standard 几何就有 144 万面。正式实现建议：
   - 优先用 `geometry_quality=standard` 且考虑 P1.0（2 万面、文件小、更快）做对比测试；
   - 或后端对 GLB 做 Draco/meshopt 压缩（Three.js 自带解码器，零新前端依赖）。
2. **GLB 链接 2 小时失效**：`SUCCEEDED` 后必须立即下载落盘（本次 40.8 MB 下载耗时 46.4s，异步任务里要留足时间）。
3. **成本与开关**：本次单图生 3D（H3.1 + 标准贴图）≈ 2.1 元/次。正式实现保持既定设计：`MODEL_3D_ENABLED` 开关（默认关）+ 手动触发。

## 六、产物与清理

- 临时探针脚本 `scripts/_tmp_tripo_probe4.py`：**已删除**
- **保留**（探针成功产物，供查看）：
  - `agent_back/uploads/_probe3d/model_pbr.glb`（40.8 MB，可用任意 glTF 查看器打开）
  - `agent_back/uploads/_probe3d/preview.png`（模型渲染图）
  - `agent_back/uploads/_probe3d/preview.webp`（原始下载件）
- 业务代码：**零改动**
- 输入图 `probe55.jpg`：保留于 `uploads/items/`（探针输入，待下批清理）

## 七、下一步（按既定顺序）

1. **第 1 步：修视角一致性** —— 换 `qwen-image-2.0-pro`（上批实测能真正旋转视角，19s/张），删除文生图降级分支
2. **第 2 步：多图生 3D** —— Tripo `images` 数组长度固定 4、顺序恰为**前/左/后/右**，与现有 panorama 四视角产物完美对齐，且与单图同价
3. **第 3 步：前端 `ModelViewer.vue`** —— GLTFLoader + 补灯光（PBR 材质配无光照材质会发黑），独立组件，不动 `PanoramaViewer.vue`
