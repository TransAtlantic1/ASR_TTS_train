# Jellycat 广义非语音标签扫描报告

- 生成时间: `2026-05-27 07:23:38 UTC`
- 扫描脚本: `/tmp/jellycat_scan_non_speech_tags.py`
- 输入: 当前 Jellycat `*_supervisions.jsonl.gz`，即 ASR 训练/数据准备会使用的 supervision；同时扫描 `*_rejected.jsonl.gz`，用于统计已经被旧纯标签规则过滤掉的数据时长。
- 详细 JSON: `/tmp/jellycat_broad_non_speech_tag_scan.json`

## 匹配口径

- `current pure square`: 现有源码里的精确规则，`^(?:\[[^\[\]]+\]\s*)+$`，只匹配整条文本完全由英文方括号标签组成的样本。
- `any bracket span`: 任意括号片段，覆盖 `[]`、`【】`、`()`、`（）`、`<>`、`{}`，单个片段最长 120 字符。
- `keyword tag`: 括号片段或整条裸标签中包含非语音关键词，例如 `lyrics`、`music`、`applause`、`laughter`、`noise`、`silence`、`inaudible`、`speech`、`cough/breath`、`beep/buzzer`，以及对应的简繁中文表达。
- `pure broad tag`: 整条文本只由括号片段组成，并且命中现有 pure-square 规则或包含非语音关键词。
- 时长统计口径: 汇总列中每条命中样本只累计一次完整 supervision/record 时长；分类表中每个类别各自累计一次。如果同一条样本命中多个类别，各类别小时数之和可能大于总 keyword-tag 小时数。
- 这些数字本身是检测统计。基于当前损失量很小，本文后续采用一个更务实的第一版清洗策略：直接 hard reject 所有包含括号片段的样本，不再先做复杂人工归类。

## 已被现有源码策略过滤的样本

| 语言 | summary 中 rejected_non_speech_tag | rejected manifest 扫描条数 | rejected manifest 扫描小时数 |
| --- | --- | --- | --- |
| EN | 1,353,476 | 1,353,476 | 4,360.73 |
| ZH | 1,227,296 | 1,227,296 | 3,854.09 |

## 当前 Supervision 残留汇总

| 语言 | 总条数 | 总小时数 | 任意括号片段 条数/小时 | 关键词标签 条数/小时 | 整条为广义标签 条数/小时 | 裸关键词标签 条数/小时 | 当前纯 `[tag]` 条数/小时 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ZH | 26,694,858 | 111,076.45 | 387,995 / 1,050.06h (1.453% rec; 0.945% hrs) | 374,510 / 943.01h (1.403% rec; 0.849% hrs) | 0 / 0.00h (0.000% rec; 0.000% hrs) | 211 / 0.09h (0.001% rec; 0.000% hrs) | 0 / 0.00h (0.000% rec; 0.000% hrs) |
| EN | 25,066,305 | 86,364.06 | 135,682 / 225.38h (0.541% rec; 0.261% hrs) | 136,828 / 219.39h (0.546% rec; 0.254% hrs) | 2 / 0.00h (0.000% rec; 0.000% hrs) | 2,939 / 0.88h (0.012% rec; 0.001% hrs) | 0 / 0.00h (0.000% rec; 0.000% hrs) |

## ZH

