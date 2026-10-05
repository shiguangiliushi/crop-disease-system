import os
import sys
import time
import torch
import tempfile
import base64
import logging
import threading
import numpy as np
from io import BytesIO
from PIL import Image
from django.conf import settings
from ultralytics import YOLO

# 确保torch使用CPU（如果需要）
if not torch.cuda.is_available():
    torch.set_num_threads(4)  # 限制CPU线程数以减少内存使用

# 配置日志
logger = logging.getLogger(__name__)

#: 模型加载 / 预热的互斥锁（第 113 批）
#:
#: 为什么需要它：第 113 批把启动预热改成**后台线程**（它原来同步跑，
#: 会让服务在 30 秒里完全不监听端口，甚至卡住起不来 —— 见 `apps.py` 的说明）。
#: 于是出现了新的并发窗口：**预热线程刚起来的那一瞬间，正好来了一个识别请求**，
#: 两边会同时去走 `YOLO(model_path)`。
#:
#: 后果不是"慢一点"，而是：加载两份 6MB 权重（内存翻倍）、
#: 两个 torch 前向同时跑（CPU 抢线程、都变慢），
#: 而且在极端情况下 torch 的延迟初始化不是线程安全的。
#:
#: 用一把模块级锁把"加载并预热"串起来：后来者等前面做完，直接复用已就绪的模型。
_WARMUP_LOCK = threading.Lock()


