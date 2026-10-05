"""
防治措施英文回填（第 78 批）

背景
------------------------------------------------------------------
`PreventionMethod.measure_en` 字段早在第 72 批就建好了，但**一条都没填**：
190 条防治方法、130 条不重复文本，全部只有中文。后果是英文界面下
`/pests/<id>`（病害详情）与 `/preventions/<id>`（综合防治）两页的"防治方法"
整块仍是中文 —— 前端 `localizedField(method, 'measure')` 已经在按 `measure_en`
取值了，缺的是数据本身。这类缺口前端修不了，必须补语料。

为什么按"句子"翻译，而不是逐条翻译 130 条措施
------------------------------------------------------------------
① 190 条措施里大量句子完全重复（"采用地膜覆盖栽培。" 出现 17 次、
   "合理密植，保持通风透光。" 13 次……）。按句子翻译只需 203 条语料，
   而且**同一句中文永远得到同一句英文**，不会出现同义不同译；
② 组装规则极简：按中文句号切分 → 逐句查表 → 用空格连接（英文习惯），
   切分不改变句子顺序，所以译文与原文一一对应，可逐句核对。

用法
------------------------------------------------------------------
    python manage.py translate_prevention_measures --dry-run   # 只体检，不写库
    python manage.py translate_prevention_measures             # 回填（幂等：已有英文的跳过）
    python manage.py translate_prevention_measures --force     # 连已有英文的也重写

缺语料时**不会**静默留下中文：命令会列出所有没查到译文的句子并以非 0 退出，
避免"看起来跑成功了、其实一半还是中文"。
"""
import re

from django.core.management.base import BaseCommand

from api.models import PreventionMethod

#: 中文句号切分，保留句号在句尾（`(?<=。)` 零宽断言）
SENTENCE_SPLIT = re.compile(r'(?<=。)')

