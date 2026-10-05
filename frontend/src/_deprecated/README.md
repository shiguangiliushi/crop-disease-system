# `src/_deprecated/` —— 已停用的历史文件（备份，未被任何模块引用）

这些文件是从 `src/` 各目录**移动**过来的，**没有删除**，目录结构保持原样（因此文件之间的相对引用仍然成立）。
项目当前没有可用的版本控制（`.git` 已损坏），所以采用"移动备份"而不是删除。

## 为什么停用

统一用脚本扫描了 `src/` 下所有 `import` 语句（含 `@/` 别名与相对路径），
以下文件**没有被任何模块引用**，属于脚手架残留、被新实现取代、或本身已损坏：

| 原路径 | 说明 |
|---|---|
| `views/AuthView.vue` | 旧版登录/注册页，已被 `LoginView.vue` / `RegisterView.vue` 取代 |
| `views/DiseaseStatistics.vue` | 统计页副本（含写死的模拟数据回退）。**该文件当时已被截断损坏**：缺少 `</script>`、缺少 `<style>` 开标签、残留 `// ... (其余代码保持不变)` 占位注释与几行游离 CSS。统计功能现由 `components/DiseaseStatistics.vue` 提供 |
| `views/FeedbackView.vue` | 反馈页，未接入路由（反馈提交已内嵌在「病害识别」结果页） |
| `views/PestopediaView.vue` | 旧版病害百科，已被 `PestEncyclopediaView.vue` 取代 |
| `views/error/403.vue`、`views/error/404.vue` | 未被路由使用（404 使用 `views/NotFoundView.vue`） |
| `components/TinyMCE.vue` | 从 `cdn.tiny.cloud/1/no-api-key` 加载编辑器，离线必失败；已被 Quill 版 `components/RichTextEditor.vue` 取代 |
| `components/CommentItem.vue` | 未被引用（版块页自行渲染评论） |
| `components/AuthDebug.vue` | 调试用组件 |
| `components/TheWelcome.vue`、`WelcomeItem.vue`、`icons/Icon*.vue` | Vue 脚手架欢迎页组件（TheWelcome 引用其余 6 个，因此整组一起移动） |
| `components/HelloWorld.vue`、`__tests__/HelloWorld.spec.ts` | 脚手架示例与它的测试 |
| `utils/permission.js` | 依赖不存在的用户状态字段（`stores/user` 的 `user.roles`），实际一直失效 |
| `utils/request.js` | 第三套 axios 客户端。最后一个引用它的 `views/ForumBoardView.vue` 只是 `import` 了却从未调用（死导入已删除），删除后全项目再无引用。**该文件本身还有一个缺陷**：拦截器读的是 `authStore.token`，而 store 暴露的字段是 `authToken`，所以它发出的请求从来不带 `Authorization` 头 |
| `api/auth.js`、`services/api.js` | 空壳/未使用的接口封装 |
| `plugins/markdown.js` | 未在任何地方注册 |
| `stores/counter.ts` | Vue 脚手架示例 store |
| `views/DetectionHistoryView.vue` | 「识别记录管理」页（路由 `/admin/detection-history`）。**第 22 批**把它与「历史记录」(`views/HistoryView.vue`) 合并为一个功能：管理员在 `/history` 用「查看全部用户」开关切换范围，能力（全部用户 / 按用户名搜索 / 批量删除 / 下载报告）都已并入。旧路由保留为重定向，`api/detection.js` 仍被合并后的页面使用（批量删除），故未移动 |

## 如何恢复

直接从本目录移回对应位置即可（相对路径与原来一致）。例如：

```powershell
Move-Item src\_deprecated\views\AuthView.vue src\views\AuthView.vue
```

若确认不再需要，可整个删除本目录：

```powershell
Remove-Item src\_deprecated -Recurse -Force
```

> ## ⚠️ 第 107 批的复核结论：**建议保留**（在拿到版本控制之前）
>
> 这份 README 当初写下的前提是"**项目没有可用的版本控制（`.git` 已损坏）**，
> 所以采用移动备份而不是删除"。第 107 批复核时确认：**这个前提仍然成立** ——
> 项目根下**没有 `.git` 目录**，也就是说这些文件是**唯一的一份副本**，
> 删掉不可恢复。
>
> 复核同时确认（逐文件比对了同名文件）：
> · `DiseaseStatistics.vue` 的**在用版本存在**（`src/components/DiseaseStatistics.vue`）；
> · 其余 7 个（`AuthView` / `PestopediaView` / `TinyMCE` / `CommentItem` /
>   `AuthDebug` / `request.js` / `permission.js`）**全项目只有这一份** ——
>   但它们都已被明确取代或本身就是坏的（见上表），所以"唯一副本"在这里
>   指"唯一的历史记录"，而不是"唯一还能用的实现"。
>
> **因此处置建议是**：
> 1. **先建立版本控制**（`git init` + 提交一次），然后**再**删这个目录 ——
>    这样"删除"变成可回滚的操作，而不是不可逆的；
> 2. 拿到版本控制后，本目录可以直接 `Remove-Item`，无需再逐文件甄别
>    （上表已经把每一个都交代过了）；
> 3. 在 1 完成之前，**不要**因为"审计说它注释为零"就删 —— 那是把
>    "临时安全网"当成"待清理垃圾"。
>
> 顺带说明：第 105 批的注释审计工具会把本目录排除在统计之外
> （`SKIP_PARTS` 里的 `_deprecated`），正是因为它已停用、
> 把它算进覆盖率只会用一个"已经不要了的代码"去污染"现存代码"的数字。
>
> > 原 README 结尾提到「`backend/api/views.py` 中还残留一份未被使用的 `NewsViewSet`」
> > —— **那份死代码已在第 106 批删除**（它永远不会被调用，却还留着一个
> > 已知必定 500 的 `def detail()`；回归测试用 AST 扫描保证只剩一份）。
