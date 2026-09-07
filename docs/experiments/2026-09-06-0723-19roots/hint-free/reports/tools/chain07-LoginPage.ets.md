```
文件: entry/src/main/ets/pages/LoginPage.ets  修复方: visual-fixer 修复 round-1 / fixer-r1(agent-a68daf720e780b4c2)  修复版本: v33(写于 fixer-r1 v22,#23441,T+81:14)
修复改了什么: 在 NavDestination 尾部 `.hideTitleBar(true)` 之后纯新增 `.onBackPressed(() => { this.navPathStack.pop(); return true })` 及 5 行说明注释(共 +9 行),让系统 BACK 复用返回箭头的出栈逻辑,不再依赖 NavDestination 默认出栈。
修复的依据: round-1 单 `spec/fix/round-1/ui/CRASH_PLoginActivity_back_failed_LoginActivity_to_MineFragment.md@v1`(fixer-r1 v22 #23428 读);该单来源行由 vv-t1-A02 v8 用脚本填为真机 round-1 `LoginActivity.hmos.json`「BACK 后 dumpLayout 内容不变」的现场证据(#24185)。fixer-r1 自查 grep onBackPressed 于本页无命中(#23433 失败),并对照 ManageRenewPage.ets:265-269 的既有写法(#23436)。
被改代码的来源: 纯新增。同一位置在 LoginPage.ets@v24 就只有 `.hideTitleBar(true)`(421-422 行);该页由 conv-login(agent-aconv-login-251236e9c3d44116,v1–v3 → 文件 v2–v4)生成、slice2-auth v15–v39 续写,自始至终没写过 onBackPressed。conv-login 没写的原因:它手里的页面 spec `page_0026_LoginActivity.md@v1` 第 55-60 行「导航关系」只登记出向跳转(AppLoadDialog / WebViewPage),没有 BACK/finish 回边;派发词(主会话 9b3105a2@v88)只给了 D-008 不硬编码 bounds、$r() 资源、沉浸式 Layer 3、export Builder 四条约束,没有「返回 pop()」这一条。
生成时为什么没做好: spec+派发缺口这一环 —— 页面 spec 不登记 BACK 回边,且给 conv-login 的派发词没有像给 conv-managerenew(@v129:「navPathStack 沿用范式页;返回 pop()」+ 先读范式页 FileUploadPage)那样下硬要求,converter 转而照抄同样缺该回调的兄弟页。
是否必要: 必要,真机 dumpLayout 证明本页 BACK 无响应、页面退不出去,且改法与同工程 ManageRenewPage 既有实现一致。
证据(每条带坐标):
  1. diff LoginPage.ets@v33:仅新增 `.onBackPressed(){pop();return true}` 与注释,无删除行(写者 fixer-r1 v22 #23441)。
  2. LoginPage.ets@v24 内容 421-423 行:`.hideTitleBar(true)` 后直接闭合 —— 生成期同位置无 onBackPressed;写者脊柱 v2–v4=conv-login、v6–v24=slice2-auth。
  3. page_0026_LoginActivity.md@v1(conv-login #7975 全文 Read,67/67 行):「导航关系」表只有 AppLoadDialog、WebViewActivity 两条出向,无返回/finish 条目;「沉浸式」只指向 immersive skill。
  4. conv-login 派发词(派发自 主会话·9b3105a2@v88)关键约束仅四条(D-008 / $r() / Layer 3 / Builder),无返回键要求;其参照页为 ChoiceTemplatePage.ets@v3、GuidePage、HomePage、SplashPage(#7996/#7998 全文读)。
  5. 反例 conv-managerenew(派发自 主会话·9b3105a2@v129)派发词第 3 条明写「navPathStack 沿用范式页;返回 pop()」,ManageRenewPage.ets@v1(#8109)一次成型即带 onBackPressed(#23436 输出 265-269 行)。
  6. fixer-r1 v22 #23436 同一次 Bash 同时打印 LoginPage 415-440 行(无回调)与 ManageRenewPage 的回调实现,是它「照 ManageRenew 补齐」的直接现场。
  7. 同轮 fixer-r1 v26 #23492 另用 python 脚本改过本文件(标题栏返回图标 24 方框 → 12x19vp),输出 `ok entry/src/main/ets/pages/LoginPage.ets`,账本未立版本(方向不明条目已判为写)。
无法确认的部分: ①文件 v5 是「实录外修改」断点,blame@v33 全文行级归属未知,v25–v32(slice2-auth v40/41、group2-closer v37–v42)内容未知 —— 不能完全排除中间某版曾有过 onBackPressed 又被删(但 v24 与 v32 两端都可证无);②finding 单正文为外部输入、无法复原,只能凭其来源行与 fixer 引用;③「Android LoginActivity 未重写 onBackPressed、基类 BaseBusinessActivity 默认 finish」只有 fixer-r1 与 ManageRenewPage:266 的注释旁证,未直接取证 LoginActivity.kt 原文;④ChoiceTemplatePage@v3 缺该回调仅由 fixer-r1 收尾输出佐证,我只读到该版 62-87 行。
置信: 中 —— 修复内容、生成期缺失、spec/派发缺口三点都有直接坐标;根因归到「派发词+页面 spec 未登记 BACK 回边」是与 conv-managerenew 的对照推断,且中间数版内容未知、行级归属被断点截断。
```