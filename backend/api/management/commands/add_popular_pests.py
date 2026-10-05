"""
一次性数据导入：补 10 条"常见病害"（与 38 类数据集无关的另一批内容）

**与 `add_detailed_pests.py` 的区别**：
  · 那个补的是**数据集里的 38 类**（识别结果要关联的病害）；
  · 这个补的是**首页/百科里展示的热门条目**，`help` 文字也写着 "top 10 popular pests"。

⚠️ 本文件的 `help` 是英文的（"Add top 10 popular pests to the database"），
而项目其它命令都是中文 —— 历史遗留，不影响功能。
要统一风格时顺手改掉即可，但**不要**改 `help` 以外的行为：
它是幂等导入（按名称 get_or_create），重复跑不会产生重复数据。
"""
from django.core.management.base import BaseCommand
from api.models import PestInfo, PreventionMethod

class Command(BaseCommand):
    help = 'Add top 10 popular pests to the database'

    def handle(self, *args, **options):
        # 病害数据
        pests_data = [
            {
                'name': '苹果黑星病',
                'crop_type': 'apple',
                'english_identifier': 'apple_scab',
                'symptoms': '叶片上出现黑褐色病斑，边缘不整齐，后期病斑上产生黑色霉层。',
                'description': '由真菌Venturia inaequalis引起，主要危害苹果叶片和果实。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '冬季清除病叶病果，减少越冬菌源。'
                    },
                    {
                        'category': 'CHEMICAL',
                        'measure': '花前花后各喷一次杀菌剂，如多菌灵、代森锰锌等。'
                    }
                ]
            },
            {
                'name': '苹果黑腐病',
                'crop_type': 'apple',
                'english_identifier': 'apple_black_rot',
                'symptoms': '果实上出现褐色水渍状病斑，后期病斑凹陷，上生黑色小点。',
                'description': '由真菌Botryosphaeria obtusa引起，危害果实、叶片和枝条。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '及时清除病果、病枝，减少侵染源。'
                    },
                    {
                        'category': 'CHEMICAL',
                        'measure': '果实套袋前喷施苯醚甲环唑或戊唑醇等药剂。'
                    }
                ]
            },
            {
                'name': '苹果雪松锈病',
                'crop_type': 'apple',
                'english_identifier': 'apple_cedar_apple_rust',
                'symptoms': '叶片正面出现橙黄色病斑，背面产生管状物。',
                'description': '由真菌Gymnosporangium juniperi-virginianae引起，需在苹果和柏树间转主寄生。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '避免在柏树附近种植苹果树。'
                    },
                    {
                        'category': 'CHEMICAL',
                        'measure': '春季萌芽前喷施石硫合剂，花后喷施三唑酮。'
                    }
                ]
            },
            {
                'name': '苹果健康',
                'crop_type': 'apple',
                'english_identifier': 'apple_healthy',
                'symptoms': '叶片绿色有光泽，无病斑，生长正常。',
                'description': '健康的苹果叶片，未受病害侵染。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '保持园区清洁，及时清除病残体。'
                    },
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '合理施肥，增强树势，提高抗病性。'
                    }
                ]
            },
            {
                'name': '蓝莓健康',
                'crop_type': 'blueberry',
                'english_identifier': 'blueberry_healthy',
                'symptoms': '叶片完整，颜色正常，无病斑。',
                'description': '健康的蓝莓植株，生长健壮。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '保持园区排水良好，避免积水。'
                    },
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '合理修剪，保持通风透光。'
                    }
                ]
            },
            {
                'name': '樱桃白粉病',
                'crop_type': 'cherry',
                'english_identifier': 'cherry_powdery_mildew',
                'symptoms': '叶片表面出现白色粉状霉层，后期叶片扭曲变形。',
                'description': '由真菌Podosphaera clandestina引起，主要危害叶片和嫩梢。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '合理修剪，保持树冠通风透光。'
                    },
                    {
                        'category': 'CHEMICAL',
                        'measure': '发病初期喷施苯醚甲环唑或腈菌唑等药剂。'
                    }
                ]
            },
            {
                'name': '樱桃健康',
                'crop_type': 'cherry',
                'english_identifier': 'cherry_healthy',
                'symptoms': '叶片绿色有光泽，无病斑，生长健壮。',
                'description': '健康的樱桃植株，未受病害侵染。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '合理施肥，增强树势。'
                    },
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '及时清除病残体，减少病源。'
                    }
                ]
            },
            {
                'name': '玉米灰斑病',
                'crop_type': 'corn',
                'english_identifier': 'corn_gray_leaf_spot',
                'symptoms': '叶片上出现长方形病斑，中央灰白色，边缘褐色。',
                'description': '由真菌Cercospora zeae-maydis引起，主要危害玉米叶片。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '选用抗病品种，合理密植。'
                    },
                    {
                        'category': 'CHEMICAL',
                        'measure': '发病初期喷施苯醚甲环唑或嘧菌酯等药剂。'
                    }
                ]
            },
            {
                'name': '玉米锈病',
                'crop_type': 'corn',
                'english_identifier': 'corn_common_rust',
                'symptoms': '叶片上出现黄褐色小疱斑，破裂后散出锈色粉末。',
                'description': '由真菌Puccinia sorghi引起，主要危害玉米叶片。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '选用抗病品种，避免连作。'
                    },
                    {
                        'category': 'CHEMICAL',
                        'measure': '发病初期喷施三唑酮或戊唑醇等药剂。'
                    }
                ]
            },
            {
                'name': '玉米健康',
                'crop_type': 'corn',
                'english_identifier': 'corn_healthy',
                'symptoms': '叶片绿色，无病斑，生长健壮。',
                'description': '健康的玉米植株，未受病害侵染。',
                'prevention': [
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '合理密植，保持田间通风透光。'
                    },
                    {
                        'category': 'AGRICULTURAL',
                        'measure': '科学施肥，增强植株抗病性。'
                    }
                ]
            }
        ]

        # 添加病害数据
        for pest_data in pests_data:
            # 检查是否已存在
            if not PestInfo.objects.filter(english_identifier=pest_data['english_identifier']).exists():
                # 创建病害
                pest = PestInfo.objects.create(
                    name=pest_data['name'],
                    crop_type=pest_data['crop_type'],
                    english_identifier=pest_data['english_identifier'],
                    symptoms=pest_data['symptoms'],
                    description=pest_data['description']
                )
                
                # 添加防治方法
                for prev_data in pest_data['prevention']:
                    PreventionMethod.objects.create(
                        pest=pest,
                        category=prev_data['category'],
                        measure=prev_data['measure']
                    )
                
                self.stdout.write(self.style.SUCCESS(f'成功添加病害: {pest.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'病害已存在: {pest_data["name"]}'))
        
        self.stdout.write(self.style.SUCCESS('病害数据添加完成！'))
