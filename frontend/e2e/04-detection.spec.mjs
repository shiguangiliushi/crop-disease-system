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
  djangoSession,
  expectThat,
  login,
  gotoAuthed,
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

/**
 * 常驻 Django 会话（第 109 批）。
 *
 * ⚠️ 为什么不用现成的 `runDjango()`：它每次都新起一个 Python 进程 + `django.setup()`，
 * 而这个项目装了 torch，**单次要 40 秒**（实测）。第 109 批加计时打点后看清了：
 *
 *     分步耗时：准备 42.6s｜页面打开 6.5s｜等待结果 1.0s
 *               （其中 maxDetectionId 36119ms）
 *
 * 也就是**被测功能只用 1 秒**，其余全是"启 Python 查一下数据库"。
 * 这种开销会把"真的变慢"和"环境慢"混在一起 —— 没有打点根本分不清。
 *
 * 常驻会话只付一次启动成本，之后的查询是毫秒级（实测第二次 0.00s）。
 */
let session = null;

function openSession() {
  if (!session) session = djangoSession();
  return session;
}

/** 当前识别记录里最大的 id（异步 —— 会话是异步的） */
async function maxDetectionId() {
  const raw = await openSession().run([
    'from api.models import DetectionHistory',
    'print(DetectionHistory.objects.order_by("-id").values_list("id", flat=True).first() or 0)',
  ]);
  const match = /(\d+)/.exec(raw);
  return match ? Number(match[1]) : 0;
}

/**
 * 删掉 id 大于 `since` 的记录（= 这次跑新产生的），并把它们记进待清理列表。
 * 返回这次新产生的**条数**。
 */
