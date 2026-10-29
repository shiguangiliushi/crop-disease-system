/**
 * 分享卡（第 239 批）
 * ============================================================================
 * 画一张 750×1000 的图（这里按 375×500 CSS 像素画，导出时由 canvas 自己放大），
 * 内容是"病害名 + 置信度 + 一句免责声明"。
 *
 * ## 为什么不像 H5 那样把识别照片也画进去
 *
 * H5 的 `shareCard.js` 会把照片画上去，但照片是 **http 远程图片**：
 *   · H5 里需要 `img.crossOrigin = 'anonymous'`，否则 canvas 被污染、`toDataURL` 直接抛异常；
 *   · 小程序里绘制远程图必须先 `uni.downloadFile` 拿到本地路径；
 *   · App 里又有自己的下载策略。
 * 三端各一套，且任何一处失败就是"分享卡生成失败"这种最差体验。
 * 所以 uni-app 版先做**纯文字卡**（仍然能说明"是什么病、把握多大"），
 * 照片等真机验证过 downloadFile 链路后再加。
 */
const CARD_W = 375
const CARD_H = 500

function wrap(ctx, text, maxWidth) {
  // 简易折行：按字符宽度累计（中文场景够用），超过就换行
  const lines = []
  let line = ''
  for (const char of String(text || '')) {
    const next = line + char
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line)
      line = char
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

/**
 * 生成分享卡，返回临时文件路径（H5 是 dataURL，App/小程序是临时文件）
 *
 * @param {{canvasId: string, disease: string, diseaseEn?: string, confidence?: number,
 *          footer: string, labels: {confidence: string}}} options
 */
export function makeShareCard({ canvasId, disease, diseaseEn = '', confidence = 0, footer, labels }) {
  return new Promise((resolve, reject) => {
    let ctx
    try {
      ctx = uni.createCanvasContext(canvasId)
    } catch (error) {
      reject(new Error('当前环境不支持生成分享卡'))
      return
    }

    const percent = (() => {
      const value = Number(confidence) || 0
      const ratio = value > 1 ? value / 100 : value
      return `${Math.round(ratio * 100)}%`
    })()

    // 背景
    ctx.setFillStyle('#f2f7f3')
    ctx.fillRect(0, 0, CARD_W, CARD_H)
    // 顶部色块
    ctx.setFillStyle('#2f855a')
    ctx.fillRect(0, 0, CARD_W, 92)
    ctx.setFillStyle('#ffffff')
    ctx.setFontSize(20)
    ctx.setTextAlign('center')
    ctx.fillText('农作物病害识别', CARD_W / 2, 56)

    // 病害名（可能很长，折行）
    ctx.setTextAlign('left')
    ctx.setFillStyle('#1f2d26')
    ctx.setFontSize(30)
    const titleLines = wrap(ctx, disease, CARD_W - 64).slice(0, 3)
    titleLines.forEach((line, index) => {
      ctx.fillText(line, 32, 170 + index * 42)
    })

    let cursor = 170 + titleLines.length * 42
    if (diseaseEn) {
      ctx.setFontSize(16)
      ctx.setFillStyle('#8b9a91')
      ctx.fillText(diseaseEn, 32, cursor + 8)
      cursor += 28
    }

    // 置信度
    ctx.setFillStyle('#2f855a')
    ctx.setFontSize(44)
    ctx.fillText(percent, 32, cursor + 64)
    ctx.setFillStyle('#8b9a91')
    ctx.setFontSize(16)
    ctx.fillText(labels?.confidence || '', 32, cursor + 92)

    // 免责声明
    ctx.setFillStyle('#8b9a91')
    ctx.setFontSize(14)
    wrap(ctx, footer, CARD_W - 64).slice(0, 4).forEach((line, index) => {
      ctx.fillText(line, 32, CARD_H - 96 + index * 22)
    })

    ctx.draw(false, () => {
      // draw 是异步的，稍等一下再导出；H5 端实测 50~100ms 足够
      setTimeout(() => {
        uni.canvasToTempFilePath({
          canvasId,
          width: CARD_W,
          height: CARD_H,
          destWidth: CARD_W * 2,
          destHeight: CARD_H * 2,
          success: (res) => resolve(res.tempFilePath),
          fail: (error) => reject(new Error(error?.errMsg || '导出图片失败')),
        })
      }, 120)
    })
  })
}
