<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/wordmark-dark.svg">
    <img src="../assets/wordmark-light.svg" alt="phasentic" width="360">
  </picture>
</p>

<p align="center">
  采用经过验证、可复现方法的粉末 X 射线衍射物相鉴定工具。
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
  <a href="../docs/">文档</a>
</p>

Phasentic 读取粉末 XRD 扫描（`.xy`、`.xrdml` 或 ASCII `.raw`），检测衍射峰，
在基于 [Crystallography Open Database](https://www.crystallography.net/cod/)（或 CNR 的 [POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/)）
构建的参考数据库中检索，并拟合最多五个物相的混合物。它给出按排序的物相假设，
并把全部设置、哈希值和警告记录在 JSON 报告中。可在本地、浏览器或命令行中运行。

<p align="center">
  <img src="../docs/images/interface.png" alt="Phasentic 界面：ZrO2 的暂定结果，附拟合图、竞争假设和各物相备选" width="900">
  <br>
  <sub>随机选取的一条开发集扫描，来自 Precursor Genome 数据集（PG_2452，Cu Kα）。Phasentic 选定 ZrO₂。经人工精修的标注中还含有两个次要物相：LiOH·H₂O 仅出现在竞争假设中（ZrO₂ + LiH₃O₂），Li₂CO₃ 则未被本次运行检出。</sub>
</p>

<a name="how-accurate-is-it"></a>
## 准确度如何

参数在 485 条 Precursor Genome 扫描（人工精修标注）上调优，然后在调优从未接触过的
200 条锁定扫描上运行，使用的数据库为 PXRD_COD 2026.11（源自 COD，并以 Materials
Project 补充）。放弃给出结果计为失败。

| 层级 | 正确 | 比例 |
|---|---|---|
| 化合物与晶体结构均正确（严格） | 85 / 200 | 42.5% |
| 化合物正确、多晶型不限（同族） | 104 / 200 | 52.0% |

这是在这 200 条扫描上的第二次运行。第一次（72 和 99）使用仅含 COD 的数据库；
数据库补充、恢复氢的化学式以及优先采用材料最高对称性描述，均只在 485 条调优扫描上
开发。未调优的方法得分为 71 和 96。以上数字适用于使用 PXRD_COD 2026.11、Cu Kα
和样品前驱体化学组成的已验证预设；其他设置未经测试。

<a name="install"></a>
## 安装

安装过程会配置 Python 3.12、Phasentic 及其参考数据库（从 Zenodo 下载 8.6 GB；
请预留约 10 GB 空间）。无需管理员权限。

Windows：把以下四行粘贴到 PowerShell 中（第一行是 [uv](https://docs.astral.sh/uv/)
的官方安装程序，用于安装 Python）：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/tags/v1.0.0.zip
phasentic setup
```

macOS 和 Linux：

```bash
curl -LsSf https://raw.githubusercontent.com/qaemu/phasentic/v1.0.0/install.sh | sh
```

在 Windows 上，`phasentic setup` 会下载数据库，在桌面和开始菜单中添加
**Phasentic** 快捷方式，并在独立窗口中打开 Phasentic；重新安装前请先关闭
Phasentic。在 macOS 上安装程序会把 Phasentic 添加到“应用程序”，在 Linux 上添加到
应用菜单。如果下载中断，再次运行相同的命令即可续传。

### 改用 POW_COD

如果您从 [CNR 下载页面](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/)
获得了 **POW_COD 2205 (FULL)**，可用下面的命令安装；之后 Phasentic 会用它代替 COD
数据库。公布的准确度数据是用 COD 数据库测得的，而非 POW_COD。

```bash
phasentic setup-powcod ~/Downloads/powcod-2205.zip
```

<a name="quick-start"></a>
## 快速上手

通过快捷方式打开 Phasentic，或运行 `phasentic-app`。如需在浏览器中使用，运行下面的
命令并打开 <http://127.0.0.1:8000>：

```bash
phasentic serve
```

把扫描文件拖到窗口上（或选择文件），输入前驱体和目标产物的化学式，然后点击
*Analyze*。提供化学式且使用 Cu Kα 时，会采用已验证的方法；峰容差和最大物相数可在
*Search settings* 中修改，其他取值未经验证。*PDF* 保存一份包含实测值与计算值的
简明报告；*Formal report* 打开可打印的正式报告（拟合图、各物相证据、竞争假设、
方法与可追溯性）；*CIF* 和 *JSON* 提供数据。界面提供英文和西班牙文。

在命令行中使用同一已验证方法：

```bash
phasentic analyze scan.xrdml --preset validated --chemistry "Ag2O BaCO3 Ba2Ag2C2O7" --output report.json
```

`--chemistry` 把候选物相限制在这些化学式所含元素加上 H、C、O（碳酸盐、氢氧化物、
水合物）。不加 `--preset` 时，每项分析设置都可通过参数调整（`phasentic analyze
--help`）；这些组合未经验证。

结果最多为 `tentative`（或 `ambiguous` / `unresolved`）：`supported` 结论需要附带
谱线位置校准，而本版本不提供该功能。`phasentic calibrate standard.xy` 仍可用标准样
扫描（默认 NIST SRM 640g 硅）检查仪器的谱线位置。

## 不适用的情形

- **测定物相含量。** 拟合比例因子是筛选用的幅度，不是质量分数。
- **含三个或更多物相的样品**，测试中仅有 11% 的情况识别出全部化合物。
- **次要物相或散射较弱的物相**（例如与重元素物相共存的 Li、B 或 K 盐），经常漏检。

## 工作原理

1. 导入扫描，估计背景，检测衍射峰（考虑噪声）。
2. 从参考数据库中检索候选物相，限于样品所含元素。
3. 通过有界束搜索、残差再检索和物相替换，拟合参考谱型的非负混合；
   剔除强线在扫描中缺失的物相。
4. 对假设排序，报告歧义，并记录来源信息（输入哈希、设置、数据库标识、算法版本）。

详情：[docs/scientific-method.md](../docs/scientific-method.md) 和
[PARAMETERS.md](../PARAMETERS.md)。

## 引用

如果 Phasentic 对您的工作有所贡献，请引用您所使用的版本。GitHub 的
*Cite this repository* 按钮（基于 [CITATION.cff](../CITATION.cff)）提供 APA 和
BibTeX 格式。另请引用参考数据库
[PXRD_COD 2026.11](https://doi.org/10.5281/zenodo.24059658) 及其来源：
Crystallography Open Database 和 Materials Project（若改用 POW_COD，也请引用）。

## 许可证

代码采用 MIT 许可证。参考数据库采用 CC BY 4.0（COD 数据为 CC0，Materials Project
数据为 CC BY 4.0）。POW_COD 和 Precursor Genome 数据按其各自条款分发，不包含在本
仓库中。
