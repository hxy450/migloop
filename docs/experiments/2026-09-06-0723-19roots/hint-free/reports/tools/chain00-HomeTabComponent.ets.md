```
文件: entry/src/main/ets/components/HomeTabComponent.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v20–v22(另有 3 次「不立版本」的脚本改写 #23225 / #23292 / #23360)
修复改了什么: 三处 Image 补显式比例/尺寸(顶图 `.aspectRatio(1080/660)`、icon_home_title `488/68`、icon_home_top_vip 按「ArkUI padding 计入声明尺寸」重算);把文档态授权由 `storagePermissionGranted` 布尔换成 `F008ViewModel/DocImportRouter`(走 DocumentViewPicker)并挂上零尺寸 `PermissionIntroHost()`;修右侧选中态 Row 挡死左半热区(补 `hitTestBehavior(Transparent)`)与步骤1文案被 @Builder 值参定格(改内联展开)。
修复的依据: 派发词(主会话·ff019d8a v74 派发)把 `SYSTEMIC_image-no-explicit-size` 列为 P0;写 v20 前读了 `ALIGN_PHomeFragment_layout_drift_header-banner-height.md@v3`(fixer v14 #23190),单里有像素实测:鸿蒙头图 `Image[0,127][1216,743]` 比例 0.507 ≠ 资源固有 660/1080=0.611,并直接点名 `HomeTabComponent.ets:369-371`;其余各改动各自对应 `AppPermissionIntroDialog_01_host_never_mounted`、`FileListPage_01_..._bypasses_document_picker` + `CRASH_PFileConfirmDialog_page_missing_hmos`、`HomeFragment_01/_02` 五张单(fixer v19 #23276/#23282、v20 #23349)。
被改代码的来源: 顶图那三行属 **纯新增**(blame v20 changed:替换 0 行 / 新增 5 行),被它订正的 v19:369-371 在 blame v19 里是「归属未知(断点后)」,只能定位到首版转换产物(conv-hometab v1 写 @v2 #7855,409 行,内容未入账);可确证归属的两处:`stepCell('1', this.currentItem===0 ? …)` = conv-hometab@v5(blame v19 L410),`confirmOperate` 那段(v19:262-286)= slice17-home@v16,依据是它自己写下的 `P-S9-010`「华为侧访问文件不需要存储权限」定论 + `D0 不生成永假死代码`(v19:253-260)。
生成时为什么没做好: 转换环(a2h-execute / conv-hometab v1):它读了 `fragment_home.xml@v1` 全文(#7802)把 `adjustViewBounds` 直译成 `objectFit(Contain)`,却**从未读过 icon_home_top_bg 的固有像素**(读取集里只有 app_round_corner_* 等 shape XML)—— 漏读资源真值 + ArkUI/Android 尺寸语义反向,同一错误全仓 30 处/16 文件。
是否必要: 必要 —— 头图有像素级判据(0.507 vs 0.611)、tab 切不回与步骤1文案是实测 dead handler、跳过 DocumentViewPicker 会让 FileListPage 恒空;唯一存疑是 `PermissionIntroHost()` 挂载:fixer 自己判定该浮层在鸿蒙恒不 show 并标「需人工裁定」,等于挂了个不会显示的宿主。
证据(每条带坐标):
  1. diff HomeTabComponent.ets@v20(fixer-r1 v14 #23196):+`.aspectRatio(1080 / 660)` 及「实测被压扁到 0.507 / 固有 0.611」注释;blame@v20 changed = 替换 0 行、新增 5 行。
  2. action(fixer-r1, #23190) 拉回的单原文 §3/§4:`root_cause_hint: HomeTabComponent.ets:369-371 … 缺显式高度`;该读绑 `ALIGN_..._header-banner-height.md@v3`(写者 vv-t2-A03 v10 #23815)。
  3. fixer-r1 派发词(全文):`SYSTEMIC_image-no-explicit-size` P0「Image 不写 width/height 时不取固有尺寸而是撑满父容器,取值以安卓侧资源固有尺寸为准」。
  4. action(fixer-r1, #23225) 脚本(喂 v16,不立版本):同一文件另补 `icon_home_title .aspectRatio(488/68)`、`icon_home_top_vip` padding 计入尺寸。
  5. action(fixer-r1, #23292)(喂 v19):删 `storagePermissionGranted`、引入 `DocImportRouter/F008ViewModel` 与 `PermissionIntroHost`;同版读单 #23282、读 HomeDocComponent.ets@v10[100-175] #23285、HomeFragment.kt@v2[190-250] #23288。
  6. diff @v21(#23304)挂 `PermissionIntroHost()`,写前读 PermissionIntroHost.ets@v6 全文(#23278);该文件 v1 由 slice11-startup v5(#15596)创建,文件头第 23 行就写明「`PermissionIntroHost()` 放在页面根容器里」,但生成期无人照做。
  7. action(fixer-r1, #23360)(喂 v20):右侧选中态 Row 补 `hitTestBehavior(Transparent)`、步骤1格内联展开;被改的 stepCell 调用行 = blame v19 L410 `conv-hometab@v5`。
  8. agent(conv-hometab) v1 读取集:`fragment_home.xml@v1`(#7802)、`ui-migration-pitfalls.md@v1`(#7851),自报应用 P-08/P-13/P-14/P-15/P-17,全程无 icon_home_top_bg 像素尺寸读。
无法确认的部分: ① v19:369-371 的逐行作者(blame 标「归属未知(断点后)」,首版 v2 内容未入账),只能归到首版转换产物;② `ui-migration-pitfalls.md@v1` 里是否本来就有「Image 必须显式尺寸」这一条(未展开该文件),故「参考文档缺条目」只是推断;③ v22 全文不可复原(edit-miss 盲写断点),v20 后的文件全貌只能由 diff+脚本原文拼出。
置信: 中 —— 修复侧(改了什么、凭哪张单、读了什么)有 diff + 脚本原文 + 单原文三重坐标,证据很硬;但生成侧首版内容未入账,「原写者是谁写的那三行」只能由写者脊柱与读取集反推,达不到逐行签名级别。
```