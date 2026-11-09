<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/wordmark-dark.svg">
    <img src="../assets/wordmark-light.svg" alt="phasentic" width="360">
  </picture>
</p>

<p align="center">
  تحديد الأطوار بحيود الأشعة السينية للمساحيق بطريقة مُتحقَّق منها وقابلة لإعادة الإنتاج.
</p>

<p align="center">
  <a href="../README.md">English</a> | <a href="README_es.md">Español</a> | <a href="README_fr.md">Français</a> | <a href="README_cn.md">简体中文</a> | <b>العربية</b> | <a href="README_de.md">Deutsch</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%E2%80%933.13-3776ab" alt="Python 3.10–3.13">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="رخصة MIT"></a>
</p>

<p align="center">
  <a href="#install">التثبيت</a> ·
  <a href="#quick-start">البدء السريع</a> ·
  <a href="#how-accurate-is-it">التحقق</a> ·
  <a href="../docs/">التوثيق</a>
</p>

يقرأ Phasentic مسحًا لحيود الأشعة السينية للمساحيق (XRD) بصيغة &lrm;`.xy` أو &lrm;`.xrdml` أو &lrm;`.raw` النصية (ASCII)،
ويكشف القمم، ويبحث في قاعدة بيانات مرجعية مبنية من [Crystallography Open Database](https://www.crystallography.net/cod/) (أو [POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/) التابعة لـ CNR)،
ويطابق مخاليط تضم ما يصل إلى خمسة أطوار. ويُعيد فرضيات أطوار مرتّبة، مع تسجيل كل إعداد وكل قيمة تجزئة (hash) وكل تحذير
في تقرير بصيغة JSON. ويعمل محليًا، في المتصفح أو من سطر الأوامر.

<p align="center">
  <img src="../docs/images/interface.png" alt="واجهة Phasentic: نتيجة مبدئية لـ ZrO2 مع مخطط المطابقة والفرضيات المنافسة والبدائل لكل طور" width="900">
  <br>
  <sub>مسح تطويري من مجموعة بيانات Precursor Genome (PG_2452، Cu Kα)، اختير عشوائيًا. يختار Phasentic الطور ZrO₂. ويتضمن الوسم المرجعي المنقَّح يدويًا طورين ثانويين آخرين: LiOH·H₂O الذي يظهر فقط ضمن الفرضيات المنافسة (ZrO₂ + LiH₃O₂)، وLi₂CO₃ الذي يفوته هذا التشغيل.</sub>
</p>

<a name="how-accurate-is-it"></a>

## ما مدى دقته

جُمِّدت الطريقة قبل الاختبار، مع هدف مُعلَن مسبقًا، وشُغِّلت مرة واحدة
على 200 مسح لم يسبق لها رؤيتها (Precursor Genome، بوسوم مرجعية مستخلَصة من تنقيح Rietveld بشري).
وتُحتسب حالات الامتناع عن الإجابة إخفاقات.

| المستوى | الصحيح | النسبة | فترة ثقة 95% (Wilson) | الهدف المُعلَن |
|---|---|---|---|---|
| المركّبات والبُنى البلورية الصحيحة (strict) | 85 / 200 | 42.5% | 35.9–49.4% | ≥ 35% |
| المركّبات الصحيحة، بأي شكل بلوري متعدد (family) | 104 / 200 | 52.0% | 45.1–58.8% | ≥ 45% |

يبلغ كلا التقديرين النقطيين هدفيهما؛ بينما يقع كلا الحدّين الأدنيين دونهما.
وتعتمد الدقة اعتمادًا كبيرًا على عدد الأطوار:

| عدد الأطوار في العيّنة | المسوح | الصحيح على مستوى family |
|---|---|---|
| 1 | 8 | 3 |
| 2 | 125 | 87 (70%) |
| 3 أو أكثر | 67 | 9 (13%) |

يجد القارئ البروتوكول، والتشغيل السابق على مجموعة الاختبار المحجوزة (32% / 42% للإصدار السابق)،
وتحليل الإخفاقات، وسجلات الإثبات (receipts) في [docs/validation.md](../docs/validation.md).
وتنطبق هذه الأرقام على الإعدادات المُتحقَّق منها مع POW_COD وCu Kα
وكيمياء السلائف الخاصة بالعيّنة؛ أما الإعدادات الأخرى فلم تُختبر.
قيست هذه الأرقام بنافذة 0–100°؛ أما الإعداد الحالي فيستخدم 0–90° ولم يُعَد التحقق منه بعد (انظر [CHANGELOG.md](../CHANGELOG.md)).

<a name="install"></a>

## التثبيت

يثبّت أمر واحد Python 3.12 وPhasentic وقاعدة بياناته المرجعية (تنزيل بحجم 8.6 GB من Zenodo؛
يلزم نحو 10 GB من المساحة الحرة). ولا حاجة إلى صلاحيات المسؤول.

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/heads/main.zip
phasentic setup
```

macOS وLinux:

```bash
curl -LsSf https://raw.githubusercontent.com/qaemu/phasentic/main/install.sh | sh
```

وعلى Windows يضيف أيضًا اختصار **Phasentic** إلى سطح المكتب وقائمة ابدأ، ويفتح Phasentic في نافذته الخاصة.
وعلى macOS يُضاف إلى مجلد التطبيقات، وعلى Linux إلى قائمة التطبيقات. وإذا انقطع التنزيل، شغّل الأمر نفسه مرة أخرى فيستأنف من حيث توقف.

### استخدام POW_COD بدلًا من ذلك

إذا كانت لديك **POW_COD 2205 (FULL)** من
[صفحة التنزيل لدى CNR](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/)،
فثبّتها بالأمر أدناه؛ وعندها يستخدمها Phasentic بدلًا من قاعدة COD. وقد قيست أرقام الدقة المنشورة باستخدام POW_COD.

```bash
phasentic setup-powcod ~/Downloads/powcod-2205.zip
```

<a name="quick-start"></a>

## البدء السريع

افتح Phasentic من اختصاره، أو شغّل &lrm;`phasentic-app`. ولاستخدامه في المتصفح بدلًا من ذلك، شغّل الأمر أدناه وافتح <http://127.0.0.1:8000>:

```bash
phasentic serve
```

اختر مسحًا، واكتب صيغ السلائف والصيغ المستهدفة، وأبقِ خيار *Validated method* (الطريقة المُتحقَّق منها)
محددًا (وهو الخيار الافتراضي)، ثم اضغط *Analyze* (تحليل). يُنتج *Download report* (تنزيل التقرير) تقريرًا
من صفحتين قابلًا للطباعة (مخطط المطابقة، والأدلة لكل طور، والفرضيات المنافسة، والطريقة
وقابلية التتبّع) يمكن حفظه بصيغة PDF؛ ويُنتج *JSON* السجلّ الكامل القابل للقراءة آليًا.

ومن سطر الأوامر، الطريقة المُتحقَّق منها نفسها:

```bash
phasentic analyze scan.xrdml --preset validated --chemistry "Ag2O BaCO3 Ba2Ag2C2O7" --output report.json
```

يقصر الخيار &lrm;`--chemistry` المرشّحات على عناصر تلك الصيغ إضافةً إلى H وC
وO (الكربونات والهيدروكسيدات والهيدرات). ومن دون &lrm;`--preset`، يمكن ضبط كل إعدادات
التحليل عبر الخيارات (`phasentic analyze --help`)؛ وتلك التوليفات
غير مُتحقَّق منها.

ويتطلب القرار `supported` إضافةً إلى ذلك معايرةً لمواقع الخطوط باستخدام
مسح لمادة معيارية (السيليكون NIST SRM 640g افتراضيًا): `phasentic calibrate standard.xy`.

## متى لا ينبغي استخدامه

- **لإثبات وجود طور ما.** النتائج فرضيات مرتّبة ينبغي أن يؤكدها
  باحث، ويُفضَّل أن يكون ذلك بتنقيح Rietveld.
- **لتقدير نسب الأطوار.** معاملات المقياس في المطابقة سعات للفرز الأولي، وليست
  نسبًا مئوية وزنية.
- **للعيّنات التي تضم ثلاثة أطوار أو أكثر**، إذ لم يتعرّف فيها على جميع المركّبات
  إلا في 13% من الحالات خلال الاختبار.
- **للأطوار الثانوية أو ضعيفة التشتت** (مثل أملاح Li أو B أو K المجاورة
  لأطوار تحوي عناصر ثقيلة)، والتي كثيرًا ما يفوتها.
- **من دون كيمياء العيّنة أو مع مصاعد (أنودات) غير Cu**، إذ لم تكن
  جزءًا من التحقق.

## آلية العمل

1. استيراد المسح، وتقدير الخلفية، وكشف القمم (مع مراعاة الضجيج).
2. استرجاع المرشّحين من POW_COD، مقصورين على عناصر العيّنة.
3. مطابقة مخاليط غير سالبة من أنماط الحيود المرجعية باستخدام بحث حزمي (beam search) محدود،
   وإعادة الاستعلام بالمتبقيات، وتبديل الأطوار؛ ثم استبعاد الأطوار التي تغيب خطوطها القوية
   عن المسح.
4. ترتيب الفرضيات، والإبلاغ عن الالتباس، وتسجيل المصدر (قيمة تجزئة المُدخل،
   والإعدادات، وهوية قاعدة البيانات، وإصدارات الخوارزميات).

التفاصيل: [docs/scientific-method.md](../docs/scientific-method.md) و
[PARAMETERS.md](../PARAMETERS.md).

## الاستشهاد

إذا أسهم Phasentic في عملك، فاستشهد بالإصدار الذي استخدمته. يوفّر زر
*Cite this repository* في GitHub (المستند إلى [CITATION.cff](../CITATION.cff)) صيغتي APA
وBibTeX. واستشهد أيضًا بـ POW_COD وبـ Crystallography Open Database.

## الرخصة

الشيفرة مرخّصة بموجب رخصة MIT. أما بيانات POW_COD وCOD وPrecursor Genome فتُوزَّع وفق
شروطها الخاصة، وليست مُضمَّنة في هذا المستودع.