- 输入: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_supervisions.jsonl.gz`
- 总条数: `26,694,858`; 总小时数: `111,076.45`.
- 残留关键词标签数据: `374,510` 条 / `943.01` 小时。
- 残留整条为广义标签的数据: `0` 条 / `0.00` 小时。

### 括号片段类型

| 括号类型 | 条数 | 小时数 | 出现次数 |
| --- | --- | --- | --- |
| square | 374,425 | 944.54 | 376,607 |
| full_square | 0 | 0.00 | 0 |
| paren | 9 | 0.05 | 9 |
| full_paren | 13,562 | 105.48 | 18,672 |
| angle | 0 | 0.00 | 0 |
| brace | 1 | 0.01 | 4 |

### 关键词类别

| 类别 | 条数 | 小时数 | 出现次数 |
| --- | --- | --- | --- |
| applause（掌声/鼓掌） | 326 | 2.23 | 364 |
| beep（蜂鸣/提示音/铃声） | 210 | 0.78 | 249 |
| inaudible（听不清/不可辨） | 41 | 0.04 | 41 |
| laughter（笑声） | 3,852 | 18.18 | 5,293 |
| lyrics（歌词/唱词） | 368,266 | 917.12 | 368,334 |
| music（音乐/歌唱） | 1,511 | 3.85 | 1,581 |
| noise（噪声/音效） | 362 | 1.69 | 496 |
| silence（静音/停顿） | 17 | 0.05 | 20 |
| speech_marker（语音/人声标记） | 77 | 0.44 | 78 |
| vocal_noise（咳嗽/呼吸等人声噪声） | 182 | 0.90 | 211 |

### 高频原始括号标签

| 原始标签 | 出现次数 | 记录比例分母 |
| --- | --- | --- |
| `[Lyric]` | 368,333 | 26,694,858 |
| `[Laughter]` | 3,901 | 26,694,858 |
| `[Music]` | 1,470 | 26,694,858 |
| `[观众笑声]` | 760 | 26,694,858 |
| `[Noise]` | 330 | 26,694,858 |
| `（笑）` | 204 | 26,694,858 |
| `[Beep]` | 178 | 26,694,858 |
| `（括号）` | 177 | 26,694,858 |
| `[Applause]` | 168 | 26,694,858 |
| `（笑声）` | 120 | 26,694,858 |
| `（括弧）` | 112 | 26,694,858 |
| `（AI）` | 76 | 26,694,858 |
| `[观众笑声、鼓掌]` | 73 | 26,694,858 |
| `（LLMs）` | 68 | 26,694,858 |
| `[Cough]` | 61 | 26,694,858 |
| `[Buzzer]` | 58 | 26,694,858 |
| `（已完成）` | 50 | 26,694,858 |
| `[眾人笑聲]` | 43 | 26,694,858 |
| `[观众笑声、鼓掌声]` | 42 | 26,694,858 |
| `（LLM）` | 32 | 26,694,858 |
| `（ACA）` | 31 | 26,694,858 |
| `（包含新屋以及中古屋）` | 29 | 26,694,858 |
| `（CECC）` | 29 | 26,694,858 |
| `（CNN）` | 28 | 26,694,858 |
| `（True Anomaly）` | 28 | 26,694,858 |
| `（Anduril）` | 28 | 26,694,858 |
| `（含预售）` | 27 | 26,694,858 |
| `（非常六）` | 27 | 26,694,858 |
| `[Speech]` | 26 | 26,694,858 |
| `（Alayhi Salam）` | 26 | 26,694,858 |

### 高频归一化括号内容

| 归一化内容 | 出现次数 | 记录比例分母 |
| --- | --- | --- |
| `lyric` | 368,333 | 26,694,858 |
| `laughter` | 3,905 | 26,694,858 |
| `music` | 1,470 | 26,694,858 |
| `观众笑声` | 765 | 26,694,858 |
| `noise` | 330 | 26,694,858 |
| `笑` | 205 | 26,694,858 |
| `beep` | 178 | 26,694,858 |
| `括号` | 178 | 26,694,858 |
| `applause` | 168 | 26,694,858 |
| `笑声` | 120 | 26,694,858 |
| `括弧` | 112 | 26,694,858 |
| `ai` | 76 | 26,694,858 |
| `观众笑声、鼓掌` | 73 | 26,694,858 |
| `llms` | 68 | 26,694,858 |
| `cough` | 63 | 26,694,858 |
| `buzzer` | 58 | 26,694,858 |
| `已完成` | 50 | 26,694,858 |
| `眾人笑聲` | 43 | 26,694,858 |
| `观众笑声、鼓掌声` | 42 | 26,694,858 |
| `alayhi salam` | 39 | 26,694,858 |
| `llm` | 33 | 26,694,858 |
| `aca` | 31 | 26,694,858 |
| `包含新屋以及中古屋` | 29 | 26,694,858 |
| `cecc` | 29 | 26,694,858 |
| `cnn` | 28 | 26,694,858 |
| `true anomaly` | 28 | 26,694,858 |
| `anduril` | 28 | 26,694,858 |
| `含预售` | 27 | 26,694,858 |
| `非常六` | 27 | 26,694,858 |
| `sallallahu alayhi wa sallam` | 26 | 26,694,858 |

### 示例

#### 已过滤的 non_speech_tag 示例

- `zh_e17b4aea3023_00_00129` dur=13.38 text=`[Speech]`
- `zh_703dea53e926_00_00084` dur=10.66 text=`[Music]`
- `zh_1f8252328a0c_01_00032` dur=2.2 text=`[Music]`
- `zh_1f8252328a0c_01_00284` dur=9.02 text=`[Music]`
- `zh_a87d4d182304_00_00002` dur=2.69 text=`[Music]`

#### applause（掌声/鼓掌）

- `ZH_P000490_S00031_W00000002` dur=9.4 tag=`[Applause]` text=`[Music][Applause][Music]也差不多了。`
- `ZH_P003048_S00254_W00000003` dur=28.56 tag=`[Applause]` text=`下班了聊一聊，下班和你聊，跟網友大家晚安。今天跟大家一起聊的是前副總統呂秀蓮。[Applause]來，我們下半天進學寶。\n副總統好，各位觀眾朋友大家好，大家好。\n好，我們節目其實多次邀訪呂副總統來以後，那這個網友的反應都很好。\n對。\n因為副總統總是可以在这个喧擾的政治攻防議題當中呢，拉高那個高度，讓我們看到一些形勢。\n對。`
- `ZH_P003644_S00246_W00000002` dur=13.78 tag=`[Applause]` text=`请您欣赏：\n[Applause]\n酒罢风霜`
- `ZH_P004374_S00013_W00000054` dur=14.11 tag=`[Applause]` text=`麻吉哥掰的比，嘿嘿嘿嘿，你瞧瞧这，啊，这要现形儿这是，皇上驾到！[Applause]怎么没人找你演这个戏呢？`
- `ZH_P004374_S00045_W00000159` dur=32.63 tag=`[观众笑声、鼓掌声]` text=`你...啊，对不起，哎呀，大不敬了，说你们家祖先了，对不起。[观众笑声、鼓掌声]啊，人家家随葬品都是金财宝，我们家随葬品是吹风机。\n不是，你要说什么呀？\n朱元璋。\n谁呀？\n我。\n你，你说你，你想说你老祖先是朱元璋？\n对了。\n啊。\n到了南京有一个明孝陵，知道吗？\n知道知道。\n那个是国家级的文物单位。\n啊，对对对。\n那埋着多少宝贝呀？\n啊。\n那是我们老朱家人不愿意下去挖去。\n那下去挖去呢？`

#### beep（蜂鸣/提示音/铃声）

- `ZH_P000797_S00001_W00000020` dur=2.65 tag=`[Buzzer]` text=`interview Yeah, okay. [Buzzer] interview`
- `ZH_P000817_S00024_W00000039` dur=15.02 tag=`[電話鈴聲]` text=`係啊係啊係啊，即係如果呢個...我我我經歷過圓圈...即係如果呢個電話，即係如果呢個電話係六九九幾嗰啲啊，你會... [電話鈴聲] ...係啦。我六個號碼。你記唔記得你以前...幾號嘅？六一六七五一一。`
- `ZH_P001330_S00033_W00000000` dur=14.13 tag=`[Beep]` text=`[Beep]開講，這邊東，第1585集。這集的節目，大家平安，我是吳志強博士。但這集要同各位李鴻基博士，說下，套炸艾靈修。`
- `ZH_P001330_S00345_W00000000` dur=13.3 tag=`[Beep]` text=`[Beep]海港這邊東，這幾千能吧，直接打擊。這下節目，大家平安，我是我自個無數。那只是被同歸，路卡多無數，說下穩定的時刻。`
- `ZH_P001330_S00345_W00000028` dur=10.31 tag=`[Beep]` text=`[Beep]這種婉轉無敢看，會改水，就學因的相對病情，得到憐憫，得到相對本心，聽的安慰。`

#### inaudible（听不清/不可辨）

- `ZH_P000042_S00011_W00000026` dur=1.01 tag=`` text=`听不见。`
- `ZH_P000599_S00051_W00000062` dur=0.78 tag=`` text=`听不懂`
- `ZH_P001025_S00097_W00000254` dur=1.08 tag=`` text=`听不懂。`
- `ZH_P006240_S00010_W00000205` dur=2.27 tag=`` text=`不清楚。`
- `ZH_P000729_S00029_W00000024` dur=1.26 tag=`` text=`听不懂`

#### laughter（笑声）

- `ZH_P000072_S00003_W00000009` dur=14.96 tag=`[Laughter]` text=`Ya so ba. Ya so. [Laughter]哎，我們會不會，我沒有任何歧視別什麼宗教的意思。Jesus Christ. 對嗎？是嗎？是耶穌的意思嗎？我也忘記是耶穌誕辰紀念還是什麼。`
- `ZH_P000090_S00042_W00000058` dur=27.66 tag=`[Laughter]` text=`所以你就可以直接講了。又Q到又Q到。元同學那天，我們已經去完夜店之後，回民宿休息的時候，他還跟我分享一個故事。他說他在那個沙丁魚的狀態的時候，超想吐，但是他來不及去廁所，所以他做了一個行為。有看畫面看畫面，沒看畫面聽我敘述。拿出你的手，然後把它稍微拱起來，像要捧東西，但就單隻手喔。OK OK。吐在上面。[Gagging Sound]手有點抓住，看一下旁邊。[Laughter]往旁邊甩。`
- `ZH_P000179_S00017_W00000019` dur=4.84 tag=`[Laughter]` text=`Bom. Bom. [Laughter]`
- `ZH_P000232_S00030_W00000086` dur=3.26 tag=`[Laughter]` text=`很合理吧。[Laughter] Yeah.`
- `ZH_P000240_S00098_W00000016` dur=2.52 tag=`[Laughter]` text=`Okay. [Laughter]`

#### lyrics（歌词/唱词）

- `ZH_P000000_S00017_W00000000` dur=13.4 tag=`[Lyric]` text=`[Lyric] Oh oh oh let's go 走心兄弟 Oh oh oh let's go 走心兄弟 感情的狂潮`
- `ZH_P000000_S00054_W01000076` dur=16.71 tag=`[Lyric]` text=`[Lyric] Baby tonight, hey, let's get high, hey, dancing all night, hey, party time, hey, 拉到心中心包，就拋開所有煩惱，丟掉你的歐寶，再跟我跳一跳，嘿，別害羞。`
- `ZH_P000000_S00098_W02000057` dur=3.11 tag=`[Lyric]` text=`[Lyric] 他扬起动力，亮的剧本。`
- `ZH_P000000_S00205_W00000127` dur=12.94 tag=`[Lyric]` text=`[Lyric] 拿掉心中城堡 就抛开所有烦恼 丢掉你的欧宝 再跟我跳一跳 嘿 别害羞 别小音点的节奏 一起为韩江加油`
- `ZH_P000000_S00318_W00000018` dur=10.43 tag=`[Lyric]` text=`[Lyric] 然后打线的话，如果魔音他是有在个人的社群平台说他礼拜三的时候想要归队。`

