```
文件: entry/src/main/ets/pages/MemberCenterPage.ets  修复方: build-verify-r1「编译验证 fixer 改动」(agent-af0e3d2ae54dbf769)  修复版本: v10-v11
修复改了什么: 把两个价格 helper 的访问修饰符放宽——`private static priceDigits` → `static`(v10)、`private static priceSuffix` → `static`(v11),各 1 行,`priceSplitIndex` 仍保持 private,没动任何语义。
修复的依据: 自己跑的编译日志 build1.log@v1(读于 build-verify-r1 v3 #26064/#26066)报 ArkTS 10505001「Property 'priceDigits' is private and only accessible within class 'MemberCenterPage'」(:1222,priceSuffix 同 :1223);#26068 grep 定位到声明在 1116/1124、调用点在 1222/1223 的另一个 struct(报告称 ProductItemCard)。改后 build2.log@v1 BUILD PASS(v5 #26076)。
被改代码的来源: 同一轮的 visual-fixer(fixer-r1 = agent-a68daf720e780b4c2)v30 #23577(T+81:30,python heredoc,属"实录外/脚本黑盒",未立版本)。它先在 v26 #23515 用 `Text(){ForEach(...Span)}` + splitPriceRuns/isDigitRun 实现,几分钟后 #23577 自我改写成"固定两个 Span、不用条件/循环渲染",并新增 `private static priceDigits/priceSuffix/priceSplitIndex`——`private` 是照抄同文件既有的 `private static stripCurrency` 写法。依据是 ALIGN_PMemberCenterActivitiy_font_mismatch_product-price-suffix.md@v1(#23486)+ 安卓源码 MemberCenterActivitiy.kt@v2:265-295(#23511)的 `showNowPrice.replaceSpan(Regex("\d+")){AbsoluteSizeSpan(30,true)}`。
生成时为什么没做好: 漏读源码——生成环 conv-member v1(#8173)只读了 activity_member_center.xml/item_product_info.xml/view.xml,没读页面 spec 第 7 行 anchors 指定、第 56-58 行明写"converter 需读 anchor 源码"的 MemberCenterActivitiy.kt,运行期 SpannableString 的分级字号信息在转换环整个丢失,价格被压成单个 30vp Text。
是否必要: 必要,不改则整模块 CompileArkTS 失败(2 条 10505001),且是纯可见性放宽、没有回退 fixer 的视觉修复。
证据(每条带坐标):
  1. diff MemberCenterPage.ets@v10 / @v11:唯一变更是 `private static priceDigits|priceSuffix` → `static`(写者 build-verify-r1 v3 #26072 / v4 #26074)。
  2. build-verify-r1 v3 读 build1.log@v1 命中 ArkTS Compiler Error 10505001(#26064,行 336/337/341/345/351);#26068 grep 出 1116/1124/1222/1223 四行。
  3. fixer-r1 #23577 原文:把 ForEach 版整块替换为 `Span(MemberCenterPage.priceDigits(...)).fontSize(30)` / `priceSuffix(...).fontSize(16)`,并把 splitPriceRuns/isDigitRun 换成 `private static priceDigits/priceSuffix`。
  4. fixer-r1 v26 的判据:#23486 读到该 ALIGN 单 §2-§5(期望三级字号 ￥16/数字 30/后缀中号,root_cause_hint「迁移时把安卓 SpannableString 多级字号压成了一个 Text」),#23504/#23506/#23511 读 item_product_info.xml@v1 与 MemberCenterActivitiy.kt@v2:265-295。
  5. 被覆盖的原实现出自生成期:blame MemberCenterPage.ets@v7 第 1148-1152 行 = conv-member@v1(注释「rollingTextView(滚动数字,30vp 加粗)」+ `.fontSize(30)`),slice8-pay@v7 只把 1149 行换成 `animatedPrice` 数据源。
  6. conv-member v1 的读取集(#8132–#8171)无任何 .kt;而它读到的 spec/baseline/ui/page_0028_MemberCenterActivitiy.md@v2(#8132)第 7 行就给出了 kt anchor。
  7. 可见性错误必然漏到编译环:conv-member 派发词「⚠️ 禁止编译」、fixer-r1 派发词「代码落盘即可:不动 git、不重编、不复测」,两次写入都没经过 ArkTS 检查。
无法确认的部分: v8-v11 的文件全文无法复原(file 报 edit-miss 盲写),故 blame(changed=True) 对 v10/v11 不可用,被改行的归属是靠 #23577 脚本原文 + #26068 grep 对上的,不是版本级 diff;ALIGN 单 @v1 是"外部输入"无全文快照,只看到 fixer 读到的 §2-§5 片段;调用点所在 struct 名 `ProductItemCard` 来自 build-verify-r1 收尾报告,未在实录代码文本里直接核到(编译错误信息只证明是跨 class 访问);#23515→#23577 由 ForEach 改双 Span 的动机(是否因 ArkTS 不允许 Text 内 ForEach)实录里没写明。
置信: 高,修复版本的 diff、编译错误原文、引入者脚本原文、生成期 blame 与 conv-member 的完整读取集这五环都拿到了直接坐标,只有 v8-v11 全文复原这一处缺口,且不影响结论。
```