async function collectNewDetections(since) {
  const before = createdDetectionIds.length;
  const raw = await openSession().run([
    'from api.models import DetectionHistory',
    `print(",".join(str(i) for i in DetectionHistory.objects.filter(id__gt=${since}).values_list("id", flat=True)))`,
  ]);
  const ids = raw.split(',').filter(Boolean).map(Number);
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

  /**
   * 先给后端"热一次身"（第 109 批）。
   *
   * ⚠️ 为什么需要这一步：识别接口**第一次真实推理要 21 秒**
   *    （模型加载 5.5s + 首次推理 21s，之后每次 0.8s）。后端第 107 批加了启动预热
   *    （`apps.ready()` → `ai_service.warm_up()`），但**只有后端是在预热之后启动的**
   *    才有效 —— 而本地开发常拿 `AI_WARMUP_ON_STARTUP=False` 启（省启动时间）。
   *
   * 症状：本 spec 里"走接口"的用例先跑、顺手热了身，而**走界面的那条**
   * 如果排在前面（或单独跑），就会独自承担 26 秒冷启动 ——
   * 实测那条用例耗时 **45.3 秒**，而接口本身只用 0.4 秒。
   * 诊断时间线（浏览器直连）确认过：预热之后从点击到出结果是 **2.4 秒**。
   *
   * 所以在 beforeAll 里显式热一次身：**测试要测的是"功能对不对"，
   * 不该把"后端是否已预热"这种环境差异混进来**。
   * 用 `test.skip` 之外的兜底：预热失败不报错（后面用例自己会红，且信息更明确）。
   */
  test.beforeAll(async () => {
    const image = pickTestImage();
    if (!image) return;
    try {
      const session = await login();
      const form = new FormData();
      form.append('image', new File([readFileSync(image.path)], image.name, { type: 'image/jpeg' }));
      const response = await fetch('http://127.0.0.1:8000/api/detect/', {
        method: 'POST',
        headers: { Authorization: `Token ${session.token}` },
        body: form,
      });
      if (response.ok) {
        const payload = await response.json();
        const id = (payload?.data ?? payload)?.history_id;
        if (Number.isInteger(id)) createdDetectionIds.push(id);
        console.log('  ↳ 预热推理完成（这次请求承担了冷启动）');
      }
    } catch (error) {
      console.log('  ↳ 预热失败（不影响用例，只是第一条会慢）:', String(error).slice(0, 120));
    }
  });

  test.afterAll(() => {
    // 关掉常驻 Django 会话：不关会留下一个挂着 torch 的 Python 进程，
    // 而 Playwright 会等子进程结束才退出 —— 表现为整轮测试跑完却不退出。
    if (session) {
      session.close();
      session = null;
    }
    cleanupByPrefix();
    // 把清理结果打出来：清理失败时最需要看的就是"哪些 id、删了几个文件"
    console.log('  ↳ 待清理的识别记录：', JSON.stringify(createdDetectionIds));
    console.log('  ↳ 清理结果：', String(cleanupDetections(createdDetectionIds)).replace(/\n/g, ' | '));
  });

  test('上传图片能拿到识别结果（置信度与病害名都在）', async () => {
    // 第 109 批：走推理的用例都要放宽上限（冷启动实测 26 秒），理由见下面那条用例的说明
    test.setTimeout(180_000);

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
    // ⚠️ 第 109 批：这条用例**必须给自己放宽上限**。
    //
    // 它走的是完整推理链路，而**识别接口有冷启动**：实测第一次真实
    // 推理要 21 秒（模型加载 5.5s + 首次推理 21s），之后每次 0.8s。
    // 后端第 107 批加了启动预热（`apps.ready()` → `ai_service.warm_up()`），
    // 所以**只要后端是在预热之后启动的**，这里通常 1~2 秒就出结果。
    //
    // 但有两种情况会栽在默认的 45 秒上：
    //   · 后端是用 `AI_WARMUP_ON_STARTUP=False` 启的（省启动时间）；
    //   · 这台机器同时在跑别的东西（实测：并发跑两轮 E2E 时超时）。
    // 报错形态是 `page.waitForTimeout: Test timeout of 45000ms exceeded` ——
    // 一眼看不出是"功能坏了"还是"冷启动 + 机器忙"，所以这里显式给足时间，
    // 让失败重新变成"有信息量"的信号。
    test.setTimeout(180_000);

    const image = pickTestImage();
    test.skip(!image, '没有可用的测试图片');

    // ⚠️ 这几行**必须在 goto 之前**：它们把登录态注入浏览器存储。
    //    第 109 批我在给这条用例加计时打点时，误把这三行一起替换掉了 ——
    //    结果 sessionStorage 是空的，路由守卫把用例踢到
    //    `/login?redirect=/detect&reason=loginRequired`，
    //    表现为"重试 3 次都停在登录页"，而截图里那个登录页**完全是空的**
    //    （应用还没挂载）。查了很久才回到"是不是 loginAs 没调用"这个最基本的问题。
    //    教训：给用例做"结构性编辑"时，先数一遍原来有几行、少了什么。
    const session = await login();
    const errors = watchPageErrors(page);
    await loginAs(page, session);

    // ⚠️ 第 109 批：给这条用例的分步耗时打点。
    //    它一度耗时 45 秒~1.4 分钟，而**同样的流程用浏览器直连只要 2.4 秒**
    //    （诊断脚本实测时间线），接口本身只用 0.4 秒。
    //    没有分步计时就只能对着一个总时长猜，所以这里把每一步的耗时打出来 ——
    //    排查变慢时这几行日志比任何推断都直接（就像第 106 批发现
    //    "识别接口冷启动 26 秒"也是靠分解时间线才定位到"首次推理 21 秒"）。
    const t = {};
    const tick = (name) => { t[name] = Date.now(); };
    const span = (name, from) => `${name} ${((Date.now() - t[from]) / 1000).toFixed(1)}s`;

    tick('start');
    const baseline = await maxDetectionId();
    const baselineMs = Date.now() - t.start;

    tick('goto');
    await gotoAuthed(page, '/detect');
    await page.waitForTimeout(1500);

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
    tick('click');
    await startBtn.click();

    // ⚠️ 等"结果出现"，不要睡固定秒数：CPU 推理时长波动，睡 5s 会假红、睡 30s 又太慢
    const appeared = await page.waitForSelector(
      '.results-container, .result-detail-card, .confidence-chip',
      { timeout: 90000 },
    ).then(() => true).catch(() => false);
    expectThat('结果区域渲染出来了', appeared, true);
    console.log(`  ↳ 分步耗时：${span('准备', 'start')}｜${span('页面打开', 'goto')}｜`
      + `等待结果 ${((Date.now() - t.click) / 1000).toFixed(1)}s（其中 maxDetectionId ${baselineMs}ms）`);

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
    const newCount = await collectNewDetections(baseline);
    expectThat('界面识别也确实落库了', newCount >= 1, true);

    assertNoProblems();
  });

  test('结果页的"纠错"能落库（成为训练样本的一部分）', async () => {
    // 第 109 批：走推理的用例都要放宽上限（冷启动实测 26 秒），理由见上面那条用例的说明
    test.setTimeout(180_000);

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