#### music（音乐/歌唱）

- `ZH_P000000_S00181_W00000000` dur=24.75 tag=`[Music]` text=`[Music]阿肯好，幫友，打野後備，又你好，我是阿肯，副幫將，我有幫助。\n這禮拜哦，去看了新的電影哦，那個動物方程式的第二集上映了。`
- `ZH_P000035_S00008_W00000344` dur=1.06 tag=`[Music]` text=`Okay. [Music]`
- `ZH_P000047_S00241_W00000217` dur=1.08 tag=`` text=`音乐`
- `ZH_P000246_S00004_W00000000` dur=29.0 tag=`[Humming]` text=`我進去裡面。可以啊，你就在。在我上面那裡面啊。認真。對。這樣才是最佳。這樣才是對，最佳對談的對談的那個角度。對，最佳對話狀態。好生氣哦。好。[Humming]人家很多探大集的開場樂太爽了吧。越來越。我們還在找我們要用的開頭音樂。沒錯。`
- `ZH_P000248_S00013_W00000015` dur=24.06 tag=`[Music]` text=`[Music]大嘴鼓给好朋友来，就是我们的林胜志，胜志你好。Hello，观众朋友大家好，哦，听众朋友大家好。哎，我们走，我们走。对对对。哎，给没有来，你就会好好来共一下，给条路啦。条前糖豆，你做这个啥，我就只有联想到一件事情，肚子饿。哎，对。应该蛮鲜明是跟食物有关吼。哎，就东西吃嘞。[Laughter]`

#### noise（噪声/音效）

