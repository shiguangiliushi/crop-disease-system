/**
 * 上传前压缩（第 239 批）
 *
 * 现有 H5 用 canvas 重编码（`mobile/src/utils/image.js`），那套在 uni-app 里不通用：
 *   · 小程序/App 没有 DOM canvas 的 `toBlob`；
 *   · 但 uni 提供了跨端的 `uni.compressImage`。
 * 所以这里的策略是"**优先用 uni.compressImage，失败就原样上传**"：
 * 压缩是优化项，压不了不该让用户传不了图（后端还有 5MB 校验兜底）。
 */
const COMPRESS_QUALITY = 80

export function canCompress() {
  return typeof uni.compressImage === 'function'
}

/**
 * @param {string} path `uni.chooseImage` 给的临时路径
 * @returns {Promise<string>} 压缩后的路径；不支持/失败时返回原路径（不抛异常）
 */
export async function compressForUpload(path) {
  if (!path || !canCompress()) return path
  return new Promise((resolve) => {
    uni.compressImage({
      src: path,
      quality: COMPRESS_QUALITY,
      success: (res) => resolve(res.tempFilePath || path),
      fail: (error) => {
        console.warn('[image] 压缩失败，改用原图', error?.errMsg || error)
        resolve(path)
      },
    })
  })
}

/** 文件大小（拿不到就返回 0，调用方据此跳过校验） */
export function fileSizeOf(path) {
  return new Promise((resolve) => {
    if (typeof uni.getFileInfo !== 'function') {
      resolve(0)
      return
    }
    uni.getFileInfo({
      filePath: path,
      success: (res) => resolve(res.size || 0),
      fail: () => resolve(0),
    })
  })
}