#: 中文句子 → 英文句子。农药名称用英文通用名 + 剂型缩写，产品名保留音译并括注成分。
SENTENCE_EN = {
    '严格控制湿度，及时放风排湿。': 'Keep humidity under strict control and vent promptly to remove moisture.',
    '严格检疫，防止带病苗木传入。': 'Apply strict quarantine to prevent the introduction of infected nursery stock.',
    '保护地栽培可采用银灰色地膜驱避烟粉虱。': 'Under protected cultivation, silver-grey plastic mulch repels whitefly.',
    '保护地栽培可采用银灰色地膜驱避蚜虫。': 'Under protected cultivation, silver-grey plastic mulch repels aphids.',
    '保护地栽培可采用高温闷棚，在晴天中午密闭棚室2-3小时，使温度升至45-50℃，可有效杀灭病菌。': 'Under protected cultivation, seal the greenhouse for 2–3 hours at midday on a sunny day and raise the temperature to 45–50 °C to kill the pathogen effectively.',
    '保护地栽培注意控制湿度，及时放风排湿。': 'Under protected cultivation, control humidity and vent promptly to remove moisture.',
    '保护地栽培注意放风排湿，尤其是在浇水后。': 'Under protected cultivation, vent to remove moisture, especially after watering.',
    '保护地栽培注意通风，降低湿度。': 'Under protected cultivation, ventilate to lower humidity.',
    '保持园区排水良好，避免积水。': 'Keep the orchard well drained and avoid waterlogging.',
    '保持园区清洁，及时清除病残体。': 'Keep the site clean and remove diseased debris promptly.',
    '冬季清除病叶病果，减少越冬菌源。': 'In winter, clear fallen diseased leaves and fruit to reduce the overwintering inoculum.',
    '加强田间管理，增强树势。': 'Strengthen field management to keep the trees vigorous.',
    '加强田间管理，增强植株抗性。': 'Strengthen field management to improve plant resistance.',
    '加强肥水管理，增强树势。': 'Improve fertiliser and water management to keep the trees vigorous.',
    '加强肥水管理，增强植株抗性。': 'Improve fertiliser and water management to improve plant resistance.',
    '加强通风透光，降低湿度。': 'Improve ventilation and light penetration, and lower humidity.',
    '及时排水，避免积水。': 'Drain promptly and avoid waterlogging.',
    '及时摘除老叶病叶。': 'Remove old and diseased leaves promptly.',
    '及时整枝打杈。': 'Prune and remove side shoots promptly.',
    '及时整枝打杈，摘除下部老叶。': 'Prune and remove side shoots, and take off the lower old leaves promptly.',
    '及时整枝打杈，摘除病叶。': 'Prune and remove side shoots, and take off diseased leaves promptly.',
    '及时整枝打杈，改善通风条件。': 'Prune and remove side shoots promptly to improve ventilation.',
    '及时整枝打杈，降低田间湿度。': 'Prune and remove side shoots promptly to lower field humidity.',
    '及时清除田间杂草和残株，减少虫源。': 'Clear weeds and crop residues promptly to reduce the source of insects.',
    '及时清除田间杂草和病株。': 'Clear weeds and diseased plants promptly.',
    '及时清除病叶。': 'Remove diseased leaves promptly.',
    '及时清除病叶病果。': 'Remove diseased leaves and fruit promptly.',
    '及时清除病叶病梢。': 'Remove diseased leaves and shoots promptly.',
    '及时清除病叶，减少侵染源。': 'Remove diseased leaves promptly to reduce the source of infection.',
    '及时清除病果、病枝，减少侵染源。': 'Remove diseased fruit and branches promptly to reduce the source of infection.',
    '及时清除病果。': 'Remove diseased fruit promptly.',
    '及时清除病果病叶，减少侵染源。': 'Remove diseased fruit and leaves promptly to reduce the source of infection.',
    '及时清除病枝病叶。': 'Remove diseased branches and leaves promptly.',
    '及时清除病株，减少传染源。': 'Remove diseased plants promptly to reduce the source of infection.',
    '及时清除病残体。': 'Remove diseased plant debris promptly.',
    '及时疏花疏果。': 'Thin flowers and fruit promptly.',
    '发现中心病株立即处理。': 'Rogue out the first infected plants as soon as they appear.',
    '发现中心病株立即标记并处理。': 'Mark and rogue out the first infected plants as soon as they appear.',
    '发现中心虫株立即处理。': 'Deal with the first infested plants as soon as they appear.',
    '发现病叶病果立即摘除。': 'Remove diseased leaves and fruit as soon as they are found.',
    '发现病果立即摘除。': 'Remove diseased fruit as soon as it is found.',
    '发现病株立即处理。': 'Deal with diseased plants as soon as they are found.',
    '发现病株立即拔除并带出田外销毁。': 'Pull out diseased plants at once, carry them out of the field and destroy them.',
    '发现病株立即拔除并销毁。': 'Pull out and destroy diseased plants at once.',
    '发现病株立即挖除并销毁。': 'Dig out and destroy diseased plants at once.',
    '发生初期喷施1.8%阿维菌素乳油3000倍液，或20%哒螨灵可湿性粉剂2000倍液，或240%螺螨酯悬浮剂4000倍液。': 'At the first sign of infestation, spray 1.8% abamectin EC at 3000× dilution, or 20% pyridaben WP at 2000× dilution, or 240 g/L spirodiclofen SC at 4000× dilution.',
    '发病初期及时摘除病叶、病果，减少传染源。': 'Remove diseased leaves and fruit promptly at the first sign of disease to reduce the source of infection.',
    '发病初期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液，或15%三唑酮可湿性粉剂1000倍液。': 'At the first sign of disease, spray 10% difenoconazole WG at 1500× dilution, or 25% azoxystrobin SC at 1500× dilution, or 15% triadimefon WP at 1000× dilution.',
    '发病初期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液，或70%甲基硫菌灵可湿性粉剂800倍液。': 'At the first sign of disease, spray 10% difenoconazole WG at 1500× dilution, or 25% azoxystrobin SC at 1500× dilution, or 70% thiophanate-methyl WP at 800× dilution.',
    '发病初期喷施20%病毒A可湿性粉剂500倍液，或1.5%植病灵乳剂1000倍液，或2%宁南霉素水剂200倍液。': 'At the first sign of disease, spray 20% Virus A WP at 500× dilution, or 1.5% Zhibingling EC at 1000× dilution, or 2% ningnanmycin AS at 200× dilution.',
    '发病初期喷施20%病毒A可湿性粉剂500倍液，或2%宁南霉素水剂200倍液。': 'At the first sign of disease, spray 20% Virus A WP at 500× dilution, or 2% ningnanmycin AS at 200× dilution.',
    '发病初期喷施50%异菌脲可湿性粉剂1000倍液，或75%百菌清可湿性粉剂600倍液，或25%咪鲜胺乳油1000倍液。': 'At the first sign of disease, spray 50% iprodione WP at 1000× dilution, or 75% chlorothalonil WP at 600× dilution, or 25% prochloraz EC at 1000× dilution.',
    '发病初期喷施68.75%银法利悬浮剂600-800倍液，或72%霜脲·锰锌可湿性粉剂600-800倍液，或25%甲霜灵可湿性粉剂800倍液。': 'At the first sign of disease, spray 68.75% Infinito (fluopicolide + propamocarb) SC at 600–800× dilution, or 72% cymoxanil + mancozeb WP at 600–800× dilution, or 25% metalaxyl WP at 800× dilution.',
    '发病初期喷施72%农用链霉素可溶性粉剂4000倍液，或新植霉素4000倍液，或47%春雷·王铜可湿性粉剂800倍液。': 'At the first sign of disease, spray 72% agricultural streptomycin SP at 4000× dilution, or Xinzhimeisu at 4000× dilution, or 47% kasugamycin + copper oxychloride WP at 800× dilution.',
    '发病初期喷施75%百菌清可湿性粉剂600倍液，或50%多菌灵可湿性粉剂500倍液，或10%苯醚甲环唑水分散粒剂1500倍液。': 'At the first sign of disease, spray 75% chlorothalonil WP at 600× dilution, or 50% carbendazim WP at 500× dilution, or 10% difenoconazole WG at 1500× dilution.',
    '发病初期喷施75%百菌清可湿性粉剂600倍液，或50%异菌脲可湿性粉剂1000倍液，或10%苯醚甲环唑水分散粒剂1500倍液。': 'At the first sign of disease, spray 75% chlorothalonil WP at 600× dilution, or 50% iprodione WP at 1000× dilution, or 10% difenoconazole WG at 1500× dilution.',
    '发病初期喷施三唑酮或戊唑醇等药剂。': 'At the first sign of disease, spray triadimefon, tebuconazole or a similar fungicide.',
    '发病初期喷施苯醚甲环唑或嘧菌酯等药剂。': 'At the first sign of disease, spray difenoconazole, azoxystrobin or a similar fungicide.',
    '发病初期喷施苯醚甲环唑或腈菌唑等药剂。': 'At the first sign of disease, spray difenoconazole, myclobutanil or a similar fungicide.',
    '发病初期喷施铜制剂，如47%春雷·王铜可湿性粉剂800倍液，或72%农用链霉素可溶性粉剂4000倍液。': 'At the first sign of disease, spray a copper-based fungicide such as 47% kasugamycin + copper oxychloride WP at 800× dilution, or 72% agricultural streptomycin SP at 4000× dilution.',
    '发病初期摘除受害叶片。': 'Remove the affected leaves at the first sign of disease.',
    '发病初期摘除病叶。': 'Remove diseased leaves at the first sign of disease.',
    '发病初期摘除病叶，减少传染源。': 'Remove diseased leaves at the first sign of disease to reduce the source of infection.',
    '发病期喷施10%苯醚甲环唑水分散粒剂1500倍液，或25%嘧菌酯悬浮剂1500倍液。': 'During the disease period, spray 10% difenoconazole WG at 1500× dilution, or 25% azoxystrobin SC at 1500× dilution.',
    '发病期喷施25%三唑酮可湿性粉剂1000倍液，或12.5%烯唑醇可湿性粉剂2000倍液。': 'During the disease period, spray 25% triadimefon WP at 1000× dilution, or 12.5% diniconazole WP at 2000× dilution.',
    '发病期喷施75%百菌清可湿性粉剂600倍液，或50%多菌灵可湿性粉剂500倍液。': 'During the disease period, spray 75% chlorothalonil WP at 600× dilution, or 50% carbendazim WP at 500× dilution.',
    '合理修剪，保持架面通风透光。': 'Prune sensibly to keep the trellis canopy ventilated and well lit.',
    '合理修剪，保持树冠通风透光。': 'Prune sensibly to keep the canopy ventilated and well lit.',
    '合理修剪，保持通风透光。': 'Prune sensibly to keep the canopy ventilated and well lit.',
    '合理密植，保持田间通风透光。': 'Use a sensible planting density so the field stays ventilated and well lit.',
    '合理密植，保持通风透光。': 'Use a sensible planting density to keep the canopy ventilated and well lit.',
    '合理密植，避免过密。': 'Use a sensible planting density and avoid overcrowding.',
    '合理密植，避免过密导致通风不良。': 'Use a sensible planting density; overcrowding impedes ventilation.',
    '合理控制浇水，避免大水漫灌。': 'Water sensibly and avoid flood irrigation.',
    '合理施肥，增强树势。': 'Fertilise sensibly to keep the trees vigorous.',
    '合理施肥，增强树势，提高抗病性。': 'Fertilise sensibly to keep the trees vigorous and improve disease resistance.',
    '合理施肥，增强植株抗性。': 'Fertilise sensibly to improve plant resistance.',
    '合理施肥，避免盐害。': 'Fertilise sensibly and avoid salt injury.',
    '合理浇水，避免干旱。': 'Water sensibly and avoid drought stress.',
    '合理灌溉，保持土壤湿润。': 'Irrigate sensibly to keep the soil moist.',
    '合理灌溉，避免干旱。': 'Irrigate sensibly and avoid drought stress.',
    '合理调控土壤pH值，保持在4.5-5.5之间。': 'Keep the soil pH within a sensible range of 4.5–5.5.',
    '合理调控土壤湿度，及时排水。': 'Keep soil moisture at a sensible level and drain promptly.',
    '合理调控温湿度。': 'Keep temperature and humidity at sensible levels.',
    '合理调控温湿度，创造不利于病害发生的环境。': 'Keep temperature and humidity at sensible levels to create conditions unfavourable to the disease.',
    '合理调控温湿度，创造不利于螨类繁殖的环境。': 'Keep temperature and humidity at sensible levels to create conditions unfavourable to mite reproduction.',
    '合理调控温湿度，避免高温强光。': 'Keep temperature and humidity at sensible levels and avoid high heat with intense light.',
    '合理调控环境条件，创造不利于病害发生的环境。': 'Keep environmental conditions at sensible levels to create an environment unfavourable to the disease.',
    '合理调控田间湿度，及时排水。': 'Keep field humidity at a sensible level and drain promptly.',
    '合理负载，避免结果过多。': 'Keep the crop load sensible and avoid overbearing.',
    '同时防治传毒媒介蚜虫，喷施10%吡虫啉可湿性粉剂2000倍液。': 'At the same time control the aphid vector by spraying 10% imidacloprid WP at 2000× dilution.',
    '在低温高湿季节增加检查频率。': 'Inspect more often during cool, humid seasons.',
    '在发病季节增加检查频率。': 'Inspect more often during the disease season.',
    '在发病季节（春秋季）每3-5天检查一次。': 'Inspect every 3–5 days during the disease season (spring and autumn).',
    '在春季萌芽期重点检查。': 'Focus inspections on the spring bud-break period.',
    '在田间设置黄板诱杀成螨。': 'Set yellow sticky boards in the field to trap adult mites.',
    '在田间设置黄板诱杀木虱。': 'Set yellow sticky boards in the field to trap psyllids.',
    '在田间设置黄板诱杀烟粉虱。': 'Set yellow sticky boards in the field to trap whitefly.',
    '在田间设置黄板诱杀蚜虫。': 'Set yellow sticky boards in the field to trap aphids.',
    '在病毒病高发季节增加检查频率。': 'Inspect more often during the peak season for viral diseases.',
    '在高温季节增加检查频率。': 'Inspect more often during hot weather.',
    '在高温干旱季节每天检查。': 'Inspect daily during hot, dry weather.',
    '在高温高湿季节增加检查频率。': 'Inspect more often during hot, humid weather.',
    '在高温高湿季节每天检查。': 'Inspect daily during hot, humid weather.',
    '地膜覆盖，保持土壤湿度。': 'Use plastic mulch to maintain soil moisture.',
    '增施有机肥，增强树势。': 'Apply more organic fertiliser to keep the trees vigorous.',
    '增施有机肥，增强植株抗性。': 'Apply more organic fertiliser to improve plant resistance.',
    '增施有机肥，提高植株抗病力。': 'Apply more organic fertiliser to raise the plants’ disease resistance.',
    '定期检查叶片和果实。': 'Inspect leaves and fruit regularly.',
    '定期检查叶片和果实，重点检查下部叶片。': 'Inspect leaves and fruit regularly, focusing on the lower leaves.',
    '定期检查叶片，注意观察是否有水渍状斑点。': 'Inspect the leaves regularly and look out for water-soaked spots.',
    '定期检查叶片，重点检查下部叶片。': 'Inspect the leaves regularly, focusing on the lower leaves.',
    '定期检查叶片，重点检查中上部叶片。': 'Inspect the leaves regularly, focusing on the middle and upper leaves.',
    '定期检查叶片，重点检查叶缘。': 'Inspect the leaves regularly, focusing on the leaf margins.',
    '定期检查叶片，重点检查嫩梢。': 'Inspect the leaves regularly, focusing on the young shoots.',
    '定期检查叶背面，因为霉层首先出现在叶背。': 'Inspect the underside of the leaves regularly, because the mould growth appears there first.',
    '定期检查叶背面，重点检查下部叶片。': 'Inspect the underside of the leaves regularly, focusing on the lower leaves.',
    '定期检查果实和叶片。': 'Inspect fruit and leaves regularly.',
    '定期检查植株，注意观察叶片症状。': 'Inspect the plants regularly and watch for leaf symptoms.',
    '定期田间巡查，及时发现异常。': 'Patrol the field regularly to spot anything unusual early.',
    '定期田间巡查，重点检查下部叶片。': 'Patrol the field regularly, focusing on the lower leaves.',
    '定植前用50%多菌灵可湿性粉剂500倍液蘸根。': 'Before transplanting, dip the roots in 50% carbendazim WP at 500× dilution.',
    '定植后定期检查植株下部叶片。': 'After transplanting, inspect the lower leaves regularly.',
    '实行2-3年轮作，避免与茄科作物连作。': 'Rotate with other crops for 2–3 years; do not grow Solanaceous crops back to back.',
    '实行轮作，避免与茄科作物连作。': 'Practise crop rotation; do not grow Solanaceous crops back to back.',
    '实行轮作，避免连作。': 'Practise crop rotation and avoid continuous cropping.',
    '建立健康档案，记录生长状况。': 'Keep a crop record and log the growth status.',
    '建立病害档案，指导次年预防。': 'Keep a disease record to guide prevention the following year.',
    '建立病害监测点，实时监控。': 'Set up disease monitoring points for real-time surveillance.',
    '建立病害预警系统。': 'Set up a disease early-warning system.',
    '建立病害预警系统，监测温湿度变化，提前预防。': 'Set up a disease early-warning system that tracks temperature and humidity so you can act early.',
    '建立病毒病预警系统。': 'Set up an early-warning system for viral diseases.',
    '建立虫情监测系统。': 'Set up a pest monitoring system.',
    '操作前后用肥皂洗手消毒。': 'Wash your hands with soap before and after working in the crop.',
    '操作工具用10%漂白粉溶液消毒。': 'Disinfect tools with a 10% bleaching powder solution.',
    '收获后彻底清除病残体。': 'After harvest, clear diseased plant debris thoroughly.',
    '春季萌芽前喷施石硫合剂，花后喷施三唑酮。': 'Spray lime sulphur before bud break in spring and triadimefon after flowering.',
    '果实套袋保护。': 'Bag the fruit for protection.',
    '果实套袋前喷施苯醚甲环唑或戊唑醇等药剂。': 'Before bagging the fruit, spray difenoconazole, tebuconazole or a similar fungicide.',
    '每隔5-7天喷一次，连续2-3次。': 'Spray every 5–7 days, for 2–3 applications in a row.',
    '每隔7-10天喷一次，连续2-3次。': 'Spray every 7–10 days, for 2–3 applications in a row.',
    '每隔7-10天喷一次，连续3-4次。': 'Spray every 7–10 days, for 3–4 applications in a row.',
    '注意轮换用药，避免产生抗药性。': 'Rotate between different products to avoid resistance building up.',
    '清除周围的柏树或保持距离。': 'Remove nearby junipers or keep them at a distance.',
    '监测土壤湿度，及时调整。': 'Monitor soil moisture and adjust promptly.',
    '监测环境条件，及时调整。': 'Monitor the environmental conditions and adjust promptly.',
    '监测田间湿度，及时调整。': 'Monitor field humidity and adjust promptly.',
    '监测田间湿度，及时通风。': 'Monitor field humidity and ventilate promptly.',
    '种子用10%磷酸三钠溶液浸种20分钟消毒。': 'Disinfect seed by soaking it in a 10% trisodium phosphate solution for 20 minutes.',
    '种子用52℃温水浸种30分钟消毒。': 'Disinfect seed by soaking it in water at 52 °C for 30 minutes.',
    '种子用55℃温水浸种15分钟消毒。': 'Disinfect seed by soaking it in water at 55 °C for 15 minutes.',
    '种子用55℃温水浸种15分钟消毒，或用72%农用链霉素可溶性粉剂500倍液浸种2小时。': 'Disinfect seed by soaking it in water at 55 °C for 15 minutes, or in 72% agricultural streptomycin SP at 500× dilution for 2 hours.',
    '种子用55℃温水浸种15分钟进行消毒。': 'Disinfect the seed by soaking it in water at 55 °C for 15 minutes.',
    '科学施肥，增强植株抗性。': 'Fertilise according to crop needs to improve plant resistance.',
    '科学施肥，增强植株抗病性。': 'Fertilise according to crop needs to improve disease resistance.',
    '科学灌溉，避免积水。': 'Irrigate according to crop needs and avoid waterlogging.',
    '花前花后各喷一次杀菌剂，如多菌灵、代森锰锌等。': 'Spray a fungicide once before and once after flowering, for example carbendazim or mancozeb.',
    '记录发病时间和条件，分析发病规律。': 'Record when and under what conditions the disease appears, and analyse the pattern.',
    '记录发病规律，指导预防。': 'Record the disease pattern to guide prevention.',
    '设置防虫网。': 'Install insect-proof netting.',
    '设置防虫网，阻止木虱传播。': 'Install insect-proof netting to block psyllid transmission.',
    '设置防虫网，阻止烟粉虱传播。': 'Install insect-proof netting to block whitefly transmission.',
    '设置防虫网，阻止病菌传播。': 'Install insect-proof netting to block the spread of the pathogen.',
    '设置防虫网，阻止蚜虫传播。': 'Install insect-proof netting to block aphid transmission.',
    '设置防虫网，阻止螨类传播。': 'Install insect-proof netting to block mite transmission.',
    '选用健康种子，进行种子消毒。': 'Use healthy seed and disinfect it before sowing.',
    '选用健康种薯。': 'Use healthy seed tubers.',
    '选用健康种薯，进行种薯消毒。': 'Use healthy seed tubers and disinfect them.',
    '选用抗病品种，及时清除病叶病果。': 'Grow resistant varieties and remove diseased leaves and fruit promptly.',
    '选用抗病品种，合理密植。': 'Grow resistant varieties and use a sensible planting density.',
    '选用抗病品种，合理密植，保持通风透光。': 'Grow resistant varieties, use a sensible planting density and keep the canopy ventilated and well lit.',
    '选用抗病品种，如"中蔬4号"、"佳红"等。': 'Grow resistant varieties such as Zhongshu No. 4 or Jiahong.',
    '选用抗病品种，如"佳粉15号"、"中蔬5号"等。': 'Grow resistant varieties such as Jiafen No. 15 or Zhongshu No. 5.',
    '选用抗病品种，如"毛粉802"、"中杂9号"等。': 'Grow resistant varieties such as Maofen 802 or Zhongza No. 9.',
    '选用抗病品种，实行轮作，避免与茄科作物连作。': 'Grow resistant varieties and rotate crops; do not grow Solanaceous crops back to back.',
    '选用抗病品种，实行轮作，避免连作。': 'Grow resistant varieties and rotate crops instead of cropping continuously.',
    '选用抗病品种，避免连作。': 'Grow resistant varieties and avoid continuous cropping.',
    '避免在柏树附近种植苹果树。': 'Avoid planting apple trees near junipers.',
    '避免在病株上操作后接触健康植株。': 'Do not move from diseased plants to healthy ones without cleaning up first.',
    '避免在阴天或雨天整枝。': 'Avoid pruning on overcast or rainy days.',
    '避免大水漫灌。': 'Avoid flood irrigation.',
    '采用地膜覆盖栽培。': 'Use plastic film mulch.',
    '采用地膜覆盖栽培，减少土壤中病菌传播。': 'Use plastic film mulch to reduce the spread of the pathogen from the soil.',
    '采用地膜覆盖，减少病菌传播。': 'Use plastic film mulch to reduce the spread of the pathogen.',
    '采用地膜覆盖，阻止螨类入土越冬。': 'Use plastic film mulch to stop mites from entering the soil to overwinter.',
    '采用无病苗木。': 'Use disease-free nursery stock.',
    '采用滴灌，减少水分蒸发。': 'Use drip irrigation to reduce evaporation.',
    '采用硫磺熏蒸。': 'Use sulphur fumigation.',
    '采用膜下滴灌，减少叶面湿度。': 'Use drip irrigation under film to keep the foliage dry.',
    '采用膜下滴灌，避免叶面长时间湿润。': 'Use drip irrigation under film so the foliage does not stay wet for long.',
    '采用遮阳网遮阴。': 'Use a shade net to provide shade.',
    '采用遮阳网，降低光照强度。': 'Use a shade net to reduce light intensity.',
    '采用高垄栽培，加强排水。': 'Grow on raised ridges to improve drainage.',
    '释放天敌丽蚜小蜂。': 'Release the natural enemy Encarsia formosa.',
    '释放天敌进行生物防治。': 'Release natural enemies for biological control.',
    '释放捕食螨等天敌进行生物防治。': 'Release predatory mites and other natural enemies for biological control.',
    '重点喷洒叶背面。': 'Direct the spray mainly at the underside of the leaves.',
    '重点监测木虱数量。': 'Monitor psyllid numbers closely.',
    '重点监测烟粉虱数量。': 'Monitor whitefly numbers closely.',
    '重点监测蚜虫数量。': 'Monitor aphid numbers closely.',
    '重点防治传毒媒介柑橘木虱，喷施25%噻虫嗪水分散粒剂3000倍液，或10%吡虫啉可湿性粉剂2000倍液。': 'Focus on controlling the vector, the Asian citrus psyllid: spray 25% thiamethoxam WG at 3000× dilution, or 10% imidacloprid WP at 2000× dilution.',
    '重点防治传毒媒介烟粉虱，喷施25%噻虫嗪水分散粒剂3000倍液，或10%吡虫啉可湿性粉剂2000×液。': 'Focus on controlling the vector, whitefly: spray 25% thiamethoxam WG at 3000× dilution, or 10% imidacloprid WP at 2000× dilution.',
    '重点防治传毒媒介烟粉虱，喷施25%噻虫嗪水分散粒剂3000倍液，或10%吡虫啉可湿性粉剂2000倍液。': 'Focus on controlling the vector, whitefly: spray 25% thiamethoxam WG at 3000× dilution, or 10% imidacloprid WP at 2000× dilution.',
    '高温闷棚可有效抑制病菌。': 'Sealing the greenhouse at high temperature suppresses the pathogen effectively.',
}