- `ZH_P000090_S00042_W00000058` dur=27.66 tag=`[Gagging Sound]` text=`所以你就可以直接講了。又Q到又Q到。元同學那天，我們已經去完夜店之後，回民宿休息的時候，他還跟我分享一個故事。他說他在那個沙丁魚的狀態的時候，超想吐，但是他來不及去廁所，所以他做了一個行為。有看畫面看畫面，沒看畫面聽我敘述。拿出你的手，然後把它稍微拱起來，像要捧東西，但就單隻手喔。OK OK。吐在上面。[Gagging Sound]手有點抓住，看一下旁邊。[Laughter]往旁邊甩。`
- `ZH_P000478_S00025_W00000027` dur=38.66 tag=`[Noise]` text=`[Noise] 所以我來解釋一下，因為三甲中好鹽喔，即個周樹公廟喔，伊是又著在地的即個大藝術家李梅樹教授，伊來監督要來去即根廟。[Noise] 啊即根廟的樹非常古，啊即個重修的時陣，李梅樹教授因為伊是當地人，伊就住廟邊喔，所以伊真註定即根是廟，所以伊就主編來甲伊監工。[Noise] 因為啊，即個廟內底非常最大意的兩條。[Noise] 啊伊就想講，啊龍去趕快的兩條，安尼無意思喔，藝術家的樹伊甲咱無敢換喔，所以伊就甲你猜度，叫即個就調的工人`
- `ZH_P000478_S00025_W00000027` dur=38.66 tag=`[Noise]` text=`[Noise] 所以我來解釋一下，因為三甲中好鹽喔，即個周樹公廟喔，伊是又著在地的即個大藝術家李梅樹教授，伊來監督要來去即根廟。[Noise] 啊即根廟的樹非常古，啊即個重修的時陣，李梅樹教授因為伊是當地人，伊就住廟邊喔，所以伊真註定即根是廟，所以伊就主編來甲伊監工。[Noise] 因為啊，即個廟內底非常最大意的兩條。[Noise] 啊伊就想講，啊龍去趕快的兩條，安尼無意思喔，藝術家的樹伊甲咱無敢換喔，所以伊就甲你猜度，叫即個就調的工人`
- `ZH_P000478_S00025_W00000027` dur=38.66 tag=`[Noise]` text=`[Noise] 所以我來解釋一下，因為三甲中好鹽喔，即個周樹公廟喔，伊是又著在地的即個大藝術家李梅樹教授，伊來監督要來去即根廟。[Noise] 啊即根廟的樹非常古，啊即個重修的時陣，李梅樹教授因為伊是當地人，伊就住廟邊喔，所以伊真註定即根是廟，所以伊就主編來甲伊監工。[Noise] 因為啊，即個廟內底非常最大意的兩條。[Noise] 啊伊就想講，啊龍去趕快的兩條，安尼無意思喔，藝術家的樹伊甲咱無敢換喔，所以伊就甲你猜度，叫即個就調的工人`
- `ZH_P000478_S00025_W00000027` dur=38.66 tag=`[Noise]` text=`[Noise] 所以我來解釋一下，因為三甲中好鹽喔，即個周樹公廟喔，伊是又著在地的即個大藝術家李梅樹教授，伊來監督要來去即根廟。[Noise] 啊即根廟的樹非常古，啊即個重修的時陣，李梅樹教授因為伊是當地人，伊就住廟邊喔，所以伊真註定即根是廟，所以伊就主編來甲伊監工。[Noise] 因為啊，即個廟內底非常最大意的兩條。[Noise] 啊伊就想講，啊龍去趕快的兩條，安尼無意思喔，藝術家的樹伊甲咱無敢換喔，所以伊就甲你猜度，叫即個就調的工人`

#### silence（静音/停顿）

- `ZH_P001733_S00546_W00000002` dur=9.69 tag=`[Silence]` text=`[Silence]你哋搞霸凌啊，但係我自己最欣賞自己就係，佢佢佢霸凌咗我兩年，我仲留喺嗰度，所以算係過去嗰段最艱難捱嘅時期。`
- `ZH_P002122_S00027_W00000040` dur=39.33 tag=`（上括弧停顿下括弧）` text=`现在，我们将结束口授，给我们一会儿（上括弧停顿下括弧）。Alpha层面是未区分的。照你所要的，你可以用那儿的能量。它是源头或水塘，在那儿能量的库场存以备用。被拉在较内的自己与外在的自己之间。人格的较深层面的符号与预兆进入到了这个区域。因它处于这样的境地，它在操纵实质的有机体上又有一些特别的用处，如你们正学到的，自发性在此极端的重要。`
- `ZH_P006202_S00018_W00000002` dur=5.74 tag=`[Silence]` text=`[Silence]咁呢而家呢就試下對住塊鏡，我喺呢度錄啲乜嘢喎。`
- `ZH_P006892_S00003_W00000080` dur=13.05 tag=`（吸了一口烟，沉默了一会儿）` text=`我那时是个绝对的苏联人，对于爱钱感到羞愧，执着于自己的梦想（吸了一口烟，沉默了一会儿），真让人遗憾，我们忘了很多东西，因为事情出现得太快。`
- `ZH_P001400_S00077_W00000001` dur=19.58 tag=`[Silence]` text=`[Silence] [Silence] [Silence] [Silence]好，各位好啊，咁我好耐冇參與過呢個劇透啊，歡迎大家呢再一次呢參與我哋神學樹洞嘅劇透。咁今日呢，即係啊好開心啊，當然我哋嘅台柱啊，Ivan喺度啦，咁而另外呢...`

#### speech_marker（语音/人声标记）

- `ZH_P000288_S00007_W00000001` dur=39.5 tag=`（human in the loop）` text=`现实情况更为复杂。尽管 AI 可以高效生成内容，但关键的人工在环（human in the loop）验证环节却意外地成为了一个巨大的瓶颈。法规专家必须逐字逐句地审查 AI 生成的所有内容，这并非简单的浏览，而是深入的验证过程，需要核实事实的准确性、整个文档内部逻辑的一致性，以及 AI 可能会忽略的法规语言中的微妙之处。例如，AI 可能无法完全理解某个 FDA 审评员对特定比对器械所要求的独特解释角度。目前来看，这种人工监督是不可或缺的`
- `ZH_P006993_S00019_W00000065` dur=1.52 tag=`` text=`human`
- `ZH_P000833_S00051_W00000023` dur=38.13 tag=`（human existence）` text=`正是这同一种寻求摆脱地球监禁的渴望，让人们尝试在试管中创造生命，尝试将取自确证具有优越能力的人的生殖细胞在显微镜下进行混合以培育超人，并修改其身量、形体和功能。这种摆脱人的条件的限制的愿望，我猜想，同样潜藏在将人类寿命延长至远超百年极限的希冀之中。科学家告诉我们，这种未来人将在不超过一百年的时间里诞生，它似乎被一种对既定的人类存在状态（human existence）的反抗所附体，渴望将其置换换成自己亲手创造之物，而不能再是不知从哪里来`
- `ZH_P001028_S00007_W00000063` dur=9.18 tag=`（Voice of the People）` text=`那个广播节目叫做人民之声（Voice of the People），就是一个让听众call in进去自由发泄、抱怨的节目。`
- `ZH_P001553_S00001_W00000022` dur=21.43 tag=`[Speech]` text=`在忍者屋的屋頂上還有一隻綠色大妖怪耶。這個很像鱷魚。哈哈，蠻像的。嗚，別忘了來玩這一项，旋轉木馬超人氣！[Speech]但是長得很像馬的一些妖怪。對。`

