# `backend/media/` —— 哪些入库、哪些不入库

> 第 109 批补。这个目录里**混着两类完全不同的东西**，所以"要不要进版本库"
> 不能一刀切 —— 这也是首次提交时把测试残渣一起收进来的原因。

## 口径

| 类别 | 例子 | 入库？ |
|---|---|---|
| **种子内容**（跨机器需要一致） | `pest_images/`（38 个病害图）、`news_images/`、`feedback_images/`、`detection_history/Apple___*.jpg` 等带日期的样例图 | ✅ **入库** |
| **运行期产物**（本机跑出来的） | `detection_history/det_*.jpg`（识别时的副本）、`detection_history/annotated_*.jpg`、`detection_uploads/`、非种子 `avatars/`、`consult_images/` | ❌ 忽略 |
| **早期遗留** | `uploads/`（当前代码零引用的上传路径） | ❌ 忽略 |

忽略规则写在 `backend/.gitignore`（末尾那一段），**不是**整个 `media/` ——
因为种子内容丢了，换台机器 clone 下来病害百科就没有配图了。

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

第 109 批用它清理了一次：**78 个孤儿 / 96.6 KB**，`media/uploads/` 整个目录被清掉；
清理后校验过全部 126 条数据库引用，**没有一条因清理而失效**。

> 已知的历史断链（不是清理造成的，第 106 批就记录过）：
> `detection_history/i18n-audit_placeholder_*.jpg` 共 10 条 ——
> 那是早期 i18n 审计脚本往数据库里写的占位记录，**当初就没在磁盘上建过文件**。
> 要修的话应当删掉这 10 条记录（它们没有对应的图，前端列表里是空图）。
