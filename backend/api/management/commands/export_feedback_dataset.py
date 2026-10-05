"""
导出「识别纠错」样本为可直接用于标注/训练的数据集（第 91 批）

==================================================================
为什么需要它
==================================================================
在这之前，用户点"识别不正确"留下的反馈**只能看，没法用**：

  · 反馈里没有"正确是哪一种"（只有 is_correct=false）→ 负反馈只能计数；
  · 反馈与那条识别记录没有关联（前端一直在传 detection_id，后端没这个字段）→
    找不回当时的原图与置信度；
  · 没有任何导出入口 → 想拿这些样本微调模型，只能靠人一条条从后台抄。

现在链路是通的，这个命令负责最后一步：把**人工确认过**的纠错导出成数据集。

==================================================================
⚠️ 关于标注质量：这里是"整图框"，不是精标
==================================================================
`DetectionHistory` 只存了原图与结论，**没有存检测框的坐标**（模型内部的 boxes
没有落库），所以本命令生成的 `labels/*.txt` 用的是**整图框**
（`class_id 0.5 0.5 1.0 1.0`）。

这意味着：

  * 它**可以**直接用来做"病害分类"训练（一张图 = 一个类别标签）；
  * 它**不适合**直接拿来微调检测模型（YOLO 检测需要真实框）；
    请把它当成"待标注队列"：图 + 建议标签已经配好，用 labelImg / CVAT 打开
    补上真实框即可，省掉"该给这张图打什么标签"的判断成本。

`manifest.csv` 里带上了 `model_prediction` 与 `confidence`，方便对比
"模型原来认成什么 / 人工纠正成什么"。

==================================================================
用法
==================================================================
    # 预览（不写文件），看会导出多少
    python manage.py export_feedback_dataset --dry-run

    # 真正导出到指定目录
    python manage.py export_feedback_dataset --out D:/dataset/corrections

    # 连"待确认"的一起导出（默认只导 confirmed）
    python manage.py export_feedback_dataset --out ... --include-pending

    # 导出后把 exported_at 打上时间戳（便于下次只导增量）
    python manage.py export_feedback_dataset --out ... --mark-exported

    # 只导某条反馈之后的新样本
    python manage.py export_feedback_dataset --out ... --since-id 120
"""
import csv
import logging
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.models import DetectionHistory, Feedback, PestInfo

logger = logging.getLogger(__name__)

#: 整图框（无真实检测框可用时的占位标注，见模块文档）
FULL_IMAGE_BBOX = (0.5, 0.5, 1.0, 1.0)