#### vocal_noise（咳嗽/呼吸等人声噪声）

- `ZH_P000148_S00090_W00000121` dur=1.78 tag=`` text=`Sigh`
- `ZH_P001749_S00025_W00000108` dur=24.82 tag=`[Cough]` text=`你再繼續打我，我叫我爸爸來打你。我叫我爸爸來打你。他甚至不是覺得自己做錯，他覺得男生就是可以打女生。\n嗯嗯，對對，我覺得會複製到這樣子的習慣。美國同齡也演過這一段。嗯。要先倒樂色嗎？好，先倒樂色。啊。好。Okay, show. [Cough]這個會剪進去。`
- `ZH_P003048_S00025_W00000063` dur=0.98 tag=`` text=`cough`
- `ZH_P005120_S00008_W00000029` dur=14.63 tag=`[Kiss Sound]` text=`别的我还真不知道，但是我就记得啊，当时我们的那个女老师给我们讲这个生理卫生知识健康的时候，说过这么一句话，说，每个人都有机会发生[Kiss Sound]嗯，行为。`
- `ZH_P007213_S00141_W00000027` dur=1.92 tag=`` text=`呼吸`

#### 裸关键词标签示例

- `ZH_P000042_S00011_W00000026` dur=1.01 text=`听不见。`
- `ZH_P000047_S00241_W00000217` dur=1.08 text=`音乐`
- `ZH_P000148_S00090_W00000121` dur=1.78 text=`Sigh`
- `ZH_P000599_S00051_W00000062` dur=0.78 text=`听不懂`
- `ZH_P001025_S00097_W00000254` dur=1.08 text=`听不懂。`

## EN

- 输入: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_supervisions.jsonl.gz`
- 总条数: `25,066,305`; 总小时数: `86,364.06`.
- 残留关键词标签数据: `136,828` 条 / `219.39` 小时。
- 残留整条为广义标签的数据: `2` 条 / `0.00` 小时。

### 括号片段类型

| 括号类型 | 条数 | 小时数 | 出现次数 |
| --- | --- | --- | --- |
| square | 135,681 | 225.38 | 139,247 |
| full_square | 0 | 0.00 | 0 |
| paren | 0 | 0.00 | 0 |
| full_paren | 1 | 0.00 | 2 |
| angle | 0 | 0.00 | 0 |
| brace | 0 | 0.00 | 0 |

### 关键词类别

| 类别 | 条数 | 小时数 | 出现次数 |
| --- | --- | --- | --- |
| applause（掌声/鼓掌） | 212 | 0.80 | 218 |
| beep（蜂鸣/提示音/铃声） | 19,242 | 26.12 | 20,528 |
| inaudible（听不清/不可辨） | 31 | 0.01 | 31 |
| laughter（笑声） | 51,132 | 86.06 | 52,267 |
| lyrics（歌词/唱词） | 34,363 | 61.32 | 34,364 |
| music（音乐/歌唱） | 25,370 | 28.14 | 25,497 |
| noise（噪声/音效） | 3,199 | 10.93 | 3,445 |
| silence（静音/停顿） | 302 | 0.12 | 302 |
| speech_marker（语音/人声标记） | 714 | 1.18 | 732 |
| vocal_noise（咳嗽/呼吸等人声噪声） | 2,685 | 6.14 | 2,839 |

### 高频原始括号标签

| 原始标签 | 出现次数 | 记录比例分母 |
| --- | --- | --- |
| `[Laughter]` | 51,967 | 25,066,305 |
| `[Lyric]` | 34,359 | 25,066,305 |
| `[Music]` | 24,780 | 25,066,305 |
| `[Buzzer]` | 15,980 | 25,066,305 |
| `[Beep]` | 4,350 | 25,066,305 |
| `[Sound Effect]` | 922 | 25,066,305 |
| `[Cough]` | 836 | 25,066,305 |
| `[Speech]` | 434 | 25,066,305 |
| `[Sigh]` | 346 | 25,066,305 |
| `[Coughs]` | 224 | 25,066,305 |
| `[Noise]` | 190 | 25,066,305 |
| `[Whoosh]` | 185 | 25,066,305 |
| `[Humming]` | 167 | 25,066,305 |
| `[Makes Sound]` | 159 | 25,066,305 |
| `[Sighs]` | 158 | 25,066,305 |
| `[Slap]` | 139 | 25,066,305 |
| `[Clears Throat]` | 138 | 25,066,305 |
| `[Growl]` | 105 | 25,066,305 |
| `[Applause]` | 98 | 25,066,305 |
| `[Click]` | 80 | 25,066,305 |
| `[Makes A Sound]` | 72 | 25,066,305 |
| `[Audience Laughter]` | 69 | 25,066,305 |
| `[Pfft]` | 69 | 25,066,305 |
| `[Static]` | 60 | 25,066,305 |
| `[Gasp]` | 57 | 25,066,305 |
| `[Guitar]` | 53 | 25,066,305 |
| `[Kiss]` | 49 | 25,066,305 |
| `[Bang]` | 49 | 25,066,305 |
| `[Grunts]` | 49 | 25,066,305 |
| `[Clicking]` | 47 | 25,066,305 |

### 高频归一化括号内容

| 归一化内容 | 出现次数 | 记录比例分母 |
| --- | --- | --- |
| `laughter` | 51,967 | 25,066,305 |
| `lyric` | 34,359 | 25,066,305 |
| `music` | 24,780 | 25,066,305 |
| `buzzer` | 15,980 | 25,066,305 |
| `beep` | 4,350 | 25,066,305 |
| `sound effect` | 922 | 25,066,305 |
| `cough` | 836 | 25,066,305 |
| `speech` | 434 | 25,066,305 |
| `sigh` | 346 | 25,066,305 |
| `coughs` | 224 | 25,066,305 |
| `noise` | 190 | 25,066,305 |
| `whoosh` | 185 | 25,066,305 |
| `humming` | 167 | 25,066,305 |
| `makes sound` | 159 | 25,066,305 |
| `sighs` | 158 | 25,066,305 |
| `slap` | 139 | 25,066,305 |
| `clears throat` | 138 | 25,066,305 |
| `growl` | 105 | 25,066,305 |
| `applause` | 98 | 25,066,305 |
| `click` | 80 | 25,066,305 |
| `makes a sound` | 73 | 25,066,305 |
| `audience laughter` | 69 | 25,066,305 |
| `pfft` | 69 | 25,066,305 |
| `static` | 60 | 25,066,305 |
| `gasp` | 57 | 25,066,305 |
| `guitar` | 53 | 25,066,305 |
| `kiss` | 49 | 25,066,305 |
| `bang` | 49 | 25,066,305 |
| `grunts` | 49 | 25,066,305 |
| `clicking` | 47 | 25,066,305 |

### 示例

#### 已过滤的 non_speech_tag 示例

- `en-us_1bd385e75b66_01_00385` dur=2.76 text=`[Human Sounds]`
- `en-us_1bd385e75b66_01_00483` dur=2.6 text=`[Human Sounds]`
- `en-us_1bd385e75b66_01_00592` dur=2.98 text=`[Human Sounds]`
- `en-us_1bd385e75b66_02_00388` dur=3.2 text=`[Music]`
- `en-us_1bd385e75b66_02_00542` dur=2.4 text=`[Music]`

#### applause（掌声/鼓掌）

- `EN_P001119_S00075_W00000044` dur=1.0 tag=`` text=`Applause`
- `EN_P001474_S00238_W00000079` dur=1.6 tag=`` text=`Applause`
- `EN_P001567_S00002_W00000167` dur=9.88 tag=`[Clapping]` text=`What response is he expecting? He seems like he's expecting Jesus to say, [Clapping] Good job, John. You got to keep those outsiders outside.`
- `EN_P001673_S00040_W00000030` dur=20.49 tag=`[Applause]` text=`My politics are very simple. I believe in my employees. They are greatest assets. And if we can't... [Applause] ...you know, these labor contracts affect more than 7,000 city workers. If we can't invest in our assets, I `
- `EN_P001777_S00013_W02000086` dur=1.52 tag=`` text=`Clap`

