# `backend/media/` —— 哪些入库、哪些不入库

> 第 109 批补。这个目录里**混着两类完全不同的东西**，所以"要不要进版本库"
> 不能一刀切 —— 这也是首次提交时把测试残渣一起收进来的原因。

## 口径

| 类别 | 例子 | 入库？ |
|---|---|---|
| **种子内容**（跨机器需要一致） | `pest_images/`（38 个病害图）、`news_images/`、`feedback_images/`、`detection_history/Apple___*.jpg` 等带日期的样例图 | ✅ **入库** |
| **运行期产物**（本机跑出来的） | `detection_history/det_*.jpg`（识别时的副本）、`detection_history/annotated_*.jpg`、`detection_uploads/`、非种子 `avatars/`、`consult_images/` | ❌ 忽略 |
| **帖子/富文本插图** | `uploads/`（由 `/api/upload/image/` 落盘） | ❌ 忽略 |

忽略规则写在 `backend/.gitignore`（末尾那一段），**不是**整个 `media/` ——
因为种子内容丢了，换台机器 clone 下来病害百科就没有配图了。

> ⚠️ 关于 `uploads/`：第 109 批我在 `.gitignore` 里把它写成"早期上传路径的遗留目录
> （当前代码零引用）"，**那是错的**。它由 `POST /api/upload/image/` 写入
> （见 `api/image_validation.py` 的用法示例），前端 `api/forum.js` 的
> `uploadImage()` 就在用 —— 帖子插图和富文本正文里的图都落在那里。
>
> 当时判断错的**原因**值得记下来：我查的是"数据库里有没有 FileField 引用它"，
> 而它的用途本来就是"先传图拿到 URL、再把 URL 写进正文"——
> **正文里的 URL 不是 FileField**，所以永远查不到引用。
> 这正好说明了本文件下面那条清理命令为什么必须有 `PRUNABLE_SUFFIXES` 白名单护栏。

## 为什么种子内容要入库

这个项目长期**没有版本控制**（第 109 批才建立），所以"能随时重建"的东西
和"丢了就没有"的东西混在一起。种子图属于后者：

- 病害图是配合 `add_detailed_pests` / `add_popular_pests` 灌进去的，
  那两条命令只写数据库、**不带图片**；图片不在库里就没有别的地方能拿到；
- E2E 的识别用例依赖 `media/detection_history/` 里有一张真实图片
  （`pickTestImage()` 找不到就会 `test.skip`）—— 数量、命中和体积都有讲究。

## 运行期产物怎么清

```bash
cd backend
python manage.py prune_media --min-age-days 7          # 干跑，只报告
python manage.py prune_media --min-age-days 7 --yes    # 真删
```

它会自动收集**所有** `FileField`/`ImageField` 的引用作为"保留集"，
所以新增带图片的模型不会被漏掉。默认干跑、默认只清 7 天前的
（正在上传、还没入库的文件看起来也像孤儿，不能和业务抢文件）。

### ⚠️ 它只删"看起来就是上传的媒体文件"（第 110 批补的护栏）

判"孤儿"的唯一依据是"没有任何 FileField 引用它"，而 `media/` 里
**天然不会被数据库引用**的东西恰恰最不能删。实测这个命令把
**本文件**（`media/README.md`）列进了待删名单，只差一个 `--yes` 就没了。

所以现在多了一道判据：只有扩展名在白名单里（`prune_media.PRUNABLE_SUFFIXES`：
常见图片/视频/文档/压缩包）才会被删；说明文档、脚本、配置一律不动。
选白名单而不是黑名单是因为**失效方向更安全** ——
遇到没预料到的类型，结果是"占点磁盘"而不是"文件没了"。

第 109/110 批用它清过两次：第一次 78 个孤儿 / 96.6 KB（`media/uploads/` 整个目录
当时被误判成遗留目录而清空 —— 那批文件确实是孤儿，但"目录是遗留的"这个判断是错的，
见上文）；第二次 26 个（识别测试留下的 `det_*.jpg`）。

### 测试不会再写真实 media（第 110 批修的）

跑 `manage.py test` 曾经会在这个目录里留下 `news_images/news_<随机>.png`、
`uploads/<随机>.jpg` —— 测试上传的文件，没有任何引用，还会被 `git add -A` 收进仓库
（首次提交时就这么混进了 98 个）。

根因已修：`settings.TEST_RUNNER` 指向 `api/test_runner.MediaIsolatedTestRunner`，
**整轮测试的 `MEDIA_ROOT` 指向临时目录**，跑完删掉。
实测：跑 43 条含上传的用例，真实 `media/` 文件数零变化。

> 已知的历史断链（不是清理造成的，第 106 批就记录过）：
> `detection_history/i18n-audit_placeholder_*.jpg` 共 10 条 ——
> 那是早期 i18n 审计脚本往数据库里写的占位记录，**当初就没在磁盘上建过文件**。
> 要修的话应当删掉这 10 条记录（它们没有对应的图，前端列表里是空图）。