class Command(BaseCommand):
    help = '把「识别纠错」反馈导出成数据集（图片 + YOLO 格式标签 + manifest）'

    def add_arguments(self, parser):
        parser.add_argument('--out', type=str, default='',
                            help='输出目录（不存在会自动创建）')
        parser.add_argument('--dry-run', action='store_true',
                            help='只统计，不写任何文件')
        parser.add_argument('--include-pending', action='store_true',
                            help='连 verify_status=pending 的样本一起导出（默认只导已确认）')
        parser.add_argument('--mark-exported', action='store_true',
                            help='导出成功后给这些反馈打上 exported_at（用于下次导增量）')
        parser.add_argument('--since-id', type=int, default=0,
                            help='只导 id 大于该值的反馈（增量导出用）')
        parser.add_argument('--limit', type=int, default=0,
                            help='最多导出多少条（0 = 不限）')

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        out_dir = (options['out'] or '').strip()
        if not dry_run and not out_dir:
            raise CommandError('请用 --out 指定输出目录（或加 --dry-run 只看统计）')

        queryset = self._build_queryset(options)
        rows = list(queryset)
        if not rows:
            self.stdout.write(self.style.WARNING(
                '没有可导出的样本。\n'
                '提示：样本需要同时满足「category=recognition」+「is_correct=False」'
                '+「corrected_pest 非空」，且默认只导 verify_status=confirmed 的。\n'
                '查看当前进度：GET /api/admin/dataset-stats/'
            ))
            return

        self.stdout.write(f'找到 {len(rows)} 条可导出样本')
        if dry_run:
            self._print_preview(rows)
            self.stdout.write(self.style.WARNING('（--dry-run：未写任何文件）'))
            return

        stats = self._export(rows, Path(out_dir))
        self.stdout.write(self.style.SUCCESS(
            f'导出完成：{stats["images"]} 张图 / {stats["skipped"]} 条跳过（原图缺失）'
            f' → {out_dir}'
        ))
        self.stdout.write(f'  图片   : {stats["images_dir"]}')
        self.stdout.write(f'  标签   : {stats["labels_dir"]}（整图框，见 README.txt）')
        self.stdout.write(f'  清单   : {stats["manifest"]}')
        self.stdout.write(f'  类别表 : {stats["classes"]}')
        for warning in stats['warnings']:
            self.stdout.write(self.style.WARNING(f'  ⚠ {warning}'))

        if options['mark_exported']:
            ids = [row.id for row in rows]
            updated = Feedback.objects.filter(id__in=ids).update(exported_at=timezone.now())
            self.stdout.write(f'  已把 {updated} 条反馈标记为已导出（exported_at）')

    # ------------------------------------------------------------------
    def _build_queryset(self, options):
        qs = (
            Feedback.objects
            .filter(category='recognition', is_correct=False, corrected_pest__isnull=False)
            .select_related('detection', 'corrected_pest')
            .order_by('id')
        )
        if not options['include_pending']:
            qs = qs.filter(verify_status='confirmed')
        if options['since_id']:
            qs = qs.filter(id__gt=options['since_id'])
        if options['limit']:
            qs = qs[:options['limit']]
        return qs

    def _print_preview(self, rows):
        """dry-run 时把"会导出什么"摊开，避免闭眼跑一次才发现全被过滤掉了"""
        by_class = {}
        for row in rows:
            pest = row.corrected_pest
            key = getattr(pest, 'name_en', '') or pest.name
            by_class[key] = by_class.get(key, 0) + 1
        self.stdout.write('  按纠正后的类别：')
        for name, count in sorted(by_class.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'    {count:4d}  {name}')
        missing = [row for row in rows if not (row.detection and row.detection.image)]
        if missing:
            self.stdout.write(self.style.WARNING(
                f'  ⚠ {len(missing)} 条的原图已不存在（导出时会跳过）'
            ))

    def _export(self, rows, out_dir: Path):
        images_dir = out_dir / 'images'
        labels_dir = out_dir / 'labels'
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)

        # 类别表：以 PestInfo.english_identifier 为稳定名（与模型训练时的类别标签一致）
        classes = self._collect_classes(rows)
        class_index = {row['identifier']: index for index, row in enumerate(classes)}

        stats = {'images': 0, 'skipped': 0, 'warnings': []}
        manifest_rows = []

        for row in rows:
            detection = row.detection
            if detection is None or not detection.image:
                stats['skipped'] += 1
                continue

            pest = row.corrected_pest
            identifier = pest.english_identifier or f'pest_{pest.id}'
            class_id = class_index[identifier]

            # 图片按 feedback id 命名：可追溯，也不会与别的样本撞名
            suffix = Path(detection.image.name).suffix.lower() or '.jpg'
            image_name = f'fb{row.id:06d}{suffix}'
            label_name = f'fb{row.id:06d}.txt'

            try:
                with detection.image.open('rb') as source:
                    with (images_dir / image_name).open('wb') as target:
                        shutil.copyfileobj(source, target)
            except Exception as exc:  # noqa: BLE001  单条失败不该中断整批
                stats['skipped'] += 1
                stats['warnings'].append(f'反馈 #{row.id} 读图失败：{exc}')
                continue

            cx, cy, w, h = FULL_IMAGE_BBOX
            (labels_dir / label_name).write_text(
                f'{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n', encoding='utf-8',
            )

            manifest_rows.append({
                'feedback_id': row.id,
                'image': f'images/{image_name}',
                'label': f'labels/{label_name}',
                'class_id': class_id,
                'class_identifier': identifier,
                'class_name': pest.name,
                'class_name_en': pest.name_en or '',
                'model_prediction': detection.detection_result or '',
                'confidence': '' if detection.confidence is None else f'{detection.confidence:.4f}',
                'detection_id': detection.id,
                'detection_time': timezone.localtime(detection.timestamp).isoformat()
                if detection.timestamp else '',
                'user_note': (row.suggestion or '').strip(),
                'verify_status': row.verify_status,
            })
            stats['images'] += 1

        self._write_dataset_yaml(out_dir, classes)
        manifest_path = out_dir / 'manifest.csv'
        self._write_manifest(manifest_path, manifest_rows)
        self._write_readme(out_dir, classes, stats)

        stats.update({
            'images_dir': images_dir,
            'labels_dir': labels_dir,
            'manifest': manifest_path,
            'classes': out_dir / 'dataset.yaml',
        })
        return stats

    def _collect_classes(self, rows):
        """收集类别并排序（保证同一批数据每次导出的 class_id 一致）"""
        seen = {}
        for row in rows:
            pest = row.corrected_pest
            identifier = pest.english_identifier or f'pest_{pest.id}'
            if identifier not in seen:
                seen[identifier] = {
                    'identifier': identifier,
                    'name': pest.name,
                    'name_en': pest.name_en or '',
                }
        return [seen[key] for key in sorted(seen)]

    def _write_dataset_yaml(self, out_dir: Path, classes):
        lines = [
            '# 由 export_feedback_dataset 生成（识别纠错的人工确认样本）',
            '# names 的顺序即 class_id（0 起）。identifier 与模型训练时的标签一致，',
            '# 便于把这份数据与原始数据集合并。',
            'path: .',
            'train: images',
            'val: images',
            '',
            'names:',
        ]
        for index, item in enumerate(classes):
            label = item['identifier']
            cn = item['name']
            en = item['name_en']
            comment = f'  # {cn}' + (f' / {en}' if en else '')
            lines.append(f'  {index}: {label}{comment}')
        (out_dir / 'dataset.yaml').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def _write_manifest(self, path: Path, rows):
        fieldnames = [
            'feedback_id', 'image', 'label', 'class_id', 'class_identifier',
            'class_name', 'class_name_en', 'model_prediction', 'confidence',
            'detection_id', 'detection_time', 'user_note', 'verify_status',
        ]
        # utf-8-sig：Excel 直接双击打开不乱码
        with path.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _write_readme(self, out_dir: Path, classes, stats):
        text = f"""识别纠错数据集（由 export_feedback_dataset 生成）
================================================

导出时间：{timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}
样本数  ：{stats['images']}
类别数  ：{len(classes)}
跳过    ：{stats['skipped']}（原图已不存在）

目录
----
images/        原图（从识别记录里拷出来的那一张）
labels/        YOLO 格式标注
manifest.csv   每条样本的来源：feedback_id / 原模型结论 / 置信度 / 用户备注
dataset.yaml   类别表（names 的顺序即 class_id）

⚠️ 标注是"整图框"，不是精标
---------------------------
每行标签都是 `class_id 0.5 0.5 1.0 1.0`（整图一个框）。原因：识别记录只存了
原图与结论，**没有落库检测框坐标**。所以：

  * 做**病害分类**训练：可以直接用（一张图一个类别）。
  * 微调**检测**模型：需要真实的框，请把这份数据当"待标注队列" ——
    用 labelImg / CVAT 打开 images/，按 manifest.csv 里的 class_identifier
    补齐真实框后另存 labels/ 即可，省掉"该打什么标签"的判断成本。

类别表
------
"""
        for index, item in enumerate(classes):
            text += f"  {index}: {item['identifier']}  ({item['name']}"
            text += f" / {item['name_en']})\n" if item['name_en'] else ")\n"
        text += """
只导"人工确认过"的样本
----------------------
默认只导出 verify_status=confirmed 的（管理员在 Django admin 的反馈列表里
勾选确认）。要连待确认的一起导，加 `--include-pending`。

样本的源头是用户在识别结果页点"识别不正确"并选择了正确病害；
后台的"样本统计"接口能看当前攒了多少：
    GET /api/admin/dataset-stats/
"""
        (out_dir / 'README.txt').write_text(text, encoding='utf-8')