#### beep（蜂鸣/提示音/铃声）

- `EN_P000001_S00053_W02000183` dur=8.2 tag=`[Buzzer]` text=`I have [Buzzer] Uh, let's see. I I have the most notes of every episode. It's from this one. Says.`
- `EN_P000009_S00000_W02000361` dur=1.07 tag=`[Buzzer]` text=`Delete that. [Buzzer]`
- `EN_P000009_S00037_W01000157` dur=14.72 tag=`[Buzzer]` text=`I'm going to, I shouldn't say it's too tight. Like if you were wearing them, they'd probably be fine. Yeah. But they're pretty stout. And mine are old enough now, like I was wearing this in the house today and Brooke pul`
- `EN_P000016_S00004_W01000342` dur=6.92 tag=`[Buzzer]` text=`By all means. Now let's see. What have you got here? [Buzzer] Ah! Damn! Wine all over my shirt.`
- `EN_P000032_S00050_W02000012` dur=2.02 tag=`[Buzzer]` text=`Thanks for having me. Yes. [Buzzer]`

#### inaudible（听不清/不可辨）

- `EN_P003504_S00139_W01000101` dur=1.26 tag=`` text=`Unclear`
- `EN_P000245_S00081_W03000156` dur=0.91 tag=`` text=`unclear`
- `EN_P002236_S00080_W00000248` dur=1.28 tag=`` text=`Unknown`
- `EN_P002264_S00037_W01000380` dur=0.59 tag=`` text=`Unknown`
- `EN_P002991_S00160_W00000133` dur=1.02 tag=`` text=`Unknown`

#### laughter（笑声）

- `EN_P000001_S00004_W01000415` dur=4.55 tag=`[Laughter]` text=`So this is the last episode of the pod, right? [Laughter]`
- `EN_P000001_S00103_W01000451` dur=1.37 tag=`[Laughter]` text=`No. [Laughter]`
- `EN_P000009_S00018_W00000163` dur=13.11 tag=`[Laughter]` text=`Yeah, next time I come on the podcast, we're gonna uh I'm gonna bring like a footlong from Subway or something. [Laughter] [Laughter] He's trying to get him like acclimated. Like I need all the meat, you know? Yeah. The `
- `EN_P000009_S00018_W00000163` dur=13.11 tag=`[Laughter]` text=`Yeah, next time I come on the podcast, we're gonna uh I'm gonna bring like a footlong from Subway or something. [Laughter] [Laughter] He's trying to get him like acclimated. Like I need all the meat, you know? Yeah. The `
- `EN_P000014_S00016_W00000100` dur=1.15 tag=`[Laughter]` text=`Yes. [Laughter]`

#### lyrics（歌词/唱词）

- `EN_P000039_S00000_W02000033` dur=1.24 tag=`[Lyric]` text=`[Lyric] I'm a motherfucking starboy.`
- `EN_P000039_S00000_W02000065` dur=1.44 tag=`[Lyric]` text=`[Lyric] I'm a motherfucking starboy.`
- `EN_P000039_S00000_W02000115` dur=1.44 tag=`[Lyric]` text=`[Lyric] I'm a motherfucking starboy.`
- `EN_P000039_S00000_W02000143` dur=3.74 tag=`[Lyric]` text=`[Lyric] I'm a motherfucking starboy.`
- `EN_P000039_S00000_W02000174` dur=1.44 tag=`[Lyric]` text=`[Lyric] I'm a motherfucking starboy.`

#### music（音乐/歌唱）

- `EN_P000009_S00003_W00000091` dur=1.14 tag=`[Music]` text=`Yeah, dude. [Music]`
- `EN_P000009_S00039_W01000153` dur=1.12 tag=`[Music]` text=`Yeah, kind of. [Music]`
- `EN_P000023_S00027_W00000153` dur=10.05 tag=`[Bass Humming]` text=`And uh I've got this little bass amp at the house and so he's been back there [Bass Humming] beating all over the thing and it just vibrates the house to death.`
- `EN_P000050_S00019_W00000089` dur=1.39 tag=`[Music]` text=`Deep breaths. [Music]`
- `EN_P000050_S00048_W00000226` dur=6.57 tag=`[Music]` text=`Yeah, it's got it's got good texture. Texture. Yeah, Ken. Oh no. [Music] No, just kidding.`

