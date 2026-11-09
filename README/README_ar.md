<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/wordmark-dark.svg">
    <img src="../assets/wordmark-light.svg" alt="phasentic" width="360">
  </picture>
</p>

<p align="center">
  تعرّف الأطوار بحيود الأشعة السينية على المساحيق بطريقة مُتحقَّق منها وقابلة لإعادة الإنتاج.
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

يقرأ Phasentic مسحًا لحيود المسحوق (`.xy` أو `.xrdml` أو `.raw` بصيغة ASCII)،
ويكشف القمم، ويبحث في قاعدة بيانات مرجعية مبنية على
[Crystallography Open Database](https://www.crystallography.net/cod/) (أو [POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/) من CNR)،
ويطابق خلائط تصل إلى خمسة أطوار. ويُرجع فرضيات أطوار مرتَّبة، ويسجّل كل
الإعدادات والبصمات والتحذيرات في تقرير JSON. ويعمل محليًا، في المتصفح أو من
سطر الأوامر.

<p align="center">
  <img src="../docs/images/interface.png" alt="واجهة Phasentic: نتيجة مبدئية لـ ZrO2 مع مخطط المطابقة والفرضيات المنافسة والبدائل لكل طور" width="900">
  <br>
  <sub>مسح تطويري من مجموعة بيانات Precursor Genome (PG_2452، Cu Kα)، اختير عشوائيًا. يختار Phasentic الطور ZrO₂. ويتضمن الوسم المرجعي المنقَّح يدويًا طورين ثانويين آخرين: LiOH·H₂O الذي يظهر فقط ضمن الفرضيات المنافسة (ZrO₂ + LiH₃O₂)، وLi₂CO₃ الذي يفوته هذا التشغيل.</sub>
</p>

<a name="how-accurate-is-it"></a>
## ما مدى دقته

ضُبطت الإعدادات على 485 مسحًا من Precursor Genome (وسوم منقَّحة يدويًا)، ثم
شُغِّلت على 200 مسح مقفل لم يرها الضبط قط، باستخدام قاعدة البيانات
PXRD_COD 2026.11 (المشتقة من COD مع إضافة من Materials Project). ويُحسب الامتناع
عن الإجابة إخفاقًا.

| المستوى | الصحيح | النسبة |
|---|---|---|
| المركّبات والبنى البلورية الصحيحة (صارم) | 85 / 200 | 42.5% |
| المركّبات الصحيحة، بأي متعدد أشكال (عائلة) | 104 / 200 | 52.0% |

هذا هو التشغيل الثاني على هذه المسوح الـ200. استخدم الأول (72 و99) قاعدة COD
وحدها؛ أما إضافة قاعدة البيانات، والصيغ التي استُعيد فيها الهيدروجين، وتفضيل
الوصف الأعلى تناظرًا للمادة، فقد طُوِّرت على مسوح الضبط الـ485 وحدها. وحققت
الطريقة غير المضبوطة 71 و96. تنطبق هذه الأرقام على الإعداد المسبق المُتحقَّق
منه مع PXRD_COD 2026.11 وCu Kα وكيمياء السلائف في العينة؛ والإعدادات الأخرى غير
مختبرة.

<a name="install"></a>
## التثبيت

يثبّت الإعداد Python 3.12 وPhasentic وقاعدة بياناته المرجعية (تنزيل بحجم
8.6 غيغابايت من Zenodo؛ احرص على توفر نحو 10 غيغابايت). لا حاجة إلى صلاحيات
المدير.

Windows: الصق هذه الأسطر الأربعة في PowerShell (السطر الأول هو المثبّت الرسمي لـ
[uv](https://docs.astral.sh/uv/)، الذي يثبّت Python):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/tags/v1.0.0.zip
phasentic setup
```

macOS وLinux:

```bash
curl -LsSf https://raw.githubusercontent.com/qaemu/phasentic/v1.0.0/install.sh | sh
```

على Windows يُنزّل `phasentic setup` قاعدة البيانات، ويضيف اختصار **Phasentic**
إلى سطح المكتب وقائمة ابدأ، ويفتح Phasentic في نافذته الخاصة؛ أغلق Phasentic قبل
إعادة التثبيت. وعلى macOS يضيف المثبّت Phasentic إلى التطبيقات، وعلى Linux إلى
قائمة التطبيقات. إذا انقطع التنزيل فأعد تشغيل الأوامر نفسها؛ فهو يستأنف من حيث
توقف.

### استخدام POW_COD بدلًا منها

إن كانت لديك **POW_COD 2205 (FULL)** من
[صفحة التنزيل في CNR](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/)،
فثبّتها بالأمر أدناه؛ وسيستخدمها Phasentic بدلًا من قاعدة COD. وقد قيست أرقام
الدقة المنشورة بقاعدة COD، لا بـ POW_COD.

```bash
phasentic setup-powcod ~/Downloads/powcod-2205.zip
```

<a name="quick-start"></a>
## البدء السريع

افتح Phasentic من اختصاره، أو شغّل `phasentic-app`. ولاستخدامه في متصفح، شغّل
الأمر أدناه وافتح <http://127.0.0.1:8000>:

```bash
phasentic serve
```

أفلت ملف مسح على النافذة (أو اختره)، واكتب صيغ السلائف والمنتجات المستهدفة، ثم
اضغط *Analyze*. مع الصيغ وCu Kα تُستخدم الطريقة المُتحقَّق منها؛ ويمكن تغيير
تفاوت القمم والحد الأقصى للأطوار من *Search settings*، والقيم الأخرى غير
مُتحقَّق منها. يحفظ *PDF* تقريرًا بسيطًا بالقيم المقيسة والمحسوبة؛ ويفتح *Formal
report* تقريرًا قابلًا للطباعة (مخطط المطابقة، والأدلة لكل طور، والفرضيات
المنافسة، والطريقة وإمكانية التتبع)؛ ويقدّم *CIF* و*JSON* البيانات. الواجهة
متاحة بالإنجليزية والإسبانية.

من سطر الأوامر، الطريقة المُتحقَّق منها نفسها:

```bash
phasentic analyze scan.xrdml --preset validated --chemistry "Ag2O BaCO3 Ba2Ag2C2O7" --output report.json
```

يقصر `--chemistry` المرشّحين على عناصر تلك الصيغ إضافةً إلى H وC وO (الكربونات
والهيدروكسيدات والهيدرات). ومن دون `--preset` يمكن ضبط كل إعداد للتحليل عبر
الخيارات (`phasentic analyze --help`)؛ وهذه التوليفات غير مُتحقَّق منها.

النتائج في أقصاها `tentative` (أو `ambiguous` / `unresolved`): فالقرار
`supported` يتطلب معايرة مرفقة لمواضع الخطوط، وهو ما لا يوفّره هذا الإصدار. ولا
يزال `phasentic calibrate standard.xy` يفحص مواضع خطوط الجهاز باستخدام مسح معياري
(السيليكون NIST SRM 640g افتراضيًا).

## متى لا تستخدمه

- **لتقدير نسب الأطوار.** معاملات المقياس في المطابقة سعات للفرز، لا نسب
  مئوية وزنية.
- **للعينات ذات ثلاثة أطوار أو أكثر**، إذ لم يتعرّف على جميع المركّبات إلا في
  11% من الحالات في الاختبار.
- **للأطوار الثانوية أو ضعيفة التشتت** (مثل أملاح Li أو B أو K بجوار أطوار
  العناصر الثقيلة)، التي كثيرًا ما يفوتها.

## كيف يعمل

1. يستورد المسح، ويقدّر الخلفية، ويكشف القمم (مع مراعاة الضوضاء).
2. يسترجع المرشّحين من قاعدة البيانات المرجعية، مقصورين على عناصر العينة.
3. يطابق خلائط غير سالبة من المقاطع المرجعية ببحث شعاعي محدود، مع إعادة
   الاستعلام على المتبقي وتبديل الأطوار؛ ويستبعد الأطوار التي تغيب خطوطها
   القوية عن المسح.
4. يرتّب الفرضيات، ويبلّغ عن الالتباس، ويسجّل المصدر (بصمة المُدخل، والإعدادات،
   وهوية قاعدة البيانات، وإصدارات الخوارزميات).

التفاصيل: [docs/scientific-method.md](../docs/scientific-method.md) و
[PARAMETERS.md](../PARAMETERS.md).

## الاستشهاد

إذا أسهم Phasentic في عملك فاستشهد بالإصدار الذي استخدمته. يوفّر زر *Cite this
repository* في GitHub (من [CITATION.cff](../CITATION.cff)) صيغتي APA وBibTeX.
واستشهد أيضًا بقاعدة البيانات المرجعية
[PXRD_COD 2026.11](https://doi.org/10.5281/zenodo.24059658) وبمصادرها:
Crystallography Open Database وMaterials Project (وPOW_COD إن استخدمتها بدلًا
منها).

## الرخصة

الشيفرة مرخّصة بموجب رخصة MIT. وقاعدة البيانات المرجعية مرخّصة بموجب CC BY 4.0
(بيانات COD بموجب CC0، وبيانات Materials Project بموجب CC BY 4.0). أما بيانات
POW_COD وPrecursor Genome فتُوزَّع وفق شروطها الخاصة، وليست مُضمَّنة في هذا
المستودع.
