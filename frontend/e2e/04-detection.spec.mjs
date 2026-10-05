/**
 * 识别流程：上传图片 → 出结果 → 反馈纠错（第 104 批）
 * ============================================================================
 * 这是本系统**最核心的一条链路**，也是此前唯一只有"一次性脚本"的大块：
 * 之前验证它要临时写脚本、手动找图、跑完删掉，改一次代码就得重来一遍。
 *
 * 这条链路值得常驻回归的原因：
 *   · 它跨了 4 层（前端表单 → DRF MultiPartParser → YOLO 推理 → 结果序列化），
 *     任何一层改动都可能弄坏它，而**只有真跑一次才知道**；
 *   · 推理是 CPU 密集的，偶尔会慢 —— 一次性脚本里的固定 sleep 经常假红，
 *     这里用"等结果元素出现"而不是睡固定时间；
 *   · 第 92 批加了"纠错 → 训练样本池"（`corrected_pest_id`），
 *     那条链路（结果页选正确病害 → 反馈进库）同样只有跑一次才知道有没有断。
 *
 * ⚠️ 依赖真实图片：从 `media/detection_history/` 里挑一张已存在的（不新造二进制），
 *    拿不到时**明确跳过并说明**，而不是让整条链路假绿。
 */
import { test, expect } from '@playwright/test';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  api,
  assertNoProblems,
  BACKEND_DIR,
  cleanupByPrefix,
  cleanupDetections,
  expectThat,
  login,
  loginAs,
  resetChecks,
  runDjango,
  TEMP_PREFIX,
  watchPageErrors,
} from './helpers.mjs';

/**
 * 这一轮跑出来的识别记录 id —— 用例结束要删掉。
 *
 * ⚠️ 识别记录没法按前缀清（`detection_result` 存的是模型预测的病害名，不是我们造的数据），
 *    所以必须自己记 id。第一版没记，实测**每跑一次就多留一条记录 + 两张上传图**
 *    （media/detection_uploads 里的 `annotated_*.JPG` 一直在涨）。
 */
const createdDetectionIds = [];

/** 当前识别记录里最大的 id（用来圈定"这次跑新产生的记录"） */
function maxDetectionId() {
  const raw = runDjango([
    'from api.models import DetectionHistory',
    'print("MAX_ID=" + str(DetectionHistory.objects.order_by("-id").values_list("id", flat=True).first() or 0))',
  ]);
  const match = /MAX_ID=(\d+)/.exec(raw);
  return match ? Number(match[1]) : 0;
}

/** 删掉 id 大于 `since` 的记录（= 这次跑新产生的），并把它们记进待清理列表 */
function collectNewDetections(since) {
  const before = createdDetectionIds.length;
  const raw = runDjango([
    'from api.models import DetectionHistory',
    `print("NEW_IDS=" + ",".join(str(i) for i in DetectionHistory.objects.filter(id__gt=${since}).values_list("id", flat=True)))`,
  ]);
  const match = /NEW_IDS=([\d,]*)/.exec(raw);
  const ids = (match?.[1] || '').split(',').filter(Boolean).map(Number);
  createdDetectionIds.push(...ids);
  return createdDetectionIds.length - before;
}

/** 找一张"够小、够真"的测试图（太大的图在 CPU 上推理会拖到超时） */
function pickTestImage() {
  const dir = resolve(BACKEND_DIR, 'media/detection_history');
  let names = [];
  try {
    names = readdirSync(dir);
  } catch {
    return null;
  }
  const candidate = names
    .filter((n) => /\.(jpe?g|png)$/i.test(n))
    .map((n) => ({ name: n, path: resolve(dir, n), size: statSync(resolve(dir, n)).size }))
    .filter((f) => f.size > 10 * 1024 && f.size < 800 * 1024)
    .sort((a, b) => a.size - b.size)[0];
  return candidate || null;
}