#### noise（噪声/音效）

- `EN_P000001_S00128_W01000401` dur=31.6 tag=`[Makes A Loud, Guttural Sound]` text=`And then uh they're all supposed to they get these reaction shots of everybody when they open a Dalek and they see they're like pulling out the dead body. So but we're not going to see that so we get reaction shots of ev`
- `EN_P000030_S00002_W00000001` dur=17.2 tag=`[Makes Drumming Sound]` text=`I think the best part, I don't know if you can say best part, but thinking forward to heaven, there won't have to be this break. I mean like Peter, Peter's like [Makes Drumming Sound] on the drums and I'm like [Makes A S`
- `EN_P000030_S00002_W00000001` dur=17.2 tag=`[Makes A Sound]` text=`I think the best part, I don't know if you can say best part, but thinking forward to heaven, there won't have to be this break. I mean like Peter, Peter's like [Makes Drumming Sound] on the drums and I'm like [Makes A S`
- `EN_P000032_S00084_W00000207` dur=13.57 tag=`[Sound Effect]` text=`I saw that happen to a girl once where a dog was going ham on her pussy and it was a big group of people and the dog was just like [Sound Effect] and then at one point someone's like, he likes what he smells in there, hu`
- `EN_P000037_S00212_W00000133` dur=12.56 tag=`[Slap]` text=`You know, when you've got hot weather on the land and then that wind blows out to sea, you've got the colder weather coming in from the sea and the wind and they go like this. [Slap]`

#### silence（静音/停顿）

- `EN_P000135_S00127_W03000051` dur=1.39 tag=`` text=`Pause`
- `EN_P000213_S00004_W01000116` dur=0.97 tag=`` text=`silent`
- `EN_P000323_S00022_W00000233` dur=1.1 tag=`` text=`Silence`
- `EN_P000427_S00386_W00000002` dur=0.95 tag=`` text=`Pause`
- `EN_P000539_S00055_W00000032` dur=0.73 tag=`` text=`blank`

#### speech_marker（语音/人声标记）

- `EN_P000001_S00049_W01000168` dur=1.05 tag=`` text=`human`
- `EN_P000078_S00121_W03000075` dur=10.06 tag=`[Speech]` text=`Um, so, [Speech] I'm going to Okay, Hexblade's Curse is an ability.`
- `EN_P000396_S00006_W00000312` dur=8.25 tag=`[Speech]` text=`[Speech] [Laughter] All right.`
- `EN_P000483_S00097_W00000002` dur=8.94 tag=`[Speech]` text=`Hey everybody, welcome to Perfect Concert Playlist. I almost ran that word over. Perfect Con- [Speech] I was like, I had gravy in my mouth. I'm Michael, Ron's on the other side.`
- `EN_P000560_S00026_W02000319` dur=0.85 tag=`` text=`human`

#### vocal_noise（咳嗽/呼吸等人声噪声）

- `EN_P000023_S00032_W00000000` dur=1.51 tag=`` text=`Sigh`
- `EN_P000037_S00830_W00000035` dur=8.78 tag=`[Sigh]` text=`Oh, you don't? But but Bill does. Yeah, I... [Sigh] No, I mean look. That's his point.`
- `EN_P000049_S00004_W00000071` dur=1.52 tag=`` text=`Sigh`
- `EN_P000071_S00143_W01000217` dur=1.44 tag=`` text=`Sigh`
- `EN_P000073_S00063_W02000282` dur=0.9 tag=`` text=`Cough`

#### 整条为广义标签的示例

- `EN_P000738_S00589_W00000000` dur=1.15 tag=`[[Silence]` text=`[[Silence]`
- `EN_P000603_S00023_W00000000` dur=1.01 tag=`[[Silence]` text=`[[Silence]`

#### 裸关键词标签示例

- `EN_P000001_S00049_W01000168` dur=1.05 text=`human`
- `EN_P000023_S00032_W00000000` dur=1.51 text=`Sigh`
- `EN_P000049_S00004_W00000071` dur=1.52 text=`Sigh`
- `EN_P000071_S00143_W01000217` dur=1.44 text=`Sigh`
- `EN_P000073_S00063_W02000282` dur=0.9 text=`Cough`

## 第一版清洗规划：直接过滤所有含括号片段的样本

基于当前统计，第一版清洗建议直接采用最简单、最稳的策略：**hard reject 所有 `text` 中包含括号片段的 supervision**。这里的括号片段沿用本报告扫描口径，覆盖英文方括号、中文全角括号、圆括号、尖括号和花括号。

这个策略会误删一部分正常括号解释，例如 `（AI）`、`（CNN）`、`（LLM）`，但总损失很小，而且可以一次性覆盖 `[Lyric]`、`[Music]`、`[Laughter]`、`[Buzzer]`、`[Noise]` 等主要污染源。

### 1. 过滤口径

第一版 hard reject 条件：

```text
text contains any bracket span in:
[]  【】  ()  （）  <>  {}
```

建议使用与扫描脚本一致的正则，避免扫描统计和实际过滤口径不一致：

```python
BRACKET_SPAN_RE = re.compile(
    r"\[[^\[\]\n\r]{1,120}?\]"
    r"|【[^【】\n\r]{1,120}?】"
    r"|\([^()\n\r]{1,120}?\)"
    r"|（[^（）\n\r]{1,120}?）"
    r"|<[^<>\n\r]{1,120}?>"
    r"|\{[^{}\n\r]{1,120}?\}"
)
```

### 2. 预期数据损失

按当前训练用 supervisions 统计：

| 过滤口径 | ZH 损失 | EN 损失 | 合计损失 |
| --- | ---: | ---: | ---: |
| 含任意括号片段 `[]` / `（）` / `()` / `<>` / `{}` | 1,050.06h | 225.38h | 1,275.44h |
| 含英文方括号 `[...]` | 944.54h | 225.38h | 1,169.92h |
| 命中非语音关键词标签 | 943.01h | 219.39h | 1,162.40h |

