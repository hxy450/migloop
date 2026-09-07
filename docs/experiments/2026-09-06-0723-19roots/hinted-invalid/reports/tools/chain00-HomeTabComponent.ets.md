```
文件: entry/src/main/ets/components/HomeTabComponent.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v20 / v21 / v22
修复改了什么: v20 给顶部横幅 `Image(icon_home_top_bg)` 补 `.aspectRatio(1080/660)` 并加注释(纯新增 5 行);v21 在根 Stack 末尾挂了一份零尺寸的 `PermissionIntroHost()`(纯新增,只挂宿主、不接展示时机);v22 只是把一段存储权限的过时块注释合并进 VM 注释,无逻辑改动。
修复的依据: v20 依据 finding `ALIGN_PHomeFragment_layout_drift_header-banner-height.md@v3`(fixer-r1 v14 于 #23190 读到):§3 dump 实测头图比例 0.507 ≠ 资源固有 660/1080=0.611,§4 点名 `HomeTabComponent.ets:369-371` 缺显式高度,§5 直接给出 `.aspectRatio(1080/660)` 处方;上游是主会话 ff019d8a v74 派发词把 `SYSTEMIC_image-no-explicit-size` 列为 P0 首修。v21 依据 `AppPermissionIntroDialog_01_host_never_mounted.md@v1`(#23276)+ `PermissionIntroHost.ets@v6` 全文(#23278)+ 安卓 `HomeFragment.kt@v2:190-250`(#23288)。
被改代码的来源: 纯新增(blame v20 changed=True:替换 v19 的 0 行、新增 5 行)。被补的那三行 `Image(...).width('100%').objectFit(ImageFit.Contain)` 在 blame v19 里归属为 `?`(断点后,本文件行级归属 content-unknown);按 sessions 该文件生成方是 conv-hometab(agent-aconv-hometab-afeccbf00da93597),它 v1 写出文件 v2(#7855)前**全文读过** `fragment_home.xml@v1`(#7802,含 `imageView2` 的 `adjustViewBounds=true`)和 `ui-migration-pitfalls.md@v1`(#7851),收尾报告自述 "ConstraintLayout → Stack(顶图)+Column(纵向流)",代码里 "①…imageView2:match_parent 宽、adjustViewBounds 按比例、贴顶" 的注释与之对应 —— 即源码读全了,只是把 `adjustViewBounds` 直译成 `width('100%')+Contain`,没落显式比例。
生成时为什么没做好: 转换环节(a2h-execute 的 activity-converter)转换错 —— 抱着"ArkUI Image 不写尺寸会回退固有尺寸"的错误共享假设直译 `adjustViewBounds`,同族缺陷全仓 30 处/16 文件。
是否必要: v20 必要(有像素实测判据 0.507 vs 0.611,P0 系统性);v21 存疑(fixer 自己在收尾里标"需人工裁定"——它查源码后认定该浮层只在 `SDK_INT < R` 分支出现,基线设备本就不显示,挂宿主只关掉了单子的字面);v22 可免(纯注释整理)。
证据(每条带坐标):
  1. diff `HomeTabComponent.ets@v20` — 仅加 `.aspectRatio(1080 / 660)` 与 4 行说明;blame `@v20 changed=True` = 替换 0 行 / 新增 5 行,故属补写而非改错。
  2. agent fixer-r1 v14 时间线:#23190 读 `ALIGN_PHomeFragment_layout_drift_header-banner-height.md@v3`,#23194 写前读 `HomeTabComponent.ets@v19 [358-407行]`,随即 #23196 落 v20。
  3. `SYSTEMIC_image-no-explicit-size.md@v2:52-53、65-68` — ArkUI `Image` 不写尺寸不取固有尺寸而撑满父容器;§4 明指迁移注释里"固有尺寸(源未标注 size)/交 icon-sizing 自愈"这套假设本身是错的,`affects` 第 22 行正是本单。
  4. agent conv-hometab(共 6 版):v1 #7802 全文读 `fragment_home.xml@v1`、#7851 读 `ui-migration-pitfalls.md@v1` 后 #7855 写 `HomeTabComponent.ets@v2`;派发词只给 D-008「不硬编码 bounds」等约束,无 Image 显式尺寸要求。
  5. blame `HomeTabComponent.ets@v19` 第 368-371 行全部为 `?`(归属未知,断点后 373 行);slice17-home 的 155 行不含这一段 → 该 Image 块早于 slice17,属生成期基线。
  6. `PermissionIntroHost.ets` 脊柱:v1 由 slice11-startup v5 建于 T+27:50,到 v6 共 6 版全在生成期,下游 14 条读取里生成期无一处把它接进 build() → 跨 slice 接线归属真空,不是本文件写者写错。
  7. diff `@v22` — 删 4 行块注释、在 VM 注释里改写 2 行,无代码;file `@v22` 标 "断点 edit-miss / 盲写,内容无法复原"。
无法确认的部分: 本文件行级归属是 content-unknown(v2 来路 unknown、v1 为"外部输入 内容未知"),因此 `.width('100%')+Contain` 出自 conv-hometab 只有三重旁证(sessions 生成方标注、其自述报告、注释措辞),没有逐行签名;v22 全文复原不了;fixer-r1 在本文件上还有 #23225/#23292/#23360 三次"脚本黑盒"调用方向不明,不能排除同轮还有未立版本的改动;`ui-migration-pitfalls.md` 的正文未展开,无法直接证明该文档缺 Image 尺寸这一条。
置信: 中 —— 修复侧证据链(单据→读取→diff)闭合且带实测数值,但生成侧因账本断点无法逐行签名,作者归属靠旁证推定。
```