test.describe('识别流程', () => {
  test.beforeEach(() => resetChecks());
  test.afterAll(() => {
    cleanupByPrefix();
    // 把清理结果打出来：清理失败时最需要看的就是"哪些 id、删了几个文件"
    console.log('  ↳ 待清理的识别记录：', JSON.stringify(createdDetectionIds));
    console.log('  ↳ 清理结果：', String(cleanupDetections(createdDetectionIds)).replace(/\n/g, ' | '));
  });

  test('上传图片能拿到识别结果（置信度与病害名都在）', async () => {
    const image = pickTestImage();
    test.skip(!image, 'media/detection_history 里没有可用的测试图片（先跑一次识别或放一张图）');

    const session = await login();
    const bytes = readFileSync(image.path);
    const form = new FormData();
    form.append('image', new File([bytes], image.name, { type: 'image/jpeg' }));

    const started = Date.now();
    const response = await fetch('http://127.0.0.1:8000/api/detect/', {
      method: 'POST',
      headers: { Authorization: `Token ${session.token}` },
      body: form,
    });
    const elapsed = Date.now() - started;
    expectThat('识别接口 HTTP 200', response.status, 200);

    // ⚠️ 真实的响应形状（别照着想象写）：
    //    { status: 'success',
    //      data: { detection: { disease, disease_en, confidence, description,
    //                           prevention, original_image, annotated_image, bbox },
    //              history_id: 949 } }
    //    是**单个** detection 对象（不是 diseases 数组）—— 前端 DetectView 自己把它
    //    包成数组给结果卡片用。第一版按 `data.diseases` 断言，直接
    //    `Cannot read properties of undefined (reading '0')`。
    const data = (await response.json())?.data ?? {};
    const detection = data.detection;
    expectThat('返回里有 detection 对象', typeof detection, 'object');
    expectThat('带了识别记录的 history_id', typeof data.history_id, 'number');
    if (Number.isInteger(data.history_id)) createdDetectionIds.push(data.history_id);

    expectThat('结果带病害名', typeof detection?.disease === 'string' && detection.disease.length > 0, true);
    expectThat('置信度是 0~1 的数', typeof detection?.confidence === 'number'
      && detection.confidence >= 0 && detection.confidence <= 1, true);
    expectThat('给了原图地址', typeof detection?.original_image === 'string'
      && detection.original_image.length > 0, true);

    // 这条主要用来发现"某次改动把推理拖慢到不可用"（CPU 上正常在 20s 内）
    expectThat('推理耗时可接受（< 60s）', elapsed < 60000, true);
    console.log(`  ↳ 识别耗时 ${(elapsed / 1000).toFixed(1)}s，`
      + `病害：${detection.disease}（${(detection.confidence * 100).toFixed(1)}%），`
      + `history_id=${data.history_id}`);
    assertNoProblems();
  });

  test('识别页能上传并渲染出结果卡片', async ({ page }) => {
    const image = pickTestImage();
    test.skip(!image, '没有可用的测试图片');

    const session = await login();
    const errors = watchPageErrors(page);
    await loginAs(page, session);

    // ⚠️ 这条用例走的是**界面上传**，拿不到接口返回的 history_id。而识别记录
    //    没法按名字清（`detection_result` 是模型预测的病害名）—— 所以先记下"当前最大 id"，
    //    跑完把新出现的 id 圈出来一起清掉。第一版没做，实测每次跑完都多留 1 条记录 + 2 张图。
    const baseline = maxDetectionId();

    await page.goto('/detect');
    await page.waitForTimeout(2000);

    // ⚠️ 页面上的 file input 是 **hidden** 的（`class="d-none"`，由"拍照/从相册选"
    //    两个按钮转发点击触发）。`setInputFiles` 对隐藏 input 有效，不需要点系统对话框 ——
    //    第一版等的是"可见的 input[type=file]"，20s 超时。
    //    第一个 input 是相册入口（`ref="fileInput"`），第二个是拍照入口（`capture`）。
    const fileInputs = page.locator('input[type="file"]');
    expectThat('页面上有文件输入（隐藏）', await fileInputs.count() >= 1, true);
    await fileInputs.first().setInputFiles(image.path);
    await page.waitForTimeout(1500);

    const startBtn = page.locator('button', { hasText: /开始识别|开始检测/ }).first();
    expectThat('找到"开始识别"按钮', await startBtn.count() > 0, true);
    await startBtn.click();

    // ⚠️ 等"结果出现"，不要睡固定秒数：CPU 推理时长波动，睡 5s 会假红、睡 30s 又太慢
    const appeared = await page.waitForSelector(
      '.results-container, .result-detail-card, .confidence-chip',
      { timeout: 90000 },
    ).then(() => true).catch(() => false);
    expectThat('结果区域渲染出来了', appeared, true);

    if (appeared) {
      const text = await page.locator('body').innerText();
      // ⚠️ 不要断言"页面上有'置信度'三个字"：实际 UI 里那个数字是通过
      //    `confidenceText()` 算出来的**可读判断**（"很可能/较可能…"）+ 百分比徽章，
      //    并没有"置信度"这个词（实测断言红了，而功能是好的）。
      //    要验的是"结果区渲染出来了 + 有个百分比"，这才是用户能看到的证据。
      expectThat('出现百分比数字', /\d+(\.\d+)?\s*%/.test(text), true);
      expectThat('出现"识别结果"标题', /识别结果/.test(text), true);

      const containerCount = await page.locator('.results-container').count();
      expectThat('结果容器存在', containerCount >= 1, true);

      // 结果详情卡里应当有"病害详情"这一节（`filteredDiseases` 为空时这节不渲染 ——
      // 那说明识别出的病害名在本地病害库里匹配不上，属于**数据问题**，值得暴露出来）
      const detailCount = await page.locator('.result-detail-card').count();
      expectThat('渲染出结果详情卡', detailCount >= 1, true);

      const nameCount = await page.locator('.detect-disease-name').count();
      if (nameCount === 0) {
        console.log('  ⚠ 结果详情里没有病害名节点：识别出的病害在本地病害库里匹配不上'
          + '（数据问题，不是渲染坏了）');
      }
    }

    expectThat(`没有 JS 报错（实际：${JSON.stringify(errors.slice(0, 3))}）`, errors.length, 0);

    // 把界面这次产生的识别记录也纳入清理（并顺带确认"确实落库了"）
    const newCount = collectNewDetections(baseline);
    expectThat('界面识别也确实落库了', newCount >= 1, true);

    assertNoProblems();
  });

  test('结果页的"纠错"能落库（成为训练样本的一部分）', async () => {
    const image = pickTestImage();
    test.skip(!image, '没有可用的测试图片');

    const session = await login();

    // ① 先跑一次识别，拿到一条 detection 记录（结果页的纠错是挂在它上面的）
    const bytes = readFileSync(image.path);
    const form = new FormData();
    form.append('image', new File([bytes], image.name, { type: 'image/jpeg' }));
    const detected = await fetch('http://127.0.0.1:8000/api/detect/', {
      method: 'POST',
      headers: { Authorization: `Token ${session.token}` },
      body: form,
    }).then((r) => r.json());
    // 记录 id 在 `data.history_id`（不是 detection_id —— 那是 Feedback 上的字段名）
    const detectionId = (detected?.data ?? detected)?.history_id;
    expectThat('识别接口回传了记录 id', typeof detectionId === 'number', true);
    if (Number.isInteger(detectionId)) createdDetectionIds.push(detectionId);

    // ② 拿一个真实病害作为"正确病害"
    const pests = await api('/api/pests/?page_size=1', { token: session.token });
    const pest = (pests.json?.results ?? pests.json)?.[0];
    expectThat('能取到一个病害供纠错选择', typeof pest?.id === 'number', true);

    // ③ 提交纠错（第 92 批：带上 corrected_pest_id 才进得了训练样本池）
    const feedback = await api('/api/feedback/', {
      method: 'POST',
      token: session.token,
      body: {
        suggestion: `${TEMP_PREFIX} 识别不准确`,
        category: 'recognition',
        is_correct: false,
        detection_id: detectionId,
        corrected_pest_id: pest.id,
      },
    });
    expectThat('纠错提交成功', feedback.status === 201 || feedback.status === 200, true);

    // ④ 读回来确认两个关联都在（这才是"能进样本池"的硬证据）
    const id = (feedback.json?.id) ?? (feedback.json?.data?.id);
    if (typeof id === 'number') {
      const readBack = await api(`/api/feedback/${id}/`, { token: session.token });
      expectThat('回读到了这条反馈', readBack.status, 200);
      expectThat('关联了识别记录', readBack.json?.detection_id, detectionId);
      expectThat('关联了正确病害', readBack.json?.corrected_pest_id, pest.id);
      expectThat('可训练样本标记为真', readBack.json?.is_trainable, true);
      // 清理
      await api(`/api/feedback/${id}/`, { method: 'DELETE', token: session.token });
    }

    assertNoProblems();
  });

  test('未登录不能识别（识别接口不是公开的）', async () => {
    const { status } = await api('/api/detect/', {
      method: 'POST',
      body: { nothing: true },
    });
    expectThat('匿名 POST 被拒（401/403）', status === 401 || status === 403, true);
    assertNoProblems();
  });
});