当前 ZH+EN supervision 总时长约 `197,440.51h`。因此：

- 过滤所有含英文方括号 `[...]` 的样本，损失约 `0.59%`。
- 过滤所有含任意括号片段的样本，损失约 `0.65%`。

直接过滤所有括号片段比只过滤英文方括号多损失约 `105.52h`，主要来自 ZH 的 `（）` 正常解释或补充内容。考虑到整体占比只有约 `0.65%`，第一版可以接受这个误删成本，换取规则简单和训练文本更干净。

### 3. 输出物设计

不要覆盖原始 manifests。建议生成一个版本化清洗目录，例如：

```text
.../Jellycat/manifests/ZH/contains_bracket_reject_v1/
.../Jellycat/manifests/EN/contains_bracket_reject_v1/
```

每个语言目录建议产出：

| 文件 | 用途 |
| --- | --- |
| `jellycat_ZH_contains_bracket_reject_v1.reject.jsonl` | 被过滤样本清单，包含 id、recording_id、duration、matched_spans、text、reason。 |
| `jellycat_ZH_contains_bracket_reject_v1.summary.json` | 过滤前后条数、小时数、括号类型分布、示例。 |
| `jellycat_ZH_supervisions.contains_bracket_reject_v1.jsonl.gz` | 过滤后的 Lhotse supervisions。 |
| `jellycat_ZH_recordings.contains_bracket_reject_v1.jsonl.gz` | 同步过滤后的 Lhotse recordings。 |

EN 文件同理替换 `ZH` 为 `EN`。

### 4. 实施步骤

#### Step 1: 从 supervisions 生成 reject list

对 `jellycat_ZH_supervisions.jsonl.gz` 和 `jellycat_EN_supervisions.jsonl.gz` 流式扫描：

- 如果 `BRACKET_SPAN_RE.search(supervision.text)` 命中，就写入 reject list。
- reject 记录至少包含：
  - `id`
  - `recording_id`
  - `duration`
  - `language`
  - `matched_spans`
  - `matched_bracket_types`
  - `text`
  - `reason: contains_bracket_span_v1`

这一步只生成清单，不改原始文件。

#### Step 2: 同步过滤 supervisions 和 recordings

训练入口使用 Lhotse supervision/recording manifests，所以需要同步过滤两类文件：

- supervisions: 删除 `supervision.id` 或 `supervision.recording_id` 在 reject list 中的记录。
- recordings: 删除 `recording.id` 在 reject recording id 集合中的记录。

当前数据基本是一条 recording 对一条 supervision；即便如此，也应该按 `recording_id` 同步过滤，避免 orphan supervision 或 orphan recording。

#### Step 3: 校验过滤后 manifest

过滤后必须做这些检查：

| 检查项 | 预期 |
| --- | --- |
| 过滤后 supervisions 中 `BRACKET_SPAN_RE.search(text)` | `0` |
| filtered supervisions 条数 + reject 条数 | 等于原 supervisions 条数 |
| filtered supervision recording_ids | 全部存在于 filtered recordings |
| filtered recordings ids | 不包含 reject recording ids |
| 总时长损失 | ZH 约 `1,050.06h`，EN 约 `225.38h` |
| Lhotse manifest 可读性 | `load_manifest_lazy_or_eager` 能正常遍历 |

#### Step 4: 用过滤后的 manifests 重新生成 ASR 数据

不要直接复用旧 raw cuts/features/lang，因为旧数据里已经包含这些样本。建议把 ASR 数据准备从 source manifest 入口重跑：

- `source_recordings_manifest` 指向过滤后的 recordings。
- `source_supervisions_manifest` 指向过滤后的 supervisions。
- 重新生成 raw cuts。
- 重新生成 BPE/hybrid lang 资源，避免 `[Lyric]`、`[Music]` 等残留 token 继续进入词表。
- 重新生成或重新抽取训练特征，取决于当前 recipe 使用 on-the-fly 还是 precomputed features。

### 5. 为什么第一版不做 strip-tag 保留正文

像下面这些样本理论上可以只删标签、保留正文：

```text
hello [Music]
[Laughter] 然后他说...
[Music] 主持人开场...
```

但第一版不建议这么做，原因是：

- 总损失只有约 `0.65%`，为了这部分数据设计复杂 transcript 改写不划算。
- `[Lyric]` 和 `[Music]` 对应的音频经常不是普通口语，即使文本看起来可读，也未必适合 ASR 训练。
- strip-tag 会引入新的对齐风险：标签对应的声学片段仍在音频中，但 transcript 被删掉，可能造成局部错配。
- hard reject 的结果更容易验证：过滤后不应再出现任何括号片段。

### 6. 回滚和对照实验

建议保留三个版本用于对照：

| 版本 | 内容 | 用途 |
| --- | --- | --- |
| `baseline` | 当前未做括号过滤的数据 | 复现实验基线。 |
| `square_bracket_reject_v1` | 只过滤含 `[...]` 的样本 | 更保守，损失约 `0.59%`。 |
| `contains_bracket_reject_v1` | 过滤任意括号片段 | 推荐第一版，损失约 `0.65%`。 |

如果训练资源紧张，可以直接跑 `contains_bracket_reject_v1`。如果想确认误删圆括号正常文本是否有影响，可以再补一个 `square_bracket_reject_v1` 作为 ablation。

### 7. 推荐验收标准

第一版清洗完成后，建议用以下标准验收：

- ZH/EN 过滤后 supervisions 中任意括号片段命中数为 `0`。
- ZH 训练数据减少约 `1,050.06h`，EN 减少约 `225.38h`，误差只来自后续是否同步应用 duration45 等其他过滤版本。
- token inventory 中 `[Lyric]`、`[Music]`、`[Laughter]`、`[Buzzer]`、`[Noise]` 等标签 token 不再出现。
- 随机抽查 reject list 前 100 条和按时长排序 top 100 条，确认都是符合预期的含括号样本。
- 用过滤后数据做一次短训练或 fine-tune，对比 WenetSpeech/AISHELL/THCHS30 等公开集 CER，确认是否改善新数据训练劣化问题。
