"""
一次性数据导入：为 38 种指定病害补"症状 / 发病规律 / 多种防治方法"

**这是什么**：项目早期的**种子数据脚本**。病害百科的内容最初就是靠它灌进库的
（`PestInfo` + `PreventionMethod`），不是靠管理后台一条条录。

**什么时候还会用到**：只在重建数据库、或把百科恢复成出厂内容时。
日常增改病害请走管理后台的「病害批量导入」（`/api/pests/import/`，
见 `views_pest_import.py`），那个有逐行校验与结果报告。

⚠️ 两点注意：
  · 数据是**写死在这个文件里的 Python 字面量**（约 600 行），
    与 `data.yaml` 里的 38 个类别一一对应 —— 改类别名要两边一起改；
  · `cleanup_pests.py` 是它的搭档：那个负责删掉"不在这 38 种里"的病害。
    先跑 cleanup 再跑本脚本，才能得到干净的 38 条。
    顺序反了会把刚导入的也删掉。
"""
from django.core.management.base import BaseCommand
from api.models import PestInfo, PreventionMethod

class Command(BaseCommand):
    help = '添加详细的病害数据，包含症状、发病规律和多种防治方法（仅限38种指定病害）'

    def handle(self, *args, **options):
        # 详细病害数据（仅包含38种指定病害）
        detailed_pests_data = [
            # 番茄病害
            {
                'name': '番茄晚疫病',
                'crop_type': '番茄',
                'english_identifier': 'tomato_late_blight',
                'symptoms': '叶片发病初期出现水渍状暗绿色病斑，后逐渐扩大呈褐色，病斑边缘不明显。潮湿时病斑边缘产生白色霉层。茎部受害出现黑褐色条斑，易折断。果实受害产生褐色硬斑，边缘不明显。',
                'description': '由致病疫霉引起的真菌性病害，是番茄最具毁灭性的病害之一。发病迅速，可在短时间内造成大面积减产甚至绝收。适宜发病温度为18-22℃，相对湿度95%以上。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，如"中蔬4号"、"佳红"等。实行轮作，避免与茄科作物连作。合理密植，保持通风透光。及时整枝打杈，降低田间湿度。发现病株立即拔除并带出田外销毁。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施68.75%银法利悬浮剂600-800倍液，或72%霜脲·锰锌可湿性粉剂600-800倍液，或25%甲霜灵可湿性粉剂800倍液。每隔7-10天喷一次，连续3-4次。注意轮换用药，避免产生抗药性。'},
                    {'category': 'ECOLOGICAL', 'measure': '保护地栽培可采用高温闷棚，在晴天中午密闭棚室2-3小时，使温度升至45-50℃，可有效杀灭病菌。合理控制浇水，避免大水漫灌。'},
                    {'category': 'PHYSICAL', 'measure': '采用地膜覆盖栽培，减少土壤中病菌传播。设置防虫网，阻止病菌传播。发病初期及时摘除病叶、病果，减少传染源。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，重点检查下部叶片。在发病季节（春秋季）每3-5天检查一次。发现中心病株立即标记并处理。建立病害预警系统，监测温湿度变化，提前预防。'}
                ]
            },
            {
                'name': '番茄早疫病',
                'crop_type': '番茄',
                'english_identifier': 'tomato_early_blight',
                'symptoms': '叶片发病初期出现深褐色小斑点，后扩大成圆形或近圆形病斑，有明显的同心轮纹。病斑边缘深褐色，中央灰褐色。茎部受害出现黑褐色凹陷病斑。果实受害多在果肩部，产生褐色凹陷病斑。',
                'description': '由茄链格孢菌引起的真菌性病害。病菌可在病残体上越冬，通过气流传播。高温高湿条件易发病，发病适温为26-28℃。主要危害叶片、茎和果实。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，如"毛粉802"、"中杂9号"等。实行2-3年轮作，避免与茄科作物连作。增施有机肥，提高植株抗病力。及时整枝打杈，改善通风条件。收获后彻底清除病残体。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施75%百菌清可湿性粉剂600倍液，或50%异菌脲可湿性粉剂1000倍液，或10%苯醚甲环唑水分散粒剂1500倍液。每隔7-10天喷一次，连续2-3次。'},
                    {'category': 'ECOLOGICAL', 'measure': '保护地栽培注意控制湿度，及时放风排湿。采用膜下滴灌，减少叶面湿度。合理密植，避免过密导致通风不良。'},
                    {'category': 'PHYSICAL', 'measure': '种子用55℃温水浸种15分钟进行消毒。定植前用50%多菌灵可湿性粉剂500倍液蘸根。发病初期摘除病叶，减少传染源。'},
                    {'category': 'MONITORING', 'measure': '定植后定期检查植株下部叶片。在高温高湿季节增加检查频率。记录发病时间和条件，分析发病规律。建立病害档案，指导次年预防。'}
                ]
            },
            {
                'name': '番茄叶霉病',
                'crop_type': '番茄',
                'english_identifier': 'tomato_leaf_mold',
                'symptoms': '叶片发病初期在叶背面出现白色霉斑，后变为灰褐色或黑褐色绒毛状霉层。叶片正面出现淡黄色至黄绿色不规则病斑，严重时叶片卷曲干枯。果实受害在果蒂附近产生圆形黑色病斑，硬化凹陷。',
                'description': '由黄枝孢菌引起的真菌性病害。病菌可在病残体上越冬，通过气流传播。高温高湿条件易发病，发病适温为20-25℃，相对湿度80%以上。主要危害叶片，也可危害果实。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，如"佳粉15号"、"中蔬5号"等。加强通风透光，降低湿度。及时整枝打杈，摘除下部老叶。实行轮作，避免连作。收获后彻底清除病残体。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液，或70%甲基硫菌灵可湿性粉剂800倍液。重点喷洒叶背面。每隔7-10天喷一次，连续2-3次。'},
                    {'category': 'ECOLOGICAL', 'measure': '保护地栽培注意放风排湿，尤其是在浇水后。采用膜下滴灌，减少叶面湿度。合理密植，避免过密。高温闷棚可有效抑制病菌。'},
                    {'category': 'PHYSICAL', 'measure': '种子用52℃温水浸种30分钟消毒。定植前用50%多菌灵可湿性粉剂500倍液蘸根。发病初期摘除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶背面，因为霉层首先出现在叶背。在高温高湿季节增加检查频率。记录发病规律，指导预防。建立病害监测点，实时监控。'}
                ]
            },
            {
                'name': '番茄细菌性斑点病',
                'crop_type': '番茄',
                'english_identifier': 'tomato_bacterial_spot',
                'symptoms': '叶片发病初期出现水渍状小斑点，后扩大成褐色病斑，周围有黄色晕圈。严重时病斑连片，叶片枯死。果实受害出现褐色凹陷斑点，边缘隆起。',
                'description': '由丁香假单胞菌番茄致病变种引起的细菌性病害。病菌可在种子和病残体上越冬，通过雨水、灌溉水传播。高温高湿条件易发病，发病适温为25-30℃。主要危害叶片和果实。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，实行轮作，避免连作。采用高垄栽培，加强排水。及时整枝打杈，摘除病叶。避免在阴天或雨天整枝。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施72%农用链霉素可溶性粉剂4000倍液，或新植霉素4000倍液，或47%春雷·王铜可湿性粉剂800倍液。每隔5-7天喷一次，连续2-3次。'},
                    {'category': 'ECOLOGICAL', 'measure': '严格控制湿度，及时放风排湿。采用膜下滴灌，避免叶面长时间湿润。合理密植，保持通风透光。避免大水漫灌。'},
                    {'category': 'PHYSICAL', 'measure': '种子用55℃温水浸种15分钟消毒，或用72%农用链霉素可溶性粉剂500倍液浸种2小时。发病初期摘除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，注意观察是否有水渍状斑点。在高温高湿季节每天检查。发现病株立即处理。监测田间湿度，及时通风。'}
                ]
            },
            {
                'name': '健康番茄',
                'crop_type': '番茄',
                'english_identifier': 'tomato_healthy',
                'symptoms': '叶片绿色有光泽，无病斑，生长正常。茎秆健壮，无畸形。果实发育正常，无病斑。',
                'description': '健康的番茄植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '保持园区清洁，及时清除病残体。合理施肥，增强树势，提高抗病性。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理密植，保持通风透光。及时整枝打杈，摘除下部老叶。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控温湿度，创造不利于病害发生的环境。采用膜下滴灌，避免叶面长时间湿润。'},
                    {'category': 'PHYSICAL', 'measure': '选用健康种子，进行种子消毒。采用地膜覆盖栽培。设置防虫网，阻止病菌传播。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。建立健康档案，记录生长状况。监测环境条件，及时调整。'}
                ]
            },
            {
                'name': '番茄斑枯病',
                'crop_type': '番茄',
                'english_identifier': 'tomato_septoria_leaf_spot',
                'symptoms': '叶片发病初期出现水渍状小斑点，后扩大成圆形或近圆形病斑，中央灰白色，边缘褐色。病斑上产生黑色小点。严重时病斑连片，叶片枯死。',
                'description': '由番茄壳针孢菌引起的真菌性病害。病菌可在病残体上越冬，通过气流传播。低温高湿条件易发病，发病适温为20-25℃。主要危害叶片。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，实行轮作，避免连作。及时整枝打杈，摘除下部老叶。收获后彻底清除病残体。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施75%百菌清可湿性粉剂600倍液，或50%多菌灵可湿性粉剂500倍液，或10%苯醚甲环唑水分散粒剂1500倍液。每隔7-10天喷一次，连续2-3次。'},
                    {'category': 'ECOLOGICAL', 'measure': '保护地栽培注意通风，降低湿度。采用膜下滴灌，减少叶面湿度。合理密植，保持通风透光。'},
                    {'category': 'PHYSICAL', 'measure': '种子用55℃温水浸种15分钟消毒。发病初期摘除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查下部叶片。在低温高湿季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            {
                'name': '番茄二斑叶螨',
                'crop_type': '番茄',
                'english_identifier': 'tomato_two_spotted_spider_mite',
                'symptoms': '叶片受害初期出现黄白色小斑点，后斑点扩大连片，叶片变黄枯萎。严重时叶片枯死脱落。螨体在叶背危害，吐丝结网。',
                'description': '由二斑叶螨引起的害螨危害。成螨和若螨在叶背吸食汁液，导致叶片失绿。高温干旱条件有利于繁殖。主要危害叶片。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '及时清除田间杂草和残株，减少虫源。合理灌溉，避免干旱。及时整枝打杈，改善通风条件。'},
                    {'category': 'CHEMICAL', 'measure': '发生初期喷施1.8%阿维菌素乳油3000倍液，或20%哒螨灵可湿性粉剂2000倍液，或240%螺螨酯悬浮剂4000倍液。重点喷洒叶背面。每隔5-7天喷一次，连续2-3次。'},
                    {'category': 'ECOLOGICAL', 'measure': '在田间设置黄板诱杀成螨。释放捕食螨等天敌进行生物防治。合理调控温湿度，创造不利于螨类繁殖的环境。'},
                    {'category': 'PHYSICAL', 'measure': '发病初期摘除受害叶片。采用地膜覆盖，阻止螨类入土越冬。设置防虫网，阻止螨类传播。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶背面，重点检查下部叶片。在高温干旱季节每天检查。发现中心虫株立即处理。建立虫情监测系统。'}
                ]
            },
            {
                'name': '番茄靶斑病',
                'crop_type': '番茄',
                'english_identifier': 'tomato_target_spot',
                'symptoms': '叶片发病初期出现水渍状小斑点，后扩大成圆形或不规则形病斑，中央灰白色，边缘褐色，有明显的同心轮纹，形似靶心。严重时病斑连片，叶片枯死。',
                'description': '由番茄链格孢菌引起的真菌性病害。病菌可在病残体上越冬，通过气流传播。高温高湿条件易发病，发病适温为25-30℃。主要危害叶片。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，实行轮作，避免连作。及时整枝打杈，摘除下部老叶。收获后彻底清除病残体。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施50%异菌脲可湿性粉剂1000倍液，或75%百菌清可湿性粉剂600倍液，或25%咪鲜胺乳油1000倍液。每隔7-10天喷一次，连续2-3次。'},
                    {'category': 'ECOLOGICAL', 'measure': '保护地栽培注意通风，降低湿度。采用膜下滴灌，减少叶面湿度。合理密植，保持通风透光。'},
                    {'category': 'PHYSICAL', 'measure': '种子用55℃温水浸种15分钟消毒。发病初期摘除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查下部叶片。在高温高湿季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            {
                'name': '番茄花叶病毒',
                'crop_type': '番茄',
                'english_identifier': 'tomato_mosaic_virus',
                'symptoms': '叶片出现浓淡相间的花叶，叶片皱缩不平，植株矮化。茎秆上出现褐色坏死条斑。果实受害出现畸形，表面有坏死斑点。',
                'description': '由烟草花叶病毒(TMV)引起的病毒性病害。通过汁液摩擦、昆虫（蚜虫）传播。高温干旱有利于发病。目前无特效药，以预防为主。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，实行轮作，避免与茄科作物连作。及时清除田间杂草和病株。加强肥水管理，增强植株抗性。操作前后用肥皂洗手消毒。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施20%病毒A可湿性粉剂500倍液，或1.5%植病灵乳剂1000倍液，或2%宁南霉素水剂200倍液。同时防治传毒媒介蚜虫，喷施10%吡虫啉可湿性粉剂2000倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '设置防虫网，阻止蚜虫传播。在田间设置黄板诱杀蚜虫。保护地栽培可采用银灰色地膜驱避蚜虫。合理调控温湿度。'},
                    {'category': 'PHYSICAL', 'measure': '种子用10%磷酸三钠溶液浸种20分钟消毒。操作工具用10%漂白粉溶液消毒。发现病株立即拔除并销毁。避免在病株上操作后接触健康植株。'},
                    {'category': 'MONITORING', 'measure': '定期检查植株，注意观察叶片症状。重点监测蚜虫数量。在病毒病高发季节增加检查频率。建立病毒病预警系统。'}
                ]
            },
            {
                'name': '番茄黄化曲叶病毒',
                'crop_type': '番茄',
                'english_identifier': 'tomato_yellow_leaf_curl_virus',
                'symptoms': '叶片边缘向上卷曲，叶片黄化，植株矮化。节间缩短，叶片变小。果实受害变小，畸形，不能正常成熟。',
                'description': '由番茄黄化曲叶病毒(TYLCV)引起的病毒性病害。主要通过烟粉虱传播。高温干旱有利于发病。目前无特效药，以预防为主。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，实行轮作，避免与茄科作物连作。及时清除田间杂草和病株。加强肥水管理，增强植株抗性。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施20%病毒A可湿性粉剂500倍液，或2%宁南霉素水剂200倍液。重点防治传毒媒介烟粉虱，喷施25%噻虫嗪水分散粒剂3000倍液，或10%吡虫啉可湿性粉剂2000倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '设置防虫网，阻止烟粉虱传播。在田间设置黄板诱杀烟粉虱。保护地栽培可采用银灰色地膜驱避烟粉虱。释放天敌丽蚜小蜂。'},
                    {'category': 'PHYSICAL', 'measure': '发现病株立即拔除并销毁。操作工具用10%漂白粉溶液消毒。避免在病株上操作后接触健康植株。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查植株，注意观察叶片症状。重点监测烟粉虱数量。在病毒病高发季节增加检查频率。建立病毒病预警系统。'}
                ]
            },
            # 苹果病害
            {
                'name': '苹果黑星病',
                'crop_type': '苹果',
                'english_identifier': 'apple_scab',
                'symptoms': '叶片上出现黑褐色病斑，边缘不整齐，后期病斑上产生黑色霉层。果实受害出现黑色凹陷病斑，表面粗糙。',
                'description': '由苹果黑星病菌(Venturia inaequalis)引起，主要危害苹果叶片和果实。病菌在病残体上越冬，通过气流传播。低温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '冬季清除病叶病果，减少越冬菌源。合理修剪，保持树冠通风透光。增施有机肥，增强树势。'},
                    {'category': 'CHEMICAL', 'measure': '花前花后各喷一次杀菌剂，如多菌灵、代森锰锌等。发病期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '及时清除病叶病果。采用地膜覆盖，减少病菌传播。设置防虫网。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片和果实，重点检查下部叶片。在发病季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            {
                'name': '苹果黑腐病',
                'crop_type': '苹果',
                'english_identifier': 'apple_black_rot',
                'symptoms': '果实上出现褐色水渍状病斑，后期病斑凹陷，上生黑色小点。叶片受害出现圆形或不规则形病斑，中央灰白色。',
                'description': '由苹果黑腐病菌(Botryosphaeria obtusa)引起，危害果实、叶片和枝条。病菌在病残体上越冬，通过风雨传播。高温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '及时清除病果、病枝，减少侵染源。合理修剪，保持树冠通风透光。增施有机肥，增强树势。'},
                    {'category': 'CHEMICAL', 'measure': '果实套袋前喷施苯醚甲环唑或戊唑醇等药剂。发病期喷施75%百菌清可湿性粉剂600倍液，或50%多菌灵可湿性粉剂500倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '果实套袋保护。及时清除病果。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查果实和叶片。在发病季节增加检查频率。发现病果立即摘除。'}
                ]
            },
            {
                'name': '苹果雪松锈病',
                'crop_type': '苹果',
                'english_identifier': 'apple_cedar_apple_rust',
                'symptoms': '叶片正面出现橙黄色病斑，背面产生管状物。果实受害出现橙黄色斑点，表面粗糙。',
                'description': '由苹果雪松锈病菌(Gymnosporangium juniperi-virginianae)引起，需在苹果和柏树间转主寄生。病菌在柏树上越冬，通过气流传播。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '避免在柏树附近种植苹果树。清除周围的柏树或保持距离。合理修剪，保持树冠通风透光。'},
                    {'category': 'CHEMICAL', 'measure': '春季萌芽前喷施石硫合剂，花后喷施三唑酮。发病期喷施25%三唑酮可湿性粉剂1000倍液，或12.5%烯唑醇可湿性粉剂2000倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '及时清除病叶病果。设置防虫网，阻止病菌传播。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片和果实。在春季萌芽期重点检查。发现中心病株立即处理。'}
                ]
            },
            {
                'name': '健康苹果',
                'crop_type': '苹果',
                'english_identifier': 'apple_healthy',
                'symptoms': '叶片绿色有光泽，无病斑，生长正常。果实发育正常，无病斑。树势健壮。',
                'description': '健康的苹果植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '保持园区清洁，及时清除病残体。合理施肥，增强树势，提高抗病性。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理修剪，保持树冠通风透光。及时清除病枝病叶。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控环境条件，创造不利于病害发生的环境。及时排水，避免积水。'},
                    {'category': 'PHYSICAL', 'measure': '采用地膜覆盖栽培。设置防虫网，阻止病菌传播。果实套袋保护。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。建立健康档案，记录生长状况。监测环境条件，及时调整。'}
                ]
            },
            # 蓝莓
            {
                'name': '健康蓝莓',
                'crop_type': '蓝莓',
                'english_identifier': 'blueberry_healthy',
                'symptoms': '叶片完整，颜色正常，无病斑。枝条健壮，无畸形。果实发育正常，无病斑。',
                'description': '健康的蓝莓植株，生长健壮。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '保持园区排水良好，避免积水。合理施肥，增强植株抗性。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理修剪，保持通风透光。及时清除病残体。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控土壤pH值，保持在4.5-5.5之间。及时排水，避免积水。'},
                    {'category': 'PHYSICAL', 'measure': '采用地膜覆盖栽培。设置防虫网，阻止病菌传播。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。监测土壤湿度，及时调整。'}
                ]
            },
            # 樱桃病害
            {
                'name': '健康樱桃',
                'crop_type': '樱桃',
                'english_identifier': 'cherry_healthy',
                'symptoms': '叶片绿色有光泽，无病斑，生长正常。果实发育正常，无病斑。树势健壮。',
                'description': '健康的樱桃植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '合理施肥，增强树势。保持园区清洁，及时清除病残体。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理修剪，保持树冠通风透光。及时清除病枝病叶。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控温湿度，创造不利于病害发生的环境。及时排水，避免积水。'},
                    {'category': 'PHYSICAL', 'measure': '采用地膜覆盖栽培。设置防虫网，阻止病菌传播。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。建立健康档案，记录生长状况。'}
                ]
            },
            {
                'name': '樱桃白粉病',
                'crop_type': '樱桃',
                'english_identifier': 'cherry_powdery_mildew',
                'symptoms': '叶片表面出现白色粉状霉层，后期叶片扭曲变形。果实受害表面出现白色粉斑。',
                'description': '由樱桃白粉病菌(Podosphaera clandestina)引起，主要危害叶片和嫩梢。病菌在病残体上越冬，通过气流传播。高温干旱条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '合理修剪，保持树冠通风透光。及时清除病叶病梢。增施有机肥，增强树势。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施苯醚甲环唑或腈菌唑等药剂。发病期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '发病初期摘除病叶。采用硫磺熏蒸。设置防虫网，阻止病菌传播。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查嫩梢。在发病季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            # 玉米病害
            {
                'name': '玉米尾孢叶斑病',
                'crop_type': '玉米',
                'english_identifier': 'corn_gray_leaf_spot',
                'symptoms': '叶片上出现长方形病斑，中央灰白色，边缘褐色。严重时病斑连片，叶片枯死。',
                'description': '由玉米尾孢叶斑病菌(Cercospora zeae-maydis)引起，主要危害玉米叶片。病菌在病残体上越冬，通过气流传播。高温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，合理密植。实行轮作，避免连作。及时清除病残体。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施苯醚甲环唑或嘧菌酯等药剂。发病期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '及时清除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查下部叶片。在发病季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            {
                'name': '玉米普通锈病',
                'crop_type': '玉米',
                'english_identifier': 'corn_common_rust',
                'symptoms': '叶片上出现黄褐色小疱斑，破裂后散出锈色粉末。严重时叶片枯死。',
                'description': '由玉米普通锈病菌(Puccinia sorghi)引起，主要危害玉米叶片。病菌在病残体上越冬，通过气流传播。低温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，避免连作。合理密植，保持通风透光。及时清除病残体。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施三唑酮或戊唑醇等药剂。发病期喷施25%三唑酮可湿性粉剂1000倍液，或12.5%烯唑醇可湿性粉剂2000倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '及时清除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查下部叶片。在发病季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            {
                'name': '健康玉米',
                'crop_type': '玉米',
                'english_identifier': 'corn_healthy',
                'symptoms': '叶片绿色，无病斑，生长健壮。茎秆粗壮，无畸形。果穗发育正常。',
                'description': '健康的玉米植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '合理密植，保持田间通风透光。科学施肥，增强植株抗病性。'},
                    {'category': 'AGRICULTURAL', 'measure': '及时清除病残体。实行轮作，避免连作。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控田间湿度，及时排水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '选用健康种子，进行种子消毒。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。监测田间湿度，及时调整。'}
                ]
            },
            {
                'name': '玉米北方叶枯病',
                'crop_type': '玉米',
                'english_identifier': 'corn_northern_leaf_blight',
                'symptoms': '叶片出现大型梭形病斑，中央灰褐色，边缘褐色。严重时病斑连片，叶片枯死。',
                'description': '由玉米北方叶枯病菌(Setosphaeria turcica)引起，主要危害玉米叶片。病菌在病残体上越冬，通过气流传播。高温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，实行轮作，避免连作。合理密植，保持通风透光。及时清除病残体。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施苯醚甲环唑或嘧菌酯等药剂。发病期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '及时清除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查下部叶片。在发病季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            # 葡萄病害
            {
                'name': '葡萄黑腐病',
                'crop_type': '葡萄',
                'english_identifier': 'grape_black_rot',
                'symptoms': '果实出现褐色腐烂，后期干缩成僵果。叶片出现圆形病斑，中央灰白色。',
                'description': '由葡萄黑腐病菌(Guignardia bidwellii)引起，主要危害果实和叶片。病菌在病残体上越冬，通过风雨传播。高温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '及时清除病果病叶，减少侵染源。合理修剪，保持架面通风透光。增施有机肥，增强树势。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施苯醚甲环唑或嘧菌酯等药剂。发病期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '果实套袋保护。及时清除病果。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查果实和叶片。在发病季节增加检查频率。发现病果立即摘除。'}
                ]
            },
            {
                'name': '葡萄黑麻疹病',
                'crop_type': '葡萄',
                'english_identifier': 'grape_black_measles',
                'symptoms': '果实出现黑斑，表面粗糙。叶片出现不规则形病斑，中央灰白色。',
                'description': '由真菌引起，主要危害果实和叶片。病菌在病残体上越冬，通过风雨传播。高温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '及时清除病果病叶，减少侵染源。合理修剪，保持架面通风透光。增施有机肥，增强树势。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施苯醚甲环唑或嘧菌酯等药剂。发病期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '果实套袋保护。及时清除病果。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查果实和叶片。在发病季节增加检查频率。发现病果立即摘除。'}
                ]
            },
            {
                'name': '健康葡萄',
                'crop_type': '葡萄',
                'english_identifier': 'grape_healthy',
                'symptoms': '叶片绿色，果粒饱满，无病斑。枝条健壮，无畸形。树势健壮。',
                'description': '健康的葡萄植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '合理修剪，保持架面通风透光。及时清除病残体。增施有机肥，增强树势。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理负载，避免结果过多。及时疏花疏果。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控田间湿度，及时排水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '果实套袋保护。采用地膜覆盖栽培。设置防虫网。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。监测田间湿度，及时调整。'}
                ]
            },
            {
                'name': '葡萄叶枯病',
                'crop_type': '葡萄',
                'english_identifier': 'grape_leaf_blight',
                'symptoms': '叶片出现枯死斑点，后扩大成不规则形病斑。严重时叶片枯死脱落。',
                'description': '由真菌引起，主要危害叶片。病菌在病残体上越冬，通过风雨传播。高温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '及时清除病叶，减少侵染源。合理修剪，保持架面通风透光。增施有机肥，增强树势。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施苯醚甲环唑或嘧菌酯等药剂。发病期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '及时清除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查下部叶片。在发病季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            # 柑橘
            {
                'name': '柑橘黄龙病',
                'crop_type': '柑橘',
                'english_identifier': 'citrus_greening',
                'symptoms': '叶片黄化，出现斑驳状黄化。果实畸形，变小，着色不均。树势衰弱，产量下降。',
                'description': '由柑橘黄龙病菌(Candidatus Liberibacter asiaticus)引起的毁灭性病害。主要通过柑橘木虱传播。目前无特效药，以预防为主。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '严格检疫，防止带病苗木传入。及时清除病株，减少传染源。加强肥水管理，增强树势。'},
                    {'category': 'CHEMICAL', 'measure': '重点防治传毒媒介柑橘木虱，喷施25%噻虫嗪水分散粒剂3000倍液，或10%吡虫啉可湿性粉剂2000倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '设置防虫网，阻止木虱传播。在田间设置黄板诱杀木虱。释放天敌进行生物防治。'},
                    {'category': 'PHYSICAL', 'measure': '发现病株立即挖除并销毁。操作工具用10%漂白粉溶液消毒。采用无病苗木。'},
                    {'category': 'MONITORING', 'measure': '定期检查植株，注意观察叶片症状。重点监测木虱数量。建立病害预警系统。发现病株立即处理。'}
                ]
            },
            # 桃病害
            {
                'name': '桃细菌性斑点病',
                'crop_type': '桃',
                'english_identifier': 'peach_bacterial_spot',
                'symptoms': '叶片和果实出现褐色斑点，周围有水渍状边缘。严重时叶片穿孔，果实腐烂。',
                'description': '由桃细菌性斑点病菌(Xanthomonas arboricola pv. pruni)引起的细菌性病害。病菌在病残体上越冬，通过风雨传播。高温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，及时清除病叶病果。合理修剪，保持树冠通风透光。增施有机肥，增强树势。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施铜制剂，如47%春雷·王铜可湿性粉剂800倍液，或72%农用链霉素可溶性粉剂4000倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '及时清除病叶病果。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片和果实。在发病季节增加检查频率。发现病叶病果立即摘除。'}
                ]
            },
            {
                'name': '健康桃',
                'crop_type': '桃',
                'english_identifier': 'peach_healthy',
                'symptoms': '叶片绿色，生长健壮。果实发育正常，无病斑。树势健壮。',
                'description': '健康的桃植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '合理修剪，保持树冠通风透光。及时清除病残体。增施有机肥，增强树势。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理负载，避免结果过多。及时疏花疏果。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控田间湿度，及时排水。加强田间管理，增强树势。'},
                    {'category': 'PHYSICAL', 'measure': '采用地膜覆盖栽培。设置防虫网。果实套袋保护。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。监测田间湿度，及时调整。'}
                ]
            },
            # 甜椒病害
            {
                'name': '甜椒细菌性斑点病',
                'crop_type': '甜椒',
                'english_identifier': 'pepper_bacterial_spot',
                'symptoms': '叶片出现水渍状斑点，后扩大成褐色病斑。果实受害出现褐色凹陷斑点。',
                'description': '由甜椒细菌性斑点病菌(Xanthomonas campestris pv. vesicatoria)引起的细菌性病害。病菌在种子和病残体上越冬，通过风雨传播。高温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，实行轮作，避免连作。及时清除病叶病果。合理密植，保持通风透光。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施铜制剂，如47%春雷·王铜可湿性粉剂800倍液，或72%农用链霉素可溶性粉剂4000倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '种子用55℃温水浸种15分钟消毒。及时清除病叶病果。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片和果实。在发病季节增加检查频率。发现病叶病果立即摘除。'}
                ]
            },
            {
                'name': '健康甜椒',
                'crop_type': '甜椒',
                'english_identifier': 'pepper_healthy',
                'symptoms': '叶片绿色，生长健壮。果实发育正常，无病斑。植株健壮。',
                'description': '健康的甜椒植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '合理施肥，增强植株抗性。保持园区清洁，及时清除病残体。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理密植，保持通风透光。及时整枝打杈。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控温湿度，创造不利于病害发生的环境。及时排水，避免积水。'},
                    {'category': 'PHYSICAL', 'measure': '选用健康种子，进行种子消毒。采用地膜覆盖栽培。设置防虫网。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。监测田间湿度，及时调整。'}
                ]
            },
            # 马铃薯病害
            {
                'name': '马铃薯早疫病',
                'crop_type': '马铃薯',
                'english_identifier': 'potato_early_blight',
                'symptoms': '叶片出现同心轮纹病斑，中央灰白色，边缘褐色。块茎受害出现褐色凹陷病斑。',
                'description': '由茄链格孢菌引起的真菌性病害。病菌在病残体上越冬，通过气流传播。高温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，实行轮作，避免连作。选用健康种薯。及时清除病残体。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施75%百菌清可湿性粉剂600倍液，或50%异菌脲可湿性粉剂1000倍液，或10%苯醚甲环唑水分散粒剂1500倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '选用健康种薯，进行种薯消毒。及时清除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查下部叶片。在发病季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            {
                'name': '健康马铃薯',
                'crop_type': '马铃薯',
                'english_identifier': 'potato_healthy',
                'symptoms': '叶片绿色，生长健壮。块茎发育正常，无病斑。植株健壮。',
                'description': '健康的马铃薯植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用健康种薯，进行种薯消毒。实行轮作，避免连作。及时清除病残体。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理密植，保持通风透光。科学施肥，增强植株抗性。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控田间湿度，及时排水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '采用地膜覆盖栽培。设置防虫网。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。监测田间湿度，及时调整。'}
                ]
            },
            {
                'name': '马铃薯晚疫病',
                'crop_type': '马铃薯',
                'english_identifier': 'potato_late_blight',
                'symptoms': '叶片出现水渍状病斑，后扩大成褐色病斑，边缘有白色霉层。块茎受害出现褐色腐烂。',
                'description': '由致病疫霉引起的真菌性病害，是马铃薯最具毁灭性的病害之一。病菌在病残体上越冬，通过气流传播。低温高湿条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，实行轮作，避免连作。选用健康种薯。及时清除病残体。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施68.75%银法利悬浮剂600-800倍液，或72%霜脲·锰锌可湿性粉剂600-800倍液，或25%甲霜灵可湿性粉剂800倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '选用健康种薯，进行种薯消毒。及时清除病叶。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查下部叶片。在发病季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            # 树莓
            {
                'name': '健康树莓',
                'crop_type': '树莓',
                'english_identifier': 'raspberry_healthy',
                'symptoms': '叶片绿色，生长健壮。果实发育正常，无病斑。枝条健壮。',
                'description': '健康的树莓植株，生长健壮。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '保持园区排水良好，避免积水。合理施肥，增强植株抗性。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理修剪，保持通风透光。及时清除病残体。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控土壤湿度，及时排水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '采用地膜覆盖栽培。设置防虫网。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。监测土壤湿度，及时调整。'}
                ]
            },
            # 大豆
            {
                'name': '健康大豆',
                'crop_type': '大豆',
                'english_identifier': 'soybean_healthy',
                'symptoms': '叶片绿色，生长健壮。荚果发育正常，无病斑。植株健壮。',
                'description': '健康的大豆植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '实行轮作，避免连作。合理施肥，增强植株抗性。及时清除病残体。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理密植，保持通风透光。科学灌溉，避免积水。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控田间湿度，及时排水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '选用健康种子，进行种子消毒。采用地膜覆盖栽培。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。监测田间湿度，及时调整。'}
                ]
            },
            # 南瓜
            {
                'name': '南瓜白粉病',
                'crop_type': '南瓜',
                'english_identifier': 'pumpkin_powdery_mildew',
                'symptoms': '叶片表面出现白色粉状霉层，后扩大成白色粉斑。严重时叶片枯萎。',
                'description': '由真菌引起的白粉病。病菌在病残体上越冬，通过气流传播。高温干旱条件易发病。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '选用抗病品种，合理密植，保持通风透光。及时清除病叶。增施有机肥，增强植株抗性。'},
                    {'category': 'CHEMICAL', 'measure': '发病初期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液，或15%三唑酮可湿性粉剂1000倍液。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理密植，保持通风透光。及时排水，避免积水。加强田间管理，增强植株抗性。'},
                    {'category': 'PHYSICAL', 'measure': '发病初期摘除病叶。采用硫磺熏蒸。设置防虫网，阻止病菌传播。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查中上部叶片。在发病季节增加检查频率。发现中心病株立即处理。'}
                ]
            },
            # 草莓病害
            {
                'name': '健康草莓',
                'crop_type': '草莓',
                'english_identifier': 'strawberry_healthy',
                'symptoms': '叶片绿色，果实饱满，无病斑。植株健壮，生长正常。',
                'description': '健康的草莓植株，未受病害侵染。保持健康状态需要良好的栽培管理。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '保持园区清洁，及时清除病残体。合理施肥，增强植株抗性。'},
                    {'category': 'AGRICULTURAL', 'measure': '合理密植，保持通风透光。及时摘除老叶病叶。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控温湿度，创造不利于病害发生的环境。及时排水，避免积水。'},
                    {'category': 'PHYSICAL', 'measure': '采用地膜覆盖栽培。设置防虫网。'},
                    {'category': 'MONITORING', 'measure': '定期田间巡查，及时发现异常。监测田间湿度，及时调整。'}
                ]
            },
            {
                'name': '草莓叶焦病',
                'crop_type': '草莓',
                'english_identifier': 'strawberry_leaf_scorch',
                'symptoms': '叶片边缘焦枯，向内卷曲。严重时整个叶片枯死。',
                'description': '生理性病害，主要由环境条件不适引起。高温、强光、干旱或盐害等因素均可导致。',
                'prevention': [
                    {'category': 'AGRICULTURAL', 'measure': '合理浇水，避免干旱。合理施肥，避免盐害。加强田间管理，增强植株抗性。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理调控温湿度，避免高温强光。采用遮阳网，降低光照强度。'},
                    {'category': 'ECOLOGICAL', 'measure': '合理灌溉，保持土壤湿润。采用滴灌，减少水分蒸发。'},
                    {'category': 'PHYSICAL', 'measure': '采用遮阳网遮阴。地膜覆盖，保持土壤湿度。'},
                    {'category': 'MONITORING', 'measure': '定期检查叶片，重点检查叶缘。在高温季节增加检查频率。监测环境条件，及时调整。'}
                ]
            },
        ]

        # 添加病害数据
        for pest_data in detailed_pests_data:
            # 检查是否已存在（使用name和crop_type组合）
            pest = PestInfo.objects.filter(
                name=pest_data['name'],
                crop_type=pest_data['crop_type']
            ).first()
            
            if pest:
                # 更新已存在的病害
                pest.english_identifier = pest_data['english_identifier']
                pest.symptoms = pest_data['symptoms']
                pest.description = pest_data['description']
                pest.save()
                
                # 删除旧的防治方法
                PreventionMethod.objects.filter(pest=pest).delete()
                
                # 添加新的防治方法
                for prev_data in pest_data['prevention']:
                    PreventionMethod.objects.create(
                        pest=pest,
                        category=prev_data['category'],
                        measure=prev_data['measure']
                    )
                
                self.stdout.write(self.style.SUCCESS(f'已更新病害: {pest.name}'))
            else:
                # 创建新病害
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
        
        self.stdout.write(self.style.SUCCESS('详细病害数据添加完成！'))