def build_english(measure, missing):
    """按中文句号切分 → 逐句查表 → 空格连接；任一句缺译文则返回空串并记录"""
    parts = []
    for raw in SENTENCE_SPLIT.split(measure or ''):
        sentence = raw.strip()
        if not sentence:
            continue
        english = SENTENCE_EN.get(sentence)
        if not english:
            missing.add(sentence)
            return ''
        parts.append(english)
    return ' '.join(parts)


class Command(BaseCommand):
    help = '为防治方法（PreventionMethod.measure_en）回填英文语料'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='只统计，不写库')
        parser.add_argument('--force', action='store_true', help='已填过英文的也重新生成')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']

        missing = set()
        updated = 0
        skipped = 0
        untouched = 0

        for method in PreventionMethod.objects.all().order_by('id'):
            if method.measure_en and not force:
                skipped += 1
                continue
            english = build_english(method.measure, missing)
            if not english:
                untouched += 1
                continue
            if not dry_run:
                method.measure_en = english
                method.save(update_fields=['measure_en'])
            updated += 1

        verb = '可回填' if dry_run else '已回填'
        self.stdout.write(f'{verb} {updated} 条；已有英文跳过 {skipped} 条；缺语料未处理 {untouched} 条')
        self.stdout.write(f'语料表大小 {len(SENTENCE_EN)} 句')

        if missing:
            self.stderr.write(self.style.ERROR(f'以下 {len(missing)} 句没有英文语料（不会静默留中文）：'))
            for sentence in sorted(missing):
                self.stderr.write(f'  · {sentence}')
            raise SystemExit(1)

        if dry_run:
            self.stdout.write(self.style.WARNING('（--dry-run：没有写库）'))
