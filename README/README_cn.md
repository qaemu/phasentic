<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/wordmark-dark.svg">
    <img src="../assets/wordmark-light.svg" alt="phasentic" width="360">
  </picture>
</p>

<p align="center">
  基于经过验证、可复现方法的粉末X射线衍射物相鉴定工具。
</p>

<p align="center">
  <a href="../README.md">English</a> | <a href="README_es.md">Español</a> | <a href="README_fr.md">Français</a> | <b>简体中文</b> | <a href="README_ar.md">العربية</a> | <a href="README_de.md">Deutsch</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%E2%80%933.13-3776ab" alt="Python 3.10–3.13">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT 许可证"></a>
</p>

<p align="center">
  <a href="#install">安装</a> ·
  <a href="#quick-start">快速上手</a> ·
  <a href="#how-accurate-is-it">验证</a> ·
  <a href="../docs/">文档</a> ·
  <a href="#how-this-was-built">开发方式</a>
</p>

Phasentic 读取粉末XRD扫描数据（`.xy`、`.xrdml` 或 ASCII `.raw`），检测衍射峰，检索 CNR 的 [POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/) 参考数据库，并对最多五个物相的混合物进行拟合。它给出经排序的物相假设，并将全部设置、哈希值和警告记录在 JSON 报告中。软件在本地运行，可通过浏览器或命令行使用。

<p align="center">
  <img src="../docs/images/interface.png" alt="Phasentic 界面：ZrO2 与 LiOH·H2O 的暂定结果，附拟合图和竞争假设" width="900">
  <br>
  <sub>随机选取的一条开发集扫描，来自 Precursor Genome 数据集（PG_2452，Cu Kα）。Phasentic 识别出 ZrO₂ 和 LiOH·H₂O；经人工 Rietveld 精修确定的标注中还含有 Li₂CO₃，本次运行未能检出。残余信号可在 <i>Evidence per phase</i>（各物相证据）中看到。</sub>
</p>

<a name="how-accurate-is-it"></a>

## 准确度如何

方法在测试前即已冻结，并预先声明了目标值，随后在 200 条从未见过的扫描上仅运行一次（Precursor Genome，标注由人工 Rietveld 精修确定）。放弃作答计为失败。

| 层级 | 正确数 | 正确率 | 95% 置信区间（Wilson） | 声明目标 |
|---|---|---|---|---|
| 化合物与晶体结构均正确（strict） | 74 / 200 | 37.0% | 30.6–43.9% | ≥ 35% |
| 化合物正确，多晶型不限（family） | 99 / 200 | 49.5% | 42.6–56.4% | ≥ 45% |

两项点估计均达到目标；两项置信下限均低于目标。准确度在很大程度上取决于物相数量：

| 样品中的物相数 | 扫描数 | family 层级正确数 |
|---|---|---|
| 1 | 8 | 3 |
| 2 | 125 | 87 (70%) |
| 3 个及以上 | 67 | 9 (13%) |

验证协议、此前一次留出测试集运行（上一版本为 32% / 42%）、失败分析以及结果凭证见 [docs/validation.md](../docs/validation.md)。上述数字仅适用于经验证的预设配置（POW_COD、Cu Kα，并提供样品的前驱体化学组成）；其他设置未经测试。

<a name="install"></a>

## 安装

需要 Python 3.10–3.13。最简单的方式是将 `phasentic` 命令安装在独立环境中：

```bash
pipx install git+https://github.com/qaemu/phasentic
```