class AIService:
    _instance = None
    model = None

    # 恢复手动定义的类别名称列表
    class_names = [
        'Apple___Apple_scab', 'Apple___Black_rot', 'Apple___Cedar_apple_rust', 'Apple___healthy',
        'Blueberry___healthy', 'Cherry___healthy', 'Cherry___Powdery_mildew',
        'Corn___Cercospora_leaf_spot Gray_leaf_spot', 'Corn___Common_rust', 'Corn___healthy',
        'Corn___Northern_Leaf_Blight', 'Grape___Black_rot', 'Grape___Esca_(Black_Measles)',
        'Grape___healthy', 'Grape___Leaf_blight_(Isariopsis_Leaf_Spot)',
        'Orange___Haunglongbing_(Citrus_greening)', 'Peach___Bacterial_spot', 'Peach___healthy',
        'Pepper,_bell___Bacterial_spot', 'Pepper,_bell___healthy', 'Potato___Early_blight',
        'Potato___healthy', 'Potato___Late_blight', 'Raspberry___healthy', 'Soybean___healthy',
        'Squash___Powdery_mildew', 'Strawberry___healthy', 'Strawberry___Leaf_scorch',
        'Tomato___Bacterial_spot', 'Tomato___Early_blight', 'Tomato___healthy', 'Tomato___Late_blight',
        'Tomato___Leaf_Mold', 'Tomato___Septoria_leaf_spot',
        'Tomato___Spider_mites Two-spotted_spider_mite', 'Tomato___Target_Spot',
        'Tomato___Tomato_mosaic_virus', 'Tomato___Tomato_Yellow_Leaf_Curl_Virus'
    ]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIService, cls).__new__(cls)
            try:
                # 使用相对路径，避免路径问题
                model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'newmodels', 'best.pt')
                # 如果newmodels目录下没有，则尝试models目录
                if not os.path.exists(model_path):
                    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', 'best.pt')
                logger.info(f"尝试从以下位置加载模型: {model_path}")

                if not os.path.exists(model_path):
                    error_msg = f"模型文件不存在: {model_path}"
                    logger.error(error_msg)
                    return cls._instance

                file_size = os.path.getsize(model_path) / (1024 * 1024)
                logger.info(f"模型文件大小: {file_size:.2f} MB")

                # 记录模型文件大小，但不限制最小大小
                if file_size < 5:  # 保留一个基本的大小检查，防止空文件
                    error_msg = f"模型文件大小异常: {file_size:.2f} MB，可能已损坏"
                    logger.error(error_msg)
                    return cls._instance

                try:
                    # ⚠️ 第 107 批：这行注释原来写"清除torch hub缓存"，但
                    #    `torch.hub.set_dir()` **不清缓存**，它只是改下载目录。
                    #    真实意图是：别让 ultralytics/torch 往**应用目录**里写权重缓存
                    #    （只读部署、容器、以及"跑完发现多出一堆文件"都会中招），
                    #    统一丢到系统临时目录。已按实际行为改写注释。
                    torch.hub.set_dir(tempfile.gettempdir())
                    logger.info("torch hub 下载目录已指向临时目录（避免写入应用目录）")

                    # 使用YOLOv8接口加载模型
                    logger.info("开始加载YOLOv8模型...")
                    cls.model = YOLO(model_path)
                    logger.info(f"成功从 {model_path} 加载YOLOv8模型")
                    
                    # 测试模型是否可以预测
                    test_img = torch.zeros((1, 3, 640, 640))  # 创建一个测试张量
                    results = cls.model(test_img, verbose=False)  # 添加verbose=False减少输出
                    logger.info("模型预测测试成功")
                    
                except Exception as e:
                    logger.error(f"加载YOLOv8模型时出错: {str(e)}", exc_info=True)
                    logger.error("详细错误信息:", exc_info=True)
                    return cls._instance

                logger.info("模型加载成功")
                return cls._instance

            except Exception as e:
                error_msg = f"AI服务初始化失败: {str(e)}"
                logger.error(error_msg, exc_info=True)
                cls.model = None
                cls._instance = None  # 确保下次可以重试
                return None
                
        return cls._instance

    def _extract_crop_type(self, image_file):
        """尝试从文件名或图像内容中提取作物类型"""
        try:
            # 从文件名中提取作物类型
            filename = getattr(image_file, 'name', '').lower()
            for crop in ['corn', 'apple', 'tomato', 'potato', 'grape', 'cherry', 'peach', 'pepper', 'strawberry']:
                if crop in filename:
                    return crop
            return 'plant'  # 默认返回'plant'如果无法确定具体作物
        except Exception as e:
            logger.warning(f"提取作物类型时出错: {e}")
            return 'plant'

    def predict(self, image_file):
        if self.model is None:
            error_msg = "模型未加载，无法进行预测。"
            logger.error(error_msg)
            return {'status': 'error', 'message': error_msg}

        try:
            # 记录文件信息
            file_info = {
                'name': getattr(image_file, 'name', 'unknown'),
                'size': getattr(image_file, 'size', 'unknown'),
                'content_type': getattr(image_file, 'content_type', 'unknown'),
            }
            logger.info(f"开始处理图像: {file_info}")

            # 打开并转换图像
            try:
                img = Image.open(image_file)
                logger.info(f"成功打开图像: 格式={img.format}, 大小={img.size}, 模式={img.mode}")
                img = img.convert('RGB')
                logger.info(f"转换图像为RGB模式: 大小={img.size}, 模式={img.mode}")
            except Exception as img_error:
                error_msg = f"图像处理失败: {str(img_error)}"
                logger.error(error_msg, exc_info=True)
                return {'status': 'error', 'message': '无法处理图像文件，请确保上传的是有效的图片文件。'}

            # 保存临时文件路径（如果需要）
            temp_file_path = None
            try:
                # 如果image_file是InMemoryUploadedFile，保存到临时文件
                if hasattr(image_file, 'temporary_file_path'):
                    temp_file_path = image_file.temporary_file_path()
                elif hasattr(image_file, 'read'):
                    # 创建临时文件
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                        img.save(tmp_file, format='JPEG')
                        temp_file_path = tmp_file.name

                # 执行预测
                start_time = time.time()
                results = self.model(img, verbose=False)  # 添加verbose=False减少输出
                inference_time = time.time() - start_time

                # ⚠️ 第 107 批修：这一行原来把**整个 results 对象**插进日志
                #    （`结果: {results}`），而 ultralytics 的 Results 的 repr
                #    会把整张 640×640×3 的像素数组、39 个类别名、原始图像路径全部打印出来 ——
                #    一次识别就把日志刷出**几 KB**，把真正有用的信息挤没了。
                #    排查用时只看得到"谁把日志刷爆了"，看不到耗时。
                #    现在只记耗时（这是真正需要长期观察的指标：能反映机器变慢/图变大）。
                logger.info("[AI] 推理耗时 %.2f 秒", inference_time)
                logger.debug("[AI] 模型原始输出: %s", type(results).__name__)

                if not hasattr(results[0], 'boxes'):
                    error_msg = "模型输出结果中缺少boxes属性"
                    logger.error(error_msg)
                    return {'status': 'error', 'message': '模型输出结果格式错误'}

                boxes = results[0].boxes
                if boxes is None or len(boxes) == 0:
                    info_msg = "未检测到任何病害，可能是一张健康作物的图片。"
                    logger.info(info_msg)
                    # 尝试从文件名或图像内容中提取作物类型
                    crop_type = self._extract_crop_type(image_file)
                    return {
                        'status': 'healthy',
                        'message': info_msg,
                        'crop_type': crop_type,
                        'confidence': 0.9,  # 默认高置信度为健康植物
                        'identifier': 'healthy_plant',
                        'annotated_image': None
                    }

                # 取置信度最高的目标
                best_idx = boxes.conf.argmax().item()
                best_box = boxes[best_idx]
                class_id = int(best_box.cls)
                confidence = float(best_box.conf)

                if confidence < 0.1:  # 如果置信度太低，也认为未找到
                    info_msg = f"找到目标但置信度太低: {confidence:.4f}"
                    logger.info(info_msg)
                    return {
                        'status': 'not_found', 
                        'message': '置信度太低，无法确认识别结果',
                        'confidence': confidence,
                        'identifier': 'unknown',
                        'annotated_image': None
                    }

                # 检查类别ID是否有效
                if class_id < 0 or class_id >= len(self.class_names):
                    error_msg = f"无效的类别ID: {class_id}"
                    logger.error(error_msg)
                    return {
                        'status': 'error', 
                        'message': f'无效的类别ID: {class_id}',
                        'confidence': confidence,
                        'identifier': 'unknown',
                        'annotated_image': None
                    }

                disease_identifier = self.class_names[class_id]

                # 渲染带框图片
                img_base64 = None
                try:
                    # 确保results不为空且包含检测结果
                    if not results or len(results) == 0 or len(results[0].boxes) == 0:
                        logger.warning("未检测到目标，使用原始图片")
                        # 如果没有检测到目标，使用原始图片
                        buffered = BytesIO()
                        img.save(buffered, format="JPEG")
                        img_base64 = f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
                    else:
                        # 确保图像是RGB模式
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                            
                        # 将PIL图像转换为numpy数组
                        img_array = np.array(img)
                        logger.info(f"原始图像形状: {img_array.shape}, 类型: {img_array.dtype}, 通道: {img_array.shape[2] if len(img_array.shape) > 2 else 1}")
                        
                        # 确保图像是RGB格式
                        if len(img_array.shape) == 2:  # 如果是灰度图
                            img_array = np.stack((img_array,) * 3, axis=-1)
                        elif img_array.shape[2] == 4:  # 如果是RGBA
                            img_array = img_array[..., :3]
                            
                        logger.info(f"处理后的图像形状: {img_array.shape}, 类型: {img_array.dtype}")
                        
                        try:
                            # 渲染带框图像 - 使用更大的线条宽度和更明显的颜色
                            annotated_img_array = results[0].plot(
                                img=img_array,
                                line_width=3,  # 增加线条宽度
                                font_size=16,  # 增加字体大小
                                labels=True,   # 显示标签
                                conf=True,     # 显示置信度
                                font='Arial',  # 使用更清晰的字体
                                pil=True       # 确保返回PIL图像
                            )
                            
                            # 处理渲染后的图像
                            if annotated_img_array is None:
                                raise ValueError("渲染后的图像为空")
                                
                            # 记录图像信息
                            if hasattr(annotated_img_array, 'size'):
                                logger.info(f"渲染后图像大小: {annotated_img_array.size}, 类型: {type(annotated_img_array)}")
                            
                            # 确保是PIL Image对象
                            if hasattr(annotated_img_array, 'convert'):
                                # 如果是PIL图像，直接使用
                                pil_image = annotated_img_array
                            else:
                                # 否则尝试转换为PIL图像
                                if isinstance(annotated_img_array, np.ndarray):
                                    # 确保图像数据在有效范围内
                                    if np.issubdtype(annotated_img_array.dtype, np.floating):
                                        if annotated_img_array.max() <= 1.0:  # 如果是0-1范围的浮点数
                                            annotated_img_array = (annotated_img_array * 255).astype('uint8')
                                        else:
                                            annotated_img_array = np.clip(annotated_img_array, 0, 255).astype('uint8')
                                    
                                    # 确保是3通道RGB图像
                                    if len(annotated_img_array.shape) == 2:  # 灰度图转RGB
                                        annotated_img_array = np.stack((annotated_img_array,) * 3, axis=-1)
                                    elif annotated_img_array.shape[2] == 4:  # RGBA转RGB
                                        annotated_img_array = annotated_img_array[..., :3]
                                    
                                    pil_image = Image.fromarray(annotated_img_array)
                                else:
                                    raise ValueError(f"不支持的图像类型: {type(annotated_img_array)}")
                            
                            # 确保图像是RGB模式
                            if pil_image.mode != 'RGB':
                                pil_image = pil_image.convert('RGB')
                            
                            # 记录图像信息
                            logger.info(f"准备保存图像 - 模式: {pil_image.mode}, 大小: {pil_image.size}")
                            
                            try:
                                # 将图像保存到内存中的BytesIO对象
                                img_byte_arr = BytesIO()
                                pil_image.save(img_byte_arr, format='JPEG', quality=95)
                                img_byte_arr.seek(0)
                                
                                # 将BytesIO对象转换为base64编码的字符串
                                img_base64 = f"data:image/jpeg;base64,{base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')}"
                                logger.info(f"成功生成标注图片，大小: {len(img_base64)} 字节")
                                
                            except Exception as img_error:
                                logger.error(f"转换PIL图像时出错: {str(img_error)}", exc_info=True)
                                # 出错时回退到原始图片
                                buffered = BytesIO()
                                img.save(buffered, format="JPEG")
                                img_base64 = f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
                        
                        except Exception as plot_error:
                            logger.error(f"渲染标注图像时出错: {str(plot_error)}", exc_info=True)
                            # 出错时回退到原始图片
                            buffered = BytesIO()
                            img.save(buffered, format="JPEG")
                            img_base64 = f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
                            
                except Exception as e:
                    logger.error(f"渲染标注图像时出错: {str(e)}", exc_info=True)
                    img_base64 = None

                logger.info(f"检测结果: {disease_identifier}, 置信度: {confidence:.4f}")
                
                # 构建返回结果
                result = {
                    'status': 'success',
                    'identifier': disease_identifier,
                    'confidence': confidence,
                    'annotated_image': img_base64,  # 返回base64编码的图像
                    'message': '检测成功',
                    'class_id': class_id,
                    'class_name': disease_identifier
                }
                
                return result

            except Exception as inference_error:
                error_msg = f"模型推理过程中发生错误: {str(inference_error)}"
                logger.error(error_msg, exc_info=True)
                return {
                    'status': 'error', 
                    'message': f'模型推理过程中发生错误: {str(inference_error)}',
                    'confidence': 0.0,
                    'identifier': 'error',
                    'annotated_image': None
                }
                
            finally:
                # 清理临时文件
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                    except Exception as e:
                        logger.warning(f"删除临时文件失败: {e}")

        except Exception as e:
            error_msg = f"预测过程中发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'status': 'error', 
                'message': f'预测过程中发生错误: {str(e)}',
                'confidence': 0.0,
                'identifier': 'error',
                'annotated_image': None
            }


