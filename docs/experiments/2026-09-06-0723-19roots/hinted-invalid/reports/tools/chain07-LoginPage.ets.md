```
文件: entry/src/main/ets/pages/LoginPage.ets  修复方: visual-fixer 修复 round-1(agent-a68daf720e780b4c2)  修复版本: v33
修复改了什么: 纯新增——在页面 NavDestination 尾部(原本只有 `.hideTitleBar(true)`)挂上 `.onBackPressed(() => { this.navPathStack.pop(); return true })` 并附 5 行取证注释;没有删改任何旧行(diff@v33 全是 + 行)。
修复的依据: round-1 的实测单 `spec/fix/round-1/ui/CRASH_PLoginActivity_back_failed_LoginActivity_to_MineFragment.md@v1`(fixer-r1 v22 #23428 读到 §2–§5):安卓 LoginActivity 是普通 Activity,BACK 默认 finish() 回「我的」;鸿蒙侧连按两次 `uinput -K -d 2` 后 dumpLayout 仍是登录页,而点左上角箭头 (90,200) 一次即回 → 判定「登录页没接系统返回」。fixer 自己再 grep+sed 复核(#23433 失败=文件里根本没有 onBackPressed;#23436 打印 415-440 行确认尾部只有 hideTitleBar),并抄了同 batch `ManageRenewPage.ets:265` 的现成写法。
被改代码的来源: 纯新增。这段 NavDestination 尾部是 conv-login(a2h-activity-converter,转换 LoginActivity)在 v2–v4(#8012–#8016, T+14:32)写的,v4 第 347-350 行与 fixer 修复前读到的现场逐字一致。它没写 onBackPressed 的依据:①它全文读了 `LoginActivity.kt@v2`(#7984),而安卓侧该类**没有重写 onBackPressed**,即源码里没有可转换的返回逻辑;②页面 spec `page_0026_LoginActivity.md@v1` 的「导航关系」表(55-60 行)只登记了向外的 dialog / `pushPathByName('WebViewPage')`,一条返回键/finish 语义都没有;③它的派发词只给了 D-008 不硬编码 bounds、资源 $r()、沉浸式 Layer 3 三条约束。所以它只把 TitleBar 左上角箭头做成真实 pop(收尾报告:「返回/清除/勾选/checkPrivacy 为真实本地实现」),系统 BACK 默认交给 NavDestination —— 而该默认在本页实测不生效。
生成时为什么没做好: 卡在 page-spec 生成这一环——`page_0026_LoginActivity.md@v1` 的导航关系只列出边不列「Activity 默认 finish → NavDestination 需显式 pop」,converter 派发词也没兜底,于是同一批 converter 里有人挂(ManageRenewPage/WebViewPage)有人不挂,登录页漏了。
是否必要: 必要,单里有连按两次 BACK + dumpLayout 的实测取证,fixer 又两次现场复核确认文件里确无该回调,未登录用户的主要退出路径确实退化为只能点箭头。
证据(每条带坐标):
  1. diff(LoginPage.ets@v33) —— 全是 + 行,仅在 `.hideTitleBar(true)` 后追加 onBackPressed;写者 fixer-r1 v22 (#23441, T+81:14)。
  2. 单 `CRASH_PLoginActivity_back_failed_..._MineFragment.md@v1` §3(经 fixer-r1 #23428 原文):2×BACK 无变化、箭头一次即回,ManageRenewPage/WebView 的 BACK 正常 → 排除设备问题。
  3. fixer-r1 #23433(grep onBackPressed 于 LoginPage,命令失败=零命中)+ #23436(sed 415-440 打印,尾部只到 `.hideTitleBar(true)`)—— 修改前该文件确无此回调。
  4. #23436 同一次输出的对照段:`ManageRenewPage.ets:265-269` 已有 `.onBackPressed → navPathStack.pop(); return true`,注释「Android BaseBusinessActivity 默认返回(finish)→ 出栈」;fixer 照抄该形。
  5. LoginPage.ets@v4(conv-login v3, #8016)第 347-350 行 = `}` / 沉浸式注释 / `.hideTitleBar(true)` / `}`,与 @v24、与 #23436 现场逐字相同 → 这处缺口从生成期一直留到修复期。
  6. conv-login v1 读取集(#7984 LoginActivity.kt@v2 全文、#7975 page spec 全文)+ 收尾报告「沉浸式 Layer 3(hideTitleBar+背景穿透)」「返回…为真实本地实现」—— 它读全了源码,源码本身无 onBackPressed 可转。
  7. `page_0026_LoginActivity.md@v1` 55-60 行「导航关系」表只有 AppLoadDialog / WebViewActivity 两条出边,无返回键条目;conv-login 派发词全文三条约束里也无返回键要求。
  8. fixer 的落地形与单里 §5 建议 2(「不实现 onBackPress 或 return false 走默认」)相反,它选了显式 pop + return true,并在代码注释里写明理由「默认出栈在本页并未生效」—— 是有意偏离并留痕。
无法确认的部分: ①该文件 v25–v32(slice2-auth v40/41、group2-closer v37–v42)内容未知,且 @2026-07-24T11:55 有 outband-change 断点,blame 对全文报「归属未知(断点后)」——「这几版没动过尾部」是靠 v4/v24 与 #23436 现场三处逐字相同倒推的,不是逐行签名直证。②ManageRenewPage 那条 onBackPressed 的确切写者无法坐实:blame@v7 显示全文 518 行中 508 行属 conv-managerenew,但 fixer-r1 v15(#23214,脚本黑盒)先改过该文件导致行号错位,该行归属只能算「大概率 conv-managerenew」。③单本身内容不可复原(外部输入),我引的是 fixer 读它时的 stdout(#23428),非账本快照。④「NavDestination 默认出栈为何在本页失效」的机制无实录,单里列的三条源码缺口有两条是 unknown。
置信: 高 —— 修复内容、修复前现场、原作者那一版的同段原文、以及 spec 里返回键语义的缺失,四项都有直接坐标;仅中间几版内容未知一处靠三点对齐倒推。
```