或使用 [uv](https://docs.astral.sh/uv/)：`uv tool install git+https://github.com/qaemu/phasentic`，
或直接使用 pip：`pip install git+https://github.com/qaemu/phasentic`。

检查是否安装成功：

```bash
phasentic --version
```

### 添加 POW_COD 参考数据库（仅需一次）

未安装 POW_COD 时，Phasentic 使用一个仅含三个物相的演示子集运行，只适合试用界面。用于实际工作时：

1. 从 [CNR 下载页面](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/)下载 **POW_COD 2205 (FULL)**（约 1.9 GB）。
2. 运行：

   ```bash
   phasentic setup-powcod ~/Downloads/powcod-2205.zip
   ```

该命令会校验压缩包，将其解压到 `~/.phasentic/powcod`（约 6 GB），并一次性构建查询缓存（20–60 分钟）。此后 Phasentic 默认使用 POW_COD。

<a name="quick-start"></a>

## 快速上手

启动本地界面并打开 <http://127.0.0.1:8000>：

```bash
phasentic serve
```

选择一条扫描，输入前驱体和目标产物的化学式，保持选中 *Validated method*（经验证的方法，默认选项），然后点击 *Analyze*（分析）。*Download report*（下载报告）生成可打印的两页报告（拟合图、各物相证据、竞争假设、方法与可追溯性信息），可保存为 PDF；*JSON* 提供完整的机器可读记录。

在命令行中使用相同的经验证的方法：

```bash
phasentic analyze scan.xrdml --preset validated --chemistry "Ag2O BaCO3 Ba2Ag2C2O7" --output report.json
```

`--chemistry` 将候选物相限制为由这些化学式中的元素以及 H、C、O 组成的物质（碳酸盐、氢氧化物、水合物）。不使用 `--preset` 时，所有分析设置均可通过命令行参数调整（`phasentic analyze --help`）；这些参数组合未经验证。

若要得出 `supported` 判定，还需要使用标准样品扫描进行峰位校准（默认为 NIST SRM 640g 硅）：`phasentic calibrate standard.xy`。

## 不适用的场景

- **用于证明某一物相存在。** 结果是经过排序的假设，需由科研人员确认，最好通过 Rietveld精修。
- **用于测定物相含量。** 拟合标度因子只是用于筛查的幅值，不是质量分数。
- **用于含三个及以上物相的样品。** 测试中仅有 13% 的情况能识别出全部化合物。
- **用于次要物相或散射较弱的物相。** 此类物相（例如与重元素物相共存的 Li、B 或 K 盐）常被漏检。
- **缺少样品化学组成信息，或使用 Cu 以外的阳极靶时。** 这些情况不在验证范围内。

## 工作原理

1. 导入扫描数据，估计背底，检测衍射峰（考虑噪声水平）。
2. 从 POW_COD 中检索候选物相，并限定在样品所含元素范围内。
3. 采用有界集束搜索、残差再检索和物相替换，以参考谱图的非负线性组合拟合混合物；剔除强衍射线在扫描中缺失的物相。
4. 对假设排序，报告歧义情况，并记录溯源信息（输入哈希值、设置、数据库标识、算法版本）。

详情见 [docs/scientific-method.md](../docs/scientific-method.md) 和 [PARAMETERS.md](../PARAMETERS.md)。

## 复现验证结果

克隆仓库并安装：

```bash
git clone https://github.com/qaemu/phasentic && cd phasentic
pip install -e .
```

验证运行使用 `scripts/run_wp5_parallel.py`；若分析代码与冻结配置（`validation/wp5-precursor-frozen-v5.json`）中的哈希值不一致，该脚本将拒绝运行。各数据集（开发集与留出测试集）的样本清单和结果凭证位于 [`validation/`](../validation/)；扫描数据本身来自 [Precursor Genome](https://github.com/lauren-walters/precursor-genome) 数据集（CC BY 4.0）。分步说明见 [docs/validation.md](../docs/validation.md)。

<a name="how-this-was-built"></a>

## 开发方式

Phasentic 几乎完全由 Anthropic 的编程智能体 **Claude Code** 在我的指导下编写。我是唯一的开发者。问题、方法和验证协议由我选定，结果由我审查，本仓库中的每一项结论均由我负责。

使结论可供核查的环节均在看到结果之前确定：准确度目标在调参前声明；调参仅使用 100 条开发集扫描；留出测试集保持封存且只运行一次；设置和代码通过哈希值冻结；后续重构必须精确复现全部 300 个结果（[docs/validation.md](../docs/validation.md)）。借助 AI 完成的提交带有 `Assisted-by: Claude Code` 提交尾部信息（trailer）。参见 [AI_USE.md](../AI_USE.md)。

## 引用

如果 Phasentic 对您的工作有所帮助，请引用您所使用的版本。GitHub 的 *Cite this repository* 按钮（基于 [CITATION.cff](../CITATION.cff)）可提供 APA 和 BibTeX 格式。此外，请同时引用 POW_COD 和 Crystallography Open Database。

## 许可证

代码采用 MIT 许可证。POW_COD、COD 和 Precursor Genome 的数据按其各自条款分发，不包含在本仓库中。