def get_ai_service():
    """AI服务的单例访问器"""
    return AIService()


def warm_up(*, force: bool = False) -> bool:
    """
    启动预热（第 107 批新增）
    ============================================================================
    解决什么问题：**第一个上传图片的用户要等 20 多秒。**

    实测（CPU，Windows）：
      · 加载模型（`YOLO(...)`）      5.5s
      · **第一次真实推理**          21.0s
      · 之后的每次推理               0.8s

    `AIService.__new__` 里虽然有一个零张量 (`torch.zeros(1,3,640,640)`) 的
    "预测测试"，但它**只覆盖模型加载**，盖不住第一次真实推理要付的那些一次性开销
    （图像算法选择、NMS、线程池预热、注解绘制）。所以冷启动的账还是算在第一个用户头上。

    做法：启动时用一张**内存里合成的假图**完整走一遍 `predict()`。
    不读任何真实图片文件、不写数据库、不落盘（`predict` 只返回 base64）。

    为什么用假图而不是真实样例图：
      · 不依赖 `media/` 里有没有图片（生产环境可能刚部署、media 是空的）；
      · 不会因为"样例图被删了"导致预热静默失效。

    :param force: 忽略 `AI_WARMUP_ON_STARTUP` 设置强行预热（诊断/脚本用）
    :return: 预热是否成功（失败**不抛异常** —— 见下）
    """
    from django.conf import settings

    if not force and not getattr(settings, 'AI_WARMUP_ON_STARTUP', True):
        logger.info('AI 预热已通过 AI_WARMUP_ON_STARTUP=False 关闭')
        return False

    started = time.time()

    # ⚠️ 第 113 批：**整段预热都在锁里**。
    # 这一批把预热改成后台线程之后，"预热进行中正好来了识别请求"成了真实场景 ——
    # 两边会同时走 `YOLO(model_path)`：加载两份权重、两个 torch 前向抢 CPU，
    # 而 torch 的延迟初始化在极端情况下不是线程安全的。
    #
    # 用 `blocking=False` 拿锁：**拿不到就说明预热正在跑，直接返回**，
    # 不排队等待 —— 因为调用方（app 启动）不需要等结果，而真实请求走的是
    # `get_ai_service()`，它会在模型就绪后正常推理（那时预热线程已经填好了 model）。
    if not _WARMUP_LOCK.acquire(blocking=False):
        logger.info('AI 预热已在进行中，跳过重复调度')
        return False

    try:
        service = get_ai_service()
        if not service or not getattr(service, 'model', None):
            # 模型不可用是**启动时就能看到的事实**，不是预热的失败：
            # 让接口在真正被调用时返回 503（那里有面向农户的文案），
            # 而不是让 manage.py 起不来。
            logger.warning('AI 预热跳过：模型未加载（识别接口会返回 503）')
            return False

        # 合成一张 640x640 的纯色图 —— 与真实推理走完全相同的代码路径
        buffer = BytesIO()
        Image.new('RGB', (640, 640), (34, 139, 34)).save(buffer, format='JPEG')
        buffer.seek(0)
        result = service.predict(buffer)

        elapsed = time.time() - started
        if isinstance(result, dict) and result.get('status') == 'error':
            logger.warning('AI 预热完成但返回了错误状态（%.1fs）：%s', elapsed, result.get('message'))
            return False
        logger.info('AI 预热完成（%.1fs）—— 首个用户请求不再承担冷启动', elapsed)
        return True
    except Exception as exc:  # noqa: BLE001
        # **绝不因为预热失败而让服务起不来**：识别是核心功能，但它不该拥有
        # "否决启动"的权力（模型缺失、内存不足都可能发生，而其它接口仍然可用）。
        logger.warning('AI 预热失败（不影响启动）：%s', exc, exc_info=True)
        return False
    finally:
        # 必须在 finally 里放锁：漏掉任何一条返回路径都会让锁永远不释放，
        # 之后每次调度都直接被跳过（而且是静默的 —— 只有一行 info 日志）
        _WARMUP_LOCK.